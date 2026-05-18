"""
区块链核心模块 - 农产品供应链溯源系统
实现了完整的区块链数据结构、工作量证明(PoW)、交易管理与链验证
"""

import hashlib
import json
import time
from datetime import datetime
from typing import List, Dict, Optional, Any
from pathlib import Path


class Transaction:
    """供应链溯源交易"""

    TRANSACTION_TYPES = {
        "production": "生产记录",
        "processing": "加工记录",
        "logistics": "物流记录",
        "sale": "销售记录",
    }

    def __init__(
        self,
        tx_type: str,
        data: Dict[str, Any],
        timestamp: Optional[float] = None,
    ):
        """
        :param tx_type: 交易类型 (production/processing/logistics/sale)
        :param data: 交易数据
        :param timestamp: 时间戳
        """
        if tx_type not in self.TRANSACTION_TYPES:
            raise ValueError(f"无效的交易类型: {tx_type}，可选: {list(self.TRANSACTION_TYPES.keys())}")

        self.tx_type = tx_type
        self.data = data
        self.timestamp = timestamp or time.time()
        self.tx_id = self._calculate_hash()

    def _calculate_hash(self) -> str:
        """计算交易哈希作为唯一ID"""
        content = f"{self.tx_type}{json.dumps(self.data, sort_keys=True)}{self.timestamp}"
        return hashlib.sha256(content.encode()).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tx_id": self.tx_id,
            "tx_type": self.tx_type,
            "tx_type_label": self.TRANSACTION_TYPES[self.tx_type],
            "data": self.data,
            "timestamp": self.timestamp,
            "timestamp_str": datetime.fromtimestamp(self.timestamp).strftime("%Y-%m-%d %H:%M:%S"),
        }

    def __repr__(self) -> str:
        return f"Transaction({self.tx_id[:12]}... | {self.TRANSACTION_TYPES[self.tx_type]})"


class Block:
    """区块"""

    def __init__(
        self,
        index: int,
        transactions: List[Transaction],
        previous_hash: str,
        nonce: int = 0,
        timestamp: Optional[float] = None,
    ):
        self.index = index
        self.transactions = transactions
        self.timestamp = timestamp or time.time()
        self.previous_hash = previous_hash
        self.nonce = nonce
        self.hash = self.calculate_hash()

    def calculate_hash(self) -> str:
        """计算区块哈希"""
        content = f"{self.index}{self.timestamp}{self.previous_hash}{self.nonce}"
        for tx in self.transactions:
            content += tx.tx_id
        return hashlib.sha256(content.encode()).hexdigest()

    def mine_block(self, difficulty: int) -> int:
        """工作量证明挖矿"""
        target = "0" * difficulty
        while self.hash[:difficulty] != target:
            self.nonce += 1
            self.hash = self.calculate_hash()
        return self.nonce

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "timestamp": self.timestamp,
            "timestamp_str": datetime.fromtimestamp(self.timestamp).strftime("%Y-%m-%d %H:%M:%S"),
            "transactions": [tx.to_dict() for tx in self.transactions],
            "previous_hash": self.previous_hash,
            "hash": self.hash,
            "nonce": self.nonce,
            "tx_count": len(self.transactions),
        }

    def __repr__(self) -> str:
        return f"Block #{self.index} | Hash: {self.hash[:12]}... | Txs: {len(self.transactions)}"


