"""
区块链核心模块 —— 农产品供应链溯源系统
======================================

模块内容
--------
* :class:`Transaction` —— 供应链溯源交易（**内容寻址**：``tx_id`` 由交易内容实时派生）
* :class:`Block`       —— 区块（Merkle 根 + 独立难度 + 工作量证明）
* :class:`Blockchain`  —— 链管理、挖矿、索引、追溯、完整性审计与持久化

相对早期版本修正的关键问题
--------------------------
1. **交易 ID 改为派生属性**。早期版本在 ``__init__`` 中缓存 ``tx_id``，
   修改 ``tx.data`` 之后缓存不会更新，导致区块哈希不变、篡改无法被发现。
   现在 ``tx_id`` 是 ``@property``，每次读取都由当前内容重新哈希。
2. **区块哈希提交到交易内容**。区块哈希通过 Merkle 根覆盖全部交易的当前
   内容哈希（而非缓存的 ID），任何数据改动都会改变 Merkle 根 → 改变区块
   哈希 → 被 ``is_chain_valid()`` 检出。
3. **难度随块存储**。动态调整难度后，历史区块仍能按其自身难度正确验证；
   早期版本用链级难度校验所有区块，调整后会误报。
4. **索引由链重建**。产品索引不再持久化后被无条件信任，而是在加载与挖矿
   后从链上重新构建。早期版本按"交易条数"重复追加区块下标，使
   ``trace_product`` 返回 N 倍重复记录。
5. **创世区块同样满足 PoW 并被校验**。早期版本跳过 index 0 的校验，
   而创世区块的哈希其实并不满足难度目标。
6. **原子化持久化**。先写临时文件再 ``os.replace``，避免写入中断导致
   数据文件损坏。
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union

__all__ = [
    "Transaction",
    "Block",
    "Blockchain",
    "canonical_json",
    "sha256_hex",
    "compute_merkle_root",
    "merkle_proof",
    "verify_merkle_proof",
    "TRANSACTION_TYPES",
    "REQUIRED_FIELDS",
    "SCHEMA_VERSION",
    "resolve_data_dir",
    "is_dir_writable",
]

# ── 常量 ────────────────────────────────────────────────────────────────────

SCHEMA_VERSION = 2
GENESIS_TIMESTAMP = 1700000000  # 2023-11-15，固定值以保证创世区块可复现
GENESIS_PREV_HASH = "0" * 64
GENESIS_DIFFICULTY = 4

#: 创世区块那笔合成占位交易的产品编号。它代表"链的起点"而非一笔真实业务
#: 记录，因此统计、图表与交易明细默认都要把它排除，否则「交易总数」会比
#: 实际业务交易多 1，环节分布图里也会凭空多出一条"生产记录"。
GENESIS_PRODUCT_ID = "GENESIS"

TRANSACTION_TYPES: Dict[str, str] = {
    "production": "生产记录",
    "processing": "加工记录",
    "logistics": "物流记录",
    "sale": "销售记录",
}

#: 各交易类型必须提供的字段（用于上链前校验）
REQUIRED_FIELDS: Dict[str, List[str]] = {
    "production": ["product_id", "product_name", "producer", "origin"],
    "processing": ["product_id", "product_name", "processor", "process_type"],
    "logistics": [
        "product_id",
        "product_name",
        "logistics_provider",
        "departure",
        "destination",
    ],
    "sale": ["product_id", "product_name", "seller", "store"],
}


# ── 通用工具 ────────────────────────────────────────────────────────────────


def sha256_hex(text: str) -> str:
    """返回字符串 UTF-8 编码后的 SHA-256 十六进制摘要。"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_json(obj: Any) -> str:
    """
    生成**确定性** JSON 文本，用于哈希计算。

    键按字典序排序、去掉多余空白，因此同一个字典无论插入顺序如何，
    得到的哈希都一致。
    """
    return json.dumps(
        obj,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )


def to_jsonable(value: Any) -> Any:
    """
    把任意值递归转换为可稳定序列化的 JSON 原生类型。

    ``streamlit`` 的控件可能返回 ``numpy`` 标量或 ``datetime``，
    统一转换后再存链，避免哈希在不同运行环境下漂移。
    """
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_jsonable(v) for v in value]

    # numpy 标量等：优先使用 .item() 还原为 Python 原生类型
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return to_jsonable(item())
        except Exception:  # pragma: no cover - 极少数不可转换对象
            pass
    return str(value)