class Blockchain:
    """区块链 - 农产品供应链溯源系统"""

    DIFFICULTY = 4  # 挖矿难度

    def __init__(self):
        self.chain: List[Block] = []
        self.pending_transactions: List[Transaction] = []
        self.difficulty = self.DIFFICULTY
        # 产品注册表: product_id -> [区块索引列表]
        self.product_registry: Dict[str, List[int]] = {}
        # 参与方注册表
        self.participants: Dict[str, Dict] = {}
        self._create_genesis_block()

    def _create_genesis_block(self):
        """创建创世区块"""
        genesis_tx = Transaction(
            "production",
            {
                "product_id": "GENESIS",
                "product_name": "创世区块",
                "producer": "区块链系统",
                "origin": "系统初始化",
                "notes": "农产品供应链溯源区块链的起源区块",
            },
            timestamp=1700000000,
        )
        genesis_block = Block(
            index=0,
            transactions=[genesis_tx],
            previous_hash="0" * 64,
            timestamp=1700000000,
        )
        genesis_block.hash = genesis_block.calculate_hash()
        self.chain.append(genesis_block)

    def add_transaction(self, transaction: Transaction) -> int:
        """添加交易到待处理池"""
        self.pending_transactions.append(transaction)
        return len(self.pending_transactions)

    def mine_pending_transactions(self, miner_address: str = "system") -> Block:
        """挖矿打包待处理交易"""
        if not self.pending_transactions:
            raise ValueError("没有待处理的交易")

        new_block = Block(
            index=len(self.chain),
            transactions=self.pending_transactions[:],
            previous_hash=self.chain[-1].hash,
        )
        new_block.mine_block(self.difficulty)

        # 更新产品注册表
        for tx in new_block.transactions:
            product_id = tx.data.get("product_id")
            if product_id:
                if product_id not in self.product_registry:
                    self.product_registry[product_id] = []
                self.product_registry[product_id].append(new_block.index)

        self.chain.append(new_block)
        self.pending_transactions = []
        return new_block

    def trace_product(self, product_id: str) -> List[Dict[str, Any]]:
        """
        产品追溯 - 按产品ID追溯整个供应链生命周期
        返回该产品的所有交易记录（按时间排序）
        """
        if product_id not in self.product_registry:
            return []

        trace = []
        for block_idx in self.product_registry[product_id]:
            block = self.chain[block_idx]
            for tx in block.transactions:
                if tx.data.get("product_id") == product_id:
                    trace.append({
                        "block_index": block.index,
                        "block_hash": block.hash,
                        "block_time": datetime.fromtimestamp(block.timestamp).strftime("%Y-%m-%d %H:%M:%S"),
                        **tx.to_dict(),
                    })

        # 按时间排序
        trace.sort(key=lambda x: x["timestamp"])
        return trace

    def register_participant(
        self, participant_id: str, name: str, role: str, extra: Optional[Dict] = None
    ):
        """注册供应链参与方"""
        self.participants[participant_id] = {
            "name": name,
            "role": role,
            "extra": extra or {},
            "registered_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    def is_chain_valid(self) -> tuple[bool, str]:
        """
        验证区块链完整性
        返回 (是否有效, 详细信息)
        """
        for i in range(1, len(self.chain)):
            current = self.chain[i]
            previous = self.chain[i - 1]

            # 验证当前区块哈希
            if current.hash != current.calculate_hash():
                return False, f"区块 #{current.index} 的哈希不一致"

            # 验证链式链接
            if current.previous_hash != previous.hash:
                return False, f"区块 #{current.index} 的前置哈希不匹配"

            # 验证工作量证明
            if current.hash[: self.difficulty] != "0" * self.difficulty:
                return False, f"区块 #{current.index} 的工作量证明无效"

        return True, "区块链完整有效 ✅"

    def get_chain_stats(self) -> Dict[str, Any]:
        """获取区块链统计信息"""
        total_tx = sum(len(b.transactions) for b in self.chain)
        return {
            "block_count": len(self.chain),
            "total_transactions": total_tx,
            "pending_transactions": len(self.pending_transactions),
            "difficulty": self.difficulty,
            "unique_products": len(self.product_registry),
            "participants": len(self.participants),
            "last_block_time": (
                datetime.fromtimestamp(self.chain[-1].timestamp).strftime("%Y-%m-%d %H:%M:%S") if self.chain else "N/A"
            ),
            "chain_size_kb": len(json.dumps([b.to_dict() for b in self.chain])) / 1024,
        }

    def to_dict(self) -> List[Dict[str, Any]]:
        return [b.to_dict() for b in self.chain]

    # ── 本地持久化 ──────────────────────────────────────────
    DATA_DIR = "blockchain_data"
    DATA_FILE = "blockchain_backup.json"

    def _to_dict_full(self) -> Dict[str, Any]:
        """完整的区块链状态序列化（含链、待处理交易、注册表等）"""
        return {
            "chain": self.to_dict(),
            "pending_transactions": [tx.to_dict() for tx in self.pending_transactions],
            "product_registry": self.product_registry,
            "participants": self.participants,
            "difficulty": self.difficulty,
        }

    @classmethod
    def _from_dict(cls, data: Dict[str, Any]) -> "Blockchain":
        """从字典重建区块链实例"""
        bc = cls.__new__(cls)
        bc.difficulty = data.get("difficulty", cls.DIFFICULTY)
        bc.product_registry = data.get("product_registry", {})
        bc.participants = data.get("participants", {})
        bc.pending_transactions = []
        bc.chain = []

        # 重建区块
        for block_data in data.get("chain", []):
            transactions = [
                Transaction(
                    tx_type=tx["tx_type"],
                    data=tx["data"],
                    timestamp=tx["timestamp"],
                )
                for tx in block_data["transactions"]
            ]
            block = Block(
                index=block_data["index"],
                transactions=transactions,
                previous_hash=block_data["previous_hash"],
                nonce=block_data["nonce"],
                timestamp=block_data["timestamp"],
            )
            block.hash = block_data["hash"]
            bc.chain.append(block)

        # 重建待处理交易
        for tx_data in data.get("pending_transactions", []):
            tx = Transaction(
                tx_type=tx_data["tx_type"],
                data=tx_data["data"],
                timestamp=tx_data["timestamp"],
            )
            bc.pending_transactions.append(tx)

        return bc

    @classmethod
    def load_from_file(cls, filepath: str) -> Optional["Blockchain"]:
        """从本地JSON文件加载区块链，文件不存在时返回 None"""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            bc = cls._from_dict(data)
            print(f"✅ 区块链已从本地加载: {filepath}")
            return bc
        except FileNotFoundError:
            print(f"ℹ️  未找到本地区块链文件，将创建新的区块链: {filepath}")
            return None
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            print(f"⚠️  区块链文件损坏，将创建新的区块链: {e}")
            return None

    def save_to_file(self, filepath: str):
        """将区块链完整状态保存到本地JSON文件"""
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self._to_dict_full(), f, ensure_ascii=False, indent=2)
        print(f"💾 区块链已保存到本地: {filepath}")