# ── 数据目录解析 ────────────────────────────────────────────────────────────


def is_dir_writable(path: Union[str, Path]) -> bool:
    """探测目录是否可写（不存在则尝试创建）。"""
    path = Path(path)
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write_probe"
        with open(probe, "w", encoding="utf-8") as handle:
            handle.write("ok")
        probe.unlink()
        return True
    except OSError:
        return False


def resolve_data_dir(preferred: Optional[str] = None) -> Path:
    """
    选择一个**确实可写**的目录来保存链数据。

    依次尝试：显式参数 → 环境变量 ``AGRI_CHAIN_DATA_DIR`` → 项目下的
    ``blockchain_data`` → 项目下的 ``data`` → 用户主目录。全部不可写时退回
    系统临时目录。

    之所以要探测而不是直接写死路径：项目可能被放在只读目录、被容器挂载为
    只读卷，或（如本机遇到的）被沙箱/安全策略限制写入。写死路径会让程序在
    这些环境下直接崩溃。
    """
    candidates: List[Path] = []
    if preferred:
        candidates.append(Path(preferred))
    env = os.environ.get("AGRI_CHAIN_DATA_DIR")
    if env:
        candidates.append(Path(env))

    project_root = Path(__file__).resolve().parent
    candidates.append(project_root / "blockchain_data")
    candidates.append(project_root / "data")
    candidates.append(Path.home() / ".agri_blockchain")

    for candidate in candidates:
        if is_dir_writable(candidate):
            return candidate

    fallback = Path(tempfile.gettempdir()) / "agri_blockchain"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


# ── Merkle 树 ───────────────────────────────────────────────────────────────


def _merkle_levels(leaves: Sequence[str]) -> List[List[str]]:
    """自底向上构建各层哈希；奇数个节点时复制最后一个节点（比特币做法）。"""
    levels: List[List[str]] = [list(leaves)]
    current = list(leaves)
    while len(current) > 1:
        nxt: List[str] = []
        for i in range(0, len(current), 2):
            left = current[i]
            right = current[i + 1] if i + 1 < len(current) else left
            nxt.append(sha256_hex(left + right))
        levels.append(nxt)
        current = nxt
    return levels


def compute_merkle_root(tx_ids: Sequence[str]) -> str:
    """由交易 ID 列表计算 Merkle 根。空区块返回固定哨兵值。"""
    if not tx_ids:
        return sha256_hex("EMPTY_BLOCK")
    leaves = [sha256_hex(tx_id) for tx_id in tx_ids]
    return _merkle_levels(leaves)[-1][0]


def merkle_proof(tx_ids: Sequence[str], index: int) -> List[Tuple[str, bool]]:
    """
    生成第 ``index`` 笔交易的 Merkle 包含证明（轻客户端验证用）。

    返回 ``[(兄弟哈希, 兄弟是否在左侧), ...]``。
    """
    if not 0 <= index < len(tx_ids):
        raise IndexError(f"交易下标超出范围: {index}")

    leaves = [sha256_hex(tx_id) for tx_id in tx_ids]
    levels = _merkle_levels(leaves)
    proof: List[Tuple[str, bool]] = []
    idx = index

    for level in levels[:-1]:
        sibling = idx ^ 1
        if sibling < len(level):
            proof.append((level[sibling], sibling < idx))
        else:
            # 该层节点数为奇数，自己与自己配对
            proof.append((level[idx], False))
        idx //= 2
    return proof


def verify_merkle_proof(
    tx_id: str, proof: Iterable[Tuple[str, bool]], root: str
) -> bool:
    """用 Merkle 证明校验某笔交易确实属于给定根。"""
    digest = sha256_hex(tx_id)
    for sibling, sibling_is_left in proof:
        if sibling_is_left:
            digest = sha256_hex(sibling + digest)
        else:
            digest = sha256_hex(digest + sibling)
    return digest == root


# ── 交易 ────────────────────────────────────────────────────────────────────


class Transaction:
    """
    供应链溯源交易。

    ``tx_id`` 是**派生属性**：每次读取都根据当前 ``tx_type``/``data``/
    ``timestamp`` 重新计算。因此对交易内容的任何修改都会立即改变其 ID，
    并向上传播到 Merkle 根与区块哈希 —— 这是篡改可被检出的前提。
    """

    TRANSACTION_TYPES = TRANSACTION_TYPES

    def __init__(
        self,
        tx_type: str,
        data: Dict[str, Any],
        timestamp: Optional[float] = None,
    ) -> None:
        if tx_type not in TRANSACTION_TYPES:
            raise ValueError(
                f"无效的交易类型: {tx_type}，可选: {list(TRANSACTION_TYPES)}"
            )
        if not isinstance(data, dict):
            raise TypeError("交易数据必须是字典")

        self.tx_type: str = tx_type
        self.data: Dict[str, Any] = to_jsonable(data)
        self.timestamp: float = float(time.time() if timestamp is None else timestamp)

    # -- 哈希 / 身份 --------------------------------------------------------

    def compute_tx_id(self) -> str:
        """根据当前内容计算交易 ID（内容寻址）。"""
        return sha256_hex(
            canonical_json(
                {
                    "tx_type": self.tx_type,
                    "data": self.data,
                    "timestamp": self.timestamp,
                }
            )
        )

    @property
    def tx_id(self) -> str:
        """交易唯一 ID，始终与当前内容保持一致。"""
        return self.compute_tx_id()

    @property
    def tx_type_label(self) -> str:
        return TRANSACTION_TYPES[self.tx_type]

    @property
    def is_genesis(self) -> bool:
        """是否为创世区块里那笔合成占位交易（不是真实业务记录）。"""
        return self.data.get("product_id") == GENESIS_PRODUCT_ID

    @property
    def product_id(self) -> Optional[str]:
        value = self.data.get("product_id")
        return str(value) if value else None

    @property
    def timestamp_str(self) -> str:
        return datetime.fromtimestamp(self.timestamp).strftime("%Y-%m-%d %H:%M:%S")

    # -- 校验 --------------------------------------------------------------

    def missing_fields(self) -> List[str]:
        """返回缺失的必填业务字段。"""
        return [
            field
            for field in REQUIRED_FIELDS.get(self.tx_type, [])
            if not str(self.data.get(field, "")).strip()
        ]

    def validate(self) -> Tuple[bool, List[str]]:
        """结构 + 业务字段校验，返回 ``(是否通过, 问题列表)``。"""
        problems: List[str] = []
        if self.tx_type not in TRANSACTION_TYPES:
            problems.append(f"未知交易类型: {self.tx_type}")

        missing = self.missing_fields()
        if missing:
            problems.append("缺少必填字段: " + "、".join(missing))

        if self.timestamp <= 0:
            problems.append("时间戳无效")

        if self.product_id and self.product_id.strip() == "":
            problems.append("产品 ID 不能为空白")

        return (not problems), problems

    # -- 序列化 ------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tx_id": self.tx_id,
            "tx_type": self.tx_type,
            "tx_type_label": self.tx_type_label,
            "data": self.data,
            "timestamp": self.timestamp,
            "timestamp_str": self.timestamp_str,
        }

    def to_summary(self) -> Dict[str, Any]:
        """面向表格展示的扁平化摘要。"""
        return {
            "交易ID": self.tx_id,
            "环节": self.tx_type_label,
            "产品ID": self.product_id or "-",
            "产品名称": self.data.get("product_name", "-"),
            "时间": self.timestamp_str,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "Transaction":
        return cls(
            tx_type=payload["tx_type"],
            data=payload.get("data", {}),
            timestamp=payload.get("timestamp"),
        )

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return f"Transaction({self.tx_id[:12]}… | {self.tx_type_label})"


# ── 区块 ────────────────────────────────────────────────────────────────────


class Block:
    """
    区块。

    哈希载荷包含 ``difficulty``，因此把难度调低来重挖旧块同样会改变哈希、
    破坏链接关系，无法悄悄降低攻击成本。
    """

    def __init__(
        self,
        index: int,
        transactions: Sequence[Transaction],
        previous_hash: str,
        nonce: int = 0,
        timestamp: Optional[float] = None,
        difficulty: int = 4,
        block_hash: Optional[str] = None,
    ) -> None:
        self.index: int = int(index)
        self.transactions: List[Transaction] = list(transactions)
        self.timestamp: float = float(time.time() if timestamp is None else timestamp)
        self.previous_hash: str = previous_hash
        self.nonce: int = int(nonce)
        self.difficulty: int = int(difficulty)
        self.hash: str = block_hash if block_hash else self.calculate_hash()

    # -- 哈希 --------------------------------------------------------------

    @property
    def tx_ids(self) -> List[str]:
        """**实时**计算各交易的 ID（会反映任何内容改动）。"""
        return [tx.tx_id for tx in self.transactions]

    @property
    def merkle_root(self) -> str:
        return compute_merkle_root(self.tx_ids)

    def _hash_payload(self, nonce: int, merkle_root: str) -> Dict[str, Any]:
        return {
            "index": self.index,
            "timestamp": self.timestamp,
            "previous_hash": self.previous_hash,
            "nonce": nonce,
            "difficulty": self.difficulty,
            "merkle_root": merkle_root,
            "tx_count": len(self.transactions),
        }

    def calculate_hash(self) -> str:
        """按当前内容计算区块哈希。"""
        return sha256_hex(canonical_json(self._hash_payload(self.nonce, self.merkle_root)))

    @property
    def pow_target(self) -> str:
        return "0" * self.difficulty

    def satisfies_pow(self) -> bool:
        return self.hash.startswith(self.pow_target)

    # -- 挖矿 --------------------------------------------------------------

    def mine(self, difficulty: Optional[int] = None) -> Tuple[int, int]:
        """
        执行工作量证明。

        :return: ``(nonce, 尝试次数)``
        """
        if difficulty is not None:
            self.difficulty = int(difficulty)

        merkle_root = self.merkle_root  # 挖矿期间固定，避免重复计算
        target = self.pow_target
        nonce = self.nonce
        attempts = 0

        while True:
            digest = sha256_hex(canonical_json(self._hash_payload(nonce, merkle_root)))
            attempts += 1
            if digest.startswith(target):
                self.nonce = nonce
                self.hash = digest
                return nonce, attempts
            nonce += 1

    # -- Merkle 证明 --------------------------------------------------------

    def proof_for(self, tx_index: int) -> List[Tuple[str, bool]]:
        return merkle_proof(self.tx_ids, tx_index)

    # -- 序列化 ------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "timestamp": self.timestamp,
            "timestamp_str": datetime.fromtimestamp(self.timestamp).strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            "transactions": [tx.to_dict() for tx in self.transactions],
            "previous_hash": self.previous_hash,
            "hash": self.hash,
            "nonce": self.nonce,
            "difficulty": self.difficulty,
            "merkle_root": self.merkle_root,
            "tx_count": len(self.transactions),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "Block":
        transactions = [
            Transaction.from_dict(tx) for tx in payload.get("transactions", [])
        ]
        return cls(
            index=payload["index"],
            transactions=transactions,
            previous_hash=payload["previous_hash"],
            nonce=payload.get("nonce", 0),
            timestamp=payload.get("timestamp"),
            difficulty=payload.get("difficulty", GENESIS_DIFFICULTY),
            block_hash=payload.get("hash"),
        )

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return f"Block #{self.index} | {self.hash[:12]}… | {len(self.transactions)} txs"


# ── 区块链 ──────────────────────────────────────────────────────────────────


class Blockchain:
    """农产品供应链溯源区块链。"""

    DIFFICULTY = 4
    MIN_DIFFICULTY = 2
    MAX_DIFFICULTY = 5
    TARGET_BLOCK_SECONDS = 3.0
    ADJUST_EVERY = 3

    DATA_DIR = "blockchain_data"
    DATA_FILE = "blockchain_backup.json"

    def __init__(self, difficulty: int = DIFFICULTY, auto_adjust: bool = False) -> None:
        self.chain: List[Block] = []
        self.pending_transactions: List[Transaction] = []
        self.difficulty: int = int(difficulty)
        self.auto_adjust: bool = bool(auto_adjust)
        self.participants: Dict[str, Dict[str, Any]] = {}
        self.mining_log: List[Dict[str, Any]] = []

        # 索引：由链重建，不持久化信任
        self.product_index: Dict[str, List[Tuple[int, int]]] = {}
        self.product_blocks: Dict[str, List[int]] = {}
        self._by_index: Dict[int, Block] = {}

        self._create_genesis_block()
        self.rebuild_indexes()

    # -- 创世 --------------------------------------------------------------

    def _create_genesis_block(self) -> Block:
        genesis_tx = Transaction(
            "production",
            {
                "product_id": GENESIS_PRODUCT_ID,
                "product_name": "创世区块",
                "producer": "区块链系统",
                "origin": "系统初始化",
                "notes": "农产品供应链溯源区块链的起源区块",
            },
            timestamp=GENESIS_TIMESTAMP,
        )
        genesis = Block(
            index=0,
            transactions=[genesis_tx],
            previous_hash=GENESIS_PREV_HASH,
            timestamp=GENESIS_TIMESTAMP,
            difficulty=GENESIS_DIFFICULTY,
        )
        # 创世区块同样需要满足工作量证明（早期版本跳过了这一步）
        genesis.mine(GENESIS_DIFFICULTY)
        self.chain.append(genesis)
        self._by_index[0] = genesis
        return genesis

    # -- 索引 --------------------------------------------------------------

    def rebuild_indexes(self) -> None:
        """从链上重建全部派生索引（发布/加载后调用）。"""
        self._by_index = {block.index: block for block in self.chain}
        self.product_index = {}
        self.product_blocks = {}

        for block in self.chain:
            for position, tx in enumerate(block.transactions):
                product_id = tx.product_id
                if not product_id or product_id == GENESIS_PRODUCT_ID:
                    continue
                self.product_index.setdefault(product_id, []).append(
                    (block.index, position)
                )
                blocks = self.product_blocks.setdefault(product_id, [])
                if not blocks or blocks[-1] != block.index:
                    blocks.append(block.index)

    # -- 交易 --------------------------------------------------------------

    def add_transaction(self, transaction: Transaction, *, validate: bool = True) -> str:
        """
        将交易放入待处理池。

        :raises ValueError: 校验失败或交易已存在
        :return: 交易 ID
        """
        if validate:
            ok, problems = transaction.validate()
            if not ok:
                raise ValueError("交易校验失败: " + "；".join(problems))

        tx_id = transaction.tx_id
        if self.find_transaction(tx_id) is not None:
            raise ValueError(f"交易已存在（重复提交）: {tx_id[:16]}…")

        self.pending_transactions.append(transaction)
        return tx_id

    def find_transaction(self, tx_id: str) -> Optional[Dict[str, Any]]:
        """在待处理池与已上链交易中查找交易。"""
        for tx in self.pending_transactions:
            if tx.tx_id == tx_id:
                return {"status": "pending", "transaction": tx, "block_index": None}
        for block in self.chain:
            for position, tx in enumerate(block.transactions):
                if tx.tx_id == tx_id:
                    return {
                        "status": "confirmed",
                        "transaction": tx,
                        "block_index": block.index,
                        "position": position,
                    }
        return None

    # -- 挖矿 --------------------------------------------------------------

    def mine_pending_transactions(self, miner_address: str = "system") -> Block:
        """把待处理池中的交易打包成新区块并上链。"""
        if not self.pending_transactions:
            raise ValueError("没有待处理的交易")

        block = Block(
            index=len(self.chain),
            transactions=self.pending_transactions[:],
            previous_hash=self.chain[-1].hash,
            difficulty=self.difficulty,
        )
        started = time.time()
        _, attempts = block.mine(self.difficulty)
        duration = time.time() - started

        self.chain.append(block)
        self._by_index[block.index] = block
        self.pending_transactions = []
        self.rebuild_indexes()

        self.mining_log.append(
            {
                "index": block.index,
                "miner": miner_address,
                "difficulty": block.difficulty,
                "nonce": block.nonce,
                "attempts": attempts,
                "duration_s": round(duration, 4),
                "tx_count": len(block.transactions),
                "timestamp": block.timestamp,
            }
        )
        self._maybe_adjust_difficulty()
        return block

    def _maybe_adjust_difficulty(self) -> None:
        """按最近若干块的出块速度小幅调整难度（链级，仅影响后续区块）。"""
        if not self.auto_adjust:
            return
        height = len(self.chain) - 1
        if height < self.ADJUST_EVERY or height % self.ADJUST_EVERY != 0:
            return

        window = self.chain[-self.ADJUST_EVERY - 1 :]
        span = window[-1].timestamp - window[0].timestamp
        if span <= 0:
            return
        average = span / (len(window) - 1)

        if average < self.TARGET_BLOCK_SECONDS / 2:
            self.difficulty = min(self.MAX_DIFFICULTY, self.difficulty + 1)
        elif average > self.TARGET_BLOCK_SECONDS * 2:
            self.difficulty = max(self.MIN_DIFFICULTY, self.difficulty - 1)

    # -- 查询 --------------------------------------------------------------

    def get_block(self, index: int) -> Optional[Block]:
        return self._by_index.get(index)

    def get_product_list(self) -> List[str]:
        return sorted(self.product_index)

    def all_transactions(self, *, include_genesis: bool = False) -> List[Dict[str, Any]]:
        """
        按区块顺序返回全部已上链交易的扁平记录。

        :param include_genesis: 是否包含创世区块的合成占位交易。默认为
            ``False``：那笔记录代表"链的起点"，不是业务数据，混进统计和
            图表会让交易总数虚增 1、环节分布里凭空多一条"生产记录"。
        """
        records: List[Dict[str, Any]] = []
        for block in self.chain:
            for position, tx in enumerate(block.transactions):
                if tx.is_genesis and not include_genesis:
                    continue
                records.append(
                    {
                        "block_index": block.index,
                        "position": position,
                        "block_hash": block.hash,
                        "tx": tx,
                        **tx.to_dict(),
                    }
                )
        return records

    def trace_product(self, product_id: str) -> List[Dict[str, Any]]:
        """
        追溯某产品的全部供应链记录，按时间排序。

        .. note::
           早期版本遍历"按交易条数重复追加"的区块下标列表，导致同一笔记录
           被返回 4 次（4 笔交易 → 16 条结果）。现在使用
           :attr:`product_index` 中 ``(区块下标, 交易下标)`` 精确索引，
           每笔交易只出现一次。
        """
        records: List[Dict[str, Any]] = []
        seen: set = set()

        for block_index, position in self.product_index.get(product_id, []):
            if (block_index, position) in seen:
                continue
            block = self._by_index.get(block_index)
            if block is None or position >= len(block.transactions):
                continue

            tx = block.transactions[position]
            if tx.product_id != product_id:
                continue

            seen.add((block_index, position))
            records.append(
                {
                    "block_index": block.index,
                    "block_hash": block.hash,
                    "block_time": datetime.fromtimestamp(block.timestamp).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                    "tx_index": position,
                    # 保留交易对象本身，供业务规则（冷链/保质期）直接使用
                    "tx": tx,
                    **tx.to_dict(),
                }
            )

        records.sort(key=lambda item: (item["timestamp"], item["block_index"]))
        return records

    # -- 审计 --------------------------------------------------------------

    def audit_chain(self) -> List[Dict[str, Any]]:
        """逐块校验，返回可展示的审计明细。"""
        rows: List[Dict[str, Any]] = []
        for position, block in enumerate(self.chain):
            previous = self.chain[position - 1] if position > 0 else None

            hash_ok = block.hash == block.calculate_hash()
            prev_ok = (
                block.previous_hash == GENESIS_PREV_HASH
                if previous is None
                else block.previous_hash == previous.hash
            )
            pow_ok = block.satisfies_pow()
            merkle_ok = block.merkle_root == compute_merkle_root(block.tx_ids)
            tx_ok = all(tx.validate()[0] for tx in block.transactions)

            rows.append(
                {
                    "区块": block.index,
                    "高度": position,
                    "交易数": len(block.transactions),
                    "难度": block.difficulty,
                    "Nonce": block.nonce,
                    "哈希一致": hash_ok,
                    "链接正确": prev_ok,
                    "工作量证明": pow_ok,
                    "Merkle 根": merkle_ok,
                    "交易合法": tx_ok,
                    "通过": hash_ok and prev_ok and pow_ok and merkle_ok and tx_ok,
                    "哈希": block.hash,
                }
            )
        return rows

    def is_chain_valid(self) -> Tuple[bool, str]:
        """校验整条链（含创世区块），返回 ``(是否有效, 说明)``。"""
        if not self.chain:
            return False, "区块链为空"

        for position, block in enumerate(self.chain):
            previous = self.chain[position - 1] if position > 0 else None

            if block.hash != block.calculate_hash():
                return False, f"区块 #{block.index} 内容与哈希不一致（数据被篡改）"

            if block.merkle_root != compute_merkle_root(block.tx_ids):
                return False, f"区块 #{block.index} 的 Merkle 根不匹配"

            expected_prev = GENESIS_PREV_HASH if previous is None else previous.hash
            if block.previous_hash != expected_prev:
                return False, f"区块 #{block.index} 的前置哈希不匹配（链被断开）"

            if not block.satisfies_pow():
                return False, (
                    f"区块 #{block.index} 的工作量证明无效"
                    f"（需要 {block.difficulty} 个前导零）"
                )

            for tx in block.transactions:
                ok, problems = tx.validate()
                if not ok:
                    return False, f"区块 #{block.index} 存在非法交易: {'；'.join(problems)}"

        return True, f"区块链完整有效 ✅ 共 {len(self.chain)} 个区块全部通过校验"

    def verify_transaction_inclusion(
        self, tx_id: str, block_index: int
    ) -> Tuple[bool, str]:
        """用 Merkle 证明验证某交易确实包含在指定区块中。"""
        block = self._by_index.get(block_index)
        if block is None:
            return False, f"区块 #{block_index} 不存在"

        ids = block.tx_ids
        if tx_id not in ids:
            return False, "该区块不包含此交易"

        proof = block.proof_for(ids.index(tx_id))
        if verify_merkle_proof(tx_id, proof, block.merkle_root):
            return True, f"✅ Merkle 证明通过（证明路径 {len(proof)} 层）"
        return False, "❌ Merkle 证明失败"

    # -- 统计 --------------------------------------------------------------

    def get_chain_stats(self) -> Dict[str, Any]:
        """链级统计信息。"""
        # 「交易总数」只统计真实业务交易：创世区块里那笔合成占位交易不是业务
        # 记录，把它算进来会让总数比实际多 1、和环节分布图对不上。
        total_tx = sum(
            1 for block in self.chain for tx in block.transactions if not tx.is_genesis
        )
        chain_tx = sum(len(block.transactions) for block in self.chain)
        # 创世区块的时间戳是固定常量，把它计入间隔会得出无意义的巨大数值
        intervals = [
            self.chain[i].timestamp - self.chain[i - 1].timestamp
            for i in range(2, len(self.chain))
        ]
        avg_interval = sum(intervals) / len(intervals) if intervals else 0.0
        durations = [entry["duration_s"] for entry in self.mining_log]
        payload = json.dumps(
            [block.to_dict() for block in self.chain], ensure_ascii=False
        )

        return {
            "block_count": len(self.chain),
            "total_transactions": total_tx,
            "chain_transactions": chain_tx,
            "pending_transactions": len(self.pending_transactions),
            "difficulty": self.difficulty,
            "auto_adjust": self.auto_adjust,
            "unique_products": len(self.product_index),
            "confirmed_products": len(self.product_blocks),
            "participants": len(self.participants),
            "chain_size_kb": len(payload.encode("utf-8")) / 1024,
            "avg_block_seconds": avg_interval,
            "avg_mine_seconds": (
                sum(durations) / len(durations) if durations else 0.0
            ),
            "total_pow_attempts": sum(e["attempts"] for e in self.mining_log),
            "last_block_time": (
                datetime.fromtimestamp(self.chain[-1].timestamp).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
                if self.chain
                else "N/A"
            ),
        }

    # -- 篡改实验（仅内存，用于教学演示）-----------------------------------

    def tamper_transaction(
        self, block_index: int, position: int, field: str, new_value: Any
    ) -> Dict[str, Any]:
        """
        篡改指定交易的某个字段，返回篡改前后的对照片段。

        .. warning::
           仅修改内存中的对象，不会写回磁盘文件。
        """
        block = self._by_index.get(block_index)
        if block is None:
            raise ValueError(f"区块 #{block_index} 不存在")
        if not 0 <= position < len(block.transactions):
            raise ValueError("交易下标超出范围")

        tx = block.transactions[position]
        before = {
            "field": field,
            "value": tx.data.get(field),
            "tx_id": tx.tx_id,
            "block_hash": block.hash,
            "chain_valid": self.is_chain_valid()[0],
        }
        tx.data[field] = to_jsonable(new_value)
        after = {
            "field": field,
            "value": tx.data.get(field),
            "tx_id": tx.tx_id,
            "block_hash": block.hash,
            "recalculated_hash": block.calculate_hash(),
            "chain_valid": self.is_chain_valid()[0],
        }
        return {"before": before, "after": after, "block_index": block_index}

    # -- 参与方 ------------------------------------------------------------

    def register_participant(
        self, participant_id: str, name: str, role: str, extra: Optional[Dict] = None
    ) -> None:
        if not participant_id or not name:
            raise ValueError("参与方 ID 与名称不能为空")
        # extra 直接平铺进记录，便于界面按 info["type"] 等方式读取
        record = to_jsonable(dict(extra or {}))
        record["name"] = name
        record["role"] = role
        record["registered_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.participants[participant_id] = record

    def remove_participant(self, participant_id: str) -> bool:
        return self.participants.pop(participant_id, None) is not None

    # -- 持久化 ------------------------------------------------------------

    def _to_dict_full(self) -> Dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "difficulty": self.difficulty,
            "auto_adjust": self.auto_adjust,
            "chain": [block.to_dict() for block in self.chain],
            "pending_transactions": [tx.to_dict() for tx in self.pending_transactions],
            "participants": self.participants,
            "mining_log": self.mining_log,
        }

    def save_to_file(self, filepath: str) -> None:
        """原子化写入：先写临时文件并 fsync，再整体替换目标文件。"""
        target = Path(filepath)
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_suffix(target.suffix + ".tmp")

        with open(temp, "w", encoding="utf-8") as handle:
            json.dump(self._to_dict_full(), handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(temp, target)

    @classmethod
    def _from_dict(cls, payload: Dict[str, Any]) -> "Blockchain":
        chain = [Block.from_dict(item) for item in payload.get("chain", [])]
        if not chain:
            raise ValueError("数据文件中没有区块")

        instance = cls.__new__(cls)
        instance.chain = chain
        instance.difficulty = int(payload.get("difficulty", cls.DIFFICULTY))
        instance.auto_adjust = bool(payload.get("auto_adjust", False))
        instance.participants = payload.get("participants", {}) or {}
        instance.mining_log = payload.get("mining_log", []) or []
        instance.pending_transactions = [
            Transaction.from_dict(item)
            for item in payload.get("pending_transactions", [])
        ]

        instance.product_index = {}
        instance.product_blocks = {}
        instance._by_index = {block.index: block for block in chain}
        instance.rebuild_indexes()
        return instance

    @classmethod
    def load_from_file(
        cls, filepath: str, *, archive_incompatible: bool = True
    ) -> Optional["Blockchain"]:
        """
        从 JSON 文件加载区块链。

        文件不存在、损坏或 schema 版本不匹配时返回 ``None``（调用方应新建链）。
        旧版本数据文件会被重命名为 ``*.legacy-v<版本>-<时间戳>.bak`` 保留而非删除。
        """
        path = Path(filepath)
        if not path.exists():
            print(f"ℹ️  未找到本地区块链文件，将创建新的区块链: {filepath}")
            return None

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            print(f"⚠️  区块链文件损坏，将创建新的区块链: {error}")
            if archive_incompatible:
                cls._archive(path, "corrupt")
            return None

        version = int(payload.get("schema_version", 1))
        if version != SCHEMA_VERSION:
            if version < SCHEMA_VERSION:
                print(
                    f"⚠️  数据文件 schema v{version} 与当前 v{SCHEMA_VERSION} 不兼容"
                    "（区块哈希口径已变更，旧链无法通过校验），将归档后重建。"
                )
                reason = f"legacy-v{version}"
            else:
                print(
                    f"⚠️  数据文件 schema v{version} 高于本程序支持的 v{SCHEMA_VERSION}，"
                    "请升级程序；将归档后重建。"
                )
                reason = f"future-v{version}"
            if archive_incompatible:
                cls._archive(path, reason)
            return None

        try:
            instance = cls._from_dict(payload)
        except (KeyError, TypeError, ValueError) as error:
            print(f"⚠️  区块链文件结构异常，将创建新的区块链: {error}")
            if archive_incompatible:
                cls._archive(path, "invalid")
            return None

        print(f"✅ 区块链已从本地加载: {filepath}（{len(instance.chain)} 个区块）")
        return instance

    @staticmethod
    def _archive(path: Path, reason: str) -> None:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = path.with_name(f"{path.stem}.{reason}-{stamp}.bak")
        try:
            path.replace(backup)
            print(f"📦 旧数据已归档: {backup.name}")
        except OSError as error:  # pragma: no cover - 权限等异常
            print(f"⚠️  归档旧数据失败: {error}")

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return (
            f"Blockchain(blocks={len(self.chain)}, "
            f"pending={len(self.pending_transactions)}, difficulty={self.difficulty})"
        )
