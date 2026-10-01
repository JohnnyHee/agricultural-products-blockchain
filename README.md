# 🔗 农产品供应链区块链溯源系统

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue" alt="Python">
  <img src="https://img.shields.io/badge/Streamlit-1.36%2B-red" alt="Streamlit">
  <img src="https://img.shields.io/badge/SHA--256-PoW-brightgreen" alt="SHA-256 PoW">
  <img src="https://img.shields.io/badge/Merkle-Proof-success" alt="Merkle Proof">
  <img src="https://img.shields.io/badge/测试-112%20passed-brightgreen" alt="tests">
</p>

基于区块链的 **农产品供应链溯源系统**，覆盖 **生产 → 加工 → 物流 → 销售** 全链路的数据上链与追溯，
用 SHA-256 + 工作量证明 + Merkle 树保证"上链即不可篡改"，并内置 **篡改实验台** 让不可篡改性可以被当场验证。

---

## 📋 目录

- [项目亮点](#-项目亮点)
- [快速开始](#-快速开始)
- [功能页面](#-功能页面)
- [项目结构](#-项目结构)
- [核心机制](#-核心机制)
- [领域层：温控与保质期](#-领域层温控与保质期)
- [演示数据](#-演示数据)
- [API 参考](#-api-参考)
- [测试](#-测试)
- [关于数据文件](#-关于数据文件)
- [修复记录](#-修复记录)

---

## ✨ 项目亮点

| 亮点 | 说明 |
|------|------|
| 🔐 **真正可检出的篡改** | `tx_id` 由交易内容实时计算、区块哈希提交 Merkle 根，改任何一个字符都会让整条链校验失败 |
| 🌳 **Merkle 树 + 存在性证明** | 不用下载整条链，仅凭 `O(log n)` 个兄弟哈希即可证明某笔交易属于某个区块 |
| ⛏️ **创世区块同样挖矿** | 创世区块满足自身难度目标，`is_chain_valid()` 从 block #0 开始校验 |
| 📈 **可调难度 + 自动调节** | 目标出块 3 秒，每 3 块按实际出块速度调整一次难度（限定 2~5） |
| 🧊 **冷链温控核验** | 解析 `0~4°C` / `5-10°C` / `-18--2℃` 等写法，逐点比对采样温度并列出超限值 |
| ⏰ **保质期四级预警** | 正常 / 临期 / 紧急 / 已过期，按自然日计算，演示数据覆盖全部级别 |
| 📜 **可下载溯源证书** | 一键导出自包含 HTML（内联样式、无外部依赖），可离线查看或打印为 PDF |
| 🧪 **篡改实验台** | 现场改数据 → 看链失效 → 一键恢复；还能"以攻击者身份重挖本块"，直观展示为什么改一块要重算后面所有块 |
| 💾 **原子写入 + schema 版本** | `*.tmp` + `fsync` + `os.replace`；版本不匹配/文件损坏自动归档为 `*.bak` 而非崩溃 |
| ✅ **112 个测试** | 每个修复过的历史缺陷都有一条对应的回归测试；另有一组无头 UI 冒烟测试逐个页面真实渲染 |

---

## 🚀 快速开始

### 环境要求

- Python **3.10+**（使用 `dict` 合并、`set` 类型标注等特性）
- 依赖见 `requirements.txt`：streamlit / pandas / plotly

### 安装与运行

```bash
pip install -r requirements.txt
streamlit run app.py
```

浏览器会自动打开 `http://localhost:8501`。**首次启动会自动生成一条含演示数据的区块链**（约 1~2 秒挖矿），无需任何额外初始化。

> 💡 如果 `streamlit` 命令不在 PATH 中，可以用 `python -m streamlit run app.py`。

### 建议体验路径

1. **📊 总览看板** — 先看链的整体面貌与各区块构成
2. **🔍 产品溯源** — 挑一个产品，看四段环节时间线 + 冷链核验 + **Merkle 存在性证明**
3. **🛡️ 链验证与篡改实验** — 亲手改掉一条记录，看校验立刻失败；再点"攻击者重挖本块"体会代价
4. **➕ 添加交易 → ⛏️ 挖矿中心** — 自己录入一笔数据并打包上链
5. **📈 数据分析** — 环节分布、上链完整度、在途温度曲线、挖矿效率

---

## 🖥️ 功能页面

侧边栏共 **10 个页面**：

| 页面 | 内容 |
|------|------|
| 📊 **总览看板** | 区块数/交易数/参与方/难度等指标、各区块交易构成堆叠图、产品类别环形图、最近挖矿记录 |
| 🔍 **产品溯源** | 四段环节卡片时间线、冷链温控核验（含允许区间折线）、保质期预警、溯源证书下载、Merkle 存在性证明 |
| 🧊 **冷链与保质期** | 冷链合规率、多产品温度曲线对比、按紧急程度排序的保质期预警表 |
| ➕ **添加交易** | 按交易类型动态生成表单；必填/可选分区；参与方下拉自动补全名称与编号；待处理池一览 |
| ⛏️ **挖矿中心** | 难度调节、自动调难度开关、挖矿进度条、区块哈希/前哈希/Merkle 根展示、挖矿历史与耗时图 |
| 🧱 **区块浏览器** | 全链表格、单区块详情、可复算的哈希载荷、区块内交易与各自的 Merkle 证明 |
| 🛡️ **链验证与篡改实验** | 逐块审计表（哈希/链接/PoW/Merkle/交易合法性）、篡改前后对照、快照恢复、"攻击者重挖"演示 |
| 🏢 **参与方管理** | 参与方表与角色分布、新增/移除参与方 |
| 📈 **数据分析** | 环节分布、产品上链完整度、在途温度曲线、挖矿效率双轴图、全量交易明细 |
| ⚙️ **链管理**（侧边栏折叠区） | 保存 / 重新加载 / 重置为空链 / 重置为演示数据 |

---

## 📁 项目结构

```
agricultural-products-blockchain-main/
├── app.py                    # Streamlit 前端（主入口，10 个页面）
├── blockchain.py             # 区块链核心：Transaction / Block / Blockchain / Merkle
├── supply_chain.py           # 业务领域层：字段标签、演示数据、冷链与保质期规则、溯源证书
├── requirements.txt          # 依赖
├── .gitignore
├── README.md
├── tests/
│   ├── test_app_smoke.py     # 无头 UI 冒烟测试：逐个页面真实渲染并断言无异常
│   ├── test_blockchain.py    # 核心机制回归测试（含历史缺陷回归）
│   └── test_supply_chain.py  # 领域层回归测试
└── data/                     # 运行期生成的链数据（已 gitignore，可安全删除）
    └── blockchain.json
```

### 三层职责划分

| 层 | 文件 | 职责 |
|----|------|------|
| **界面层** | `app.py` | 页面编排、表单、图表、下载；**不含**任何哈希/挖矿逻辑 |
| **机制层** | `blockchain.py` | 哈希口径、PoW、Merkle、索引、校验、持久化；**不含**任何农业业务语义 |
| **领域层** | `supply_chain.py` | 中文标签与单位、演示数据、冷链/保质期规则、溯源证书 HTML；**只依赖**机制层的公开接口 |

这样分层的好处：机制层的正确性可以用纯逻辑测试覆盖（不启动 UI），业务规则改动也不会碰到哈希口径。

---

## 🔧 核心机制

### 哈希口径（篡改可检出的关键）

```python
tx_id      = sha256(canonical_json({"tx_type", "data", "timestamp"}))   # 内容 ⇒ ID，实时计算
merkle_root = merkle([tx.tx_id for tx in block.transactions])           # 交易集合 ⇒ 一个根
block.hash  = sha256(canonical_json({                                   # 根进区块哈希
    "index", "timestamp", "previous_hash", "nonce", "difficulty",
    "merkle_root", "tx_count",
}))
```

因为 `tx_id` 是**属性**而不是构造时缓存的值，改一笔交易的任何字段都会连锁导致：

```
改 data → tx_id 变 → merkle_root 变 → block.hash 变 ≠ 已存哈希 → 校验失败
```

### 校验都检查什么

`is_chain_valid()` 从 **block #0** 开始逐块检查：

1. 区块自身哈希与内容一致（内容未改）
2. `previous_hash` 等于前一块的 `hash`（链未断）
3. 区块哈希满足**该块自己的** `difficulty` 个前导零（PoW 未降级）
4. 区块声明的 Merkle 根与实际交易的 Merkle 根一致
5. 每笔交易通过结构校验

`audit_chain()` 则把上述 5 项拆成表格逐块展示，方便直接看到"是哪一项、哪个块"出问题。

### Merkle 存在性证明

```python
proof = block.proof_for(tx_index)          # [(兄弟哈希, 是否在右侧), ...]
verify_merkle_proof(tx_id, proof, block.merkle_root)  # True / False
```

证明长度是 `O(log n)`，奇数节点时复制最后一个（比特币的做法），空区块根为 `sha256("EMPTY_BLOCK")`。

### 持久化

- **原子写**：先写 `*.tmp` → `flush` → `os.fsync` → `os.replace`，断电不会留下半个文件
- **schema 版本**：文件里带 `schema_version`；版本不匹配（过旧或过新）会归档为
  `*.legacy-v<版本>-<时间戳>.bak` / `*.future-v<版本>-*.bak` 并新建链，而不是硬加载出错
- **损坏自愈**：JSON 解析失败 → `*.corrupt-*.bak`；结构异常 → `*.invalid-*.bak`
- **重复交易**：`add_transaction` 拒绝 `tx_id` 已存在的交易

---

## 🌡️ 领域层：温控与保质期

### `parse_temperature_range(text)`

难点是 `-` 既是区间分隔符、又是负号（`5-10` vs `-18--2`）。实现策略是**优先按无歧义分隔符切分**，没有时才用正则整体匹配：

| 输入 | 结果 |
|------|------|
| `"0~4°C"` / `"0-4℃"` / `"0—4°C"` / `"18到22°C"` | `(0.0, 4.0)` 等 |
| `"5-10°C"` | `(5.0, 10.0)` |
| `"-18--2℃"` | `(-18.0, -2.0)` |
| `"常温"` / `"低温"` / `"0°C"` / `""` / `None` | `None`（无法判定） |

### `cold_chain_report(transaction)`

**无论是否适用都返回同一组键**（不适用时为 `None`），调用方不需要按分支处理：

```python
{"applicable", "compliant", "range", "range_text", "low", "high",
 "readings", "min", "max", "average", "violations", "note"}
```

`compliant` 有 **三种** 取值：`True` 全部达标 / `False` 有超限采样 / `None` 无法判定（无采样或无温控范围）。
采样值兼容字符串（`"2.5"`、`"3°C"`）。

### `expiry_status(expiry_date)`

按**自然日**相减（不用时刻，否则"明天到期"会被算成仅剩 1 天）：

| 剩余天数 | 等级 | 文案 | 颜色 |
|---------|------|------|------|
| < 0 | `expired` | 已过期 N 天 | 🔴 |
| = 0 | `critical` | 今日到期 | 🔴 |
| 1 ~ 3 | `critical` | 仅剩 N 天 | 🔴 |
| 4 ~ 14 | `warning` | 剩余 N 天 | 🟠 |
| > 14 | `ok` | 剩余 N 天 | 🟢 |

---

## 🌾 演示数据

首次运行会自动生成 **4 个产品 × 4 个环节 = 16 笔交易**（每个产品恰好一个区块），外加创世区块。
所有日期都是**相对今天**生成的，因此无论如何打开，都能看到"正常 / 临期 / 紧急 / 已过期"四种保质期状态，以及一例冷链温度超限告警。

| 产品 | 类别 | 产地 | 保质期演示 |
|------|------|------|-----------|
| 🍎 有机红富士苹果 | 水果 | 陕西省延安市洛川县 | 正常（剩余约 45 天） |
| 🍚 五常有机大米 | 粮食 | 黑龙江省哈尔滨市五常市 | 临期（剩余约 8 天） |
| 🍵 西湖龙井茶叶 | 茶叶 | 浙江省杭州市西湖区 | 紧急（剩余约 2 天） |
| 🍅 有机圣女果 | 蔬菜 | 山东省潍坊市寿光市 | 已过期，且**冷链温度超限 2 次** |

**参与方 11 个**：

| 角色 | 参与方 |
|------|--------|
| 🌾 生产者 | 阳光生态农场、绿源有机农场、西湖龙井茶园、寿光蔬菜合作社 |
| 🏭 加工商 | 鲜品加工厂、绿农食品加工公司 |
| 🚚 物流商 | 顺达冷链物流、京东冷链运输 |
| 🏪 销售商 | 盒马鲜生、永辉超市 |
| 🔬 监管机构 | 省农产品质量安全检测中心 |

---

## 📖 API 参考

### `blockchain.py`

```python
Transaction(tx_type, data, timestamp=None)
  .tx_id -> str                    # 由内容实时计算（属性）
  .product_id / .is_genesis / .tx_type_label / .timestamp_str
  .validate() -> (bool, [问题])     .missing_fields() -> [字段]
  .to_dict() / Transaction.from_dict(d)

Block(index, transactions, previous_hash, nonce=0, timestamp=None, difficulty=4)
  .hash / .merkle_root / .tx_ids   .mine(difficulty=None) -> (nonce, attempts)
  .satisfies_pow() -> bool         .proof_for(tx_index) -> [(哈希, 方向)]
  .to_dict() / Block.from_dict(d)

Blockchain(difficulty=4, auto_adjust=False)
  # 类常量：DIFFICULTY=4  MIN_DIFFICULTY=2  MAX_DIFFICULTY=5
  #         TARGET_BLOCK_SECONDS=3.0  ADJUST_EVERY=3
  .add_transaction(tx, *, validate=True) -> tx_id      # 重复/非法 → ValueError
  .mine_pending_transactions(miner_address="system") -> Block
  .trace_product(product_id) -> [记录]                 # 每笔恰好一条，按时间排序
  .all_transactions(*, include_genesis=False) -> [记录]
  .get_product_list() / .get_block(index) / .find_transaction(tx_id)
  .is_chain_valid() -> (bool, 说明)   .audit_chain() -> [逐块审计]
  .verify_transaction_inclusion(tx_id, block_index) -> (bool, 说明)
  .tamper_transaction(block_index, position, field, new_value) -> {before, after}
  .register_participant(id, name, role, extra=None) / .remove_participant(id)
  .get_chain_stats() -> {block_count, total_transactions, chain_transactions, ...}
  .save_to_file(path)  |  Blockchain.load_from_file(path, *, archive_incompatible=True)
```

模块级工具：

| 函数 | 用途 |
|------|------|
| `canonical_json(obj)` / `sha256_hex(text)` | 稳定序列化（键排序、中文不转义）与哈希 |
| `compute_merkle_root(tx_ids)` | 计算 Merkle 根 |
| `merkle_proof(tx_ids, index)` / `verify_merkle_proof(tx_id, proof, root)` | 生成/验证存在性证明 |
| `to_jsonable(value)` | 递归归一化 numpy 标量、datetime，保证哈希稳定 |
| `is_dir_writable(path)` / `resolve_data_dir(preferred=None)` | 数据目录探测与回退 |

### `supply_chain.py`

| 名称 | 用途 |
|------|------|
| `FIELD_LABELS` / `label_for(field)` | 约 45 个字段的中文标签与单位 |
| `ROLES` / `ROLE_COLORS` / `STAGE_ICONS` / `STAGE_COLORS` / `stage_icon(tx_type)` | 展示元数据 |
| `SEED_PRODUCTS` / `SEED_PARTICIPANTS` / `product_id_of(product)` | 演示数据 |
| `merged_stage(product, tx_type)` | 取出某环节数据并补上产品身份字段 |
| `build_seed_transactions()` / `seed_blockchain(miner="system")` | 生成演示链 |
| `parse_temperature_range(text)` / `cold_chain_report(tx)` | 冷链温控规则 |
| `expiry_status(expiry_date, reference=None)` | 保质期预警分级 |
| `build_trace_html(blockchain, product_id, records)` | 生成自包含溯源证书 HTML（所有值经 `html.escape`） |

---

## ✅ 测试

```bash
python -m unittest discover -s tests -v
```

当前：**112 个测试全部通过**（`test_blockchain.py` 62 个 + `test_supply_chain.py` 39 个 + `test_app_smoke.py` 11 个）。
覆盖内容包括：

- 哈希口径：`tx_id` 随内容变化、键序无关、中文不转义、`timestamp=0` 不被当成缺省值、numpy 标量归一化
- Merkle：1/2/3/5/8/17 个叶子的每一片都能通过证明；伪造叶子、篡改兄弟、错误根一律拒绝；根对顺序敏感
- 区块：改载荷则哈希变、`mine()` 满足前导零
- 链：创世区块真的挖过矿、篡改（含篡改创世块）被检出、链断裂单独报错、**降难度重算哈希被检出**、重复交易被拒、`trace_product` 每笔只返回一次
- 持久化：往返一致、不留 `.tmp`、覆写安全、损坏/v1/未来版本分别归档为 `*.corrupt-*` / `*.legacy-v1-*` / `*.future-*`
- 领域层：温控区间各种写法、`compliant` 三态、保质期四级分界（含"今日到期"）、演示数据覆盖全部预警等级、溯源证书自包含且转义
- **UI 冒烟**：用 `AppTest` 真实渲染全部 9 个页面并断言零异常；断言侧边栏页面清单、演示链规模、表单/挖矿/篡改实验的控件存在
- **编码体检**：源码中不得出现 `U+FFFD` 或转义的中文序列

> `test_app_smoke.py` 会把数据目录通过环境变量 `AGRI_CHAIN_DATA_DIR` 指向一个临时目录，
> 因此跑测试不会污染你自己的 `data/blockchain.json`。

---

## 💾 关于数据文件

链数据的位置由 `resolve_data_dir()` 按下面的顺序探测，**取第一个确实可写**的目录：

1. 显式参数
2. 环境变量 `AGRI_CHAIN_DATA_DIR`
3. `<项目>/blockchain_data`
4. `<项目>/data`
5. `~/.agri_blockchain`
6. 系统临时目录（最后兜底）

之所以要探测而不是写死路径：项目可能被放进只读目录、被挂载为只读卷，或在受限沙箱里运行 ——
写死路径会让程序在这些环境下直接崩溃。数据目录当前值会显示在侧边栏的"链管理"折叠区里。

**想从头开始？** 直接删掉数据目录里的 `blockchain.json` 并刷新页面；也可以用侧边栏的
"重置为演示数据"按钮。任何被判定为不兼容的文件都会自动改名成 `*.bak` 保留，不会丢数据。

---

## 🩹 修复记录

这一版修复了早期版本中若干**实质性**缺陷。其中三条直接动摇了"区块链不可篡改"的立论，值得单独说明：

### 1. 篡改无法被检出（最严重）

早期版本的 `compute_hash` 只用**缓存的** `tx_id` 参与哈希，而 `tx_id` 在 `Transaction.__init__`
里算完就固定了 —— 修改 `tx.data` 不会改变任何哈希。实测把区块 #1 首笔交易的 `product_name`
改成 `[已篡改] 假冒产品` 之后，`is_chain_valid()` 依然返回 `(True, '区块链完整有效 ✅')`，
前端的"篡改模拟"功能因此完全失效。

**现在**：`tx_id` 是属性、`merkle_root` 是活属性、`block.hash` 提交 Merkle 根，改一个字符即被检出。
（回归测试：`TestTransaction.test_tx_id_reacts_to_data_change`、`TestBlockchain.test_tampering_is_detected`）

### 2. `trace_product` 把记录重复了 4 倍

`mine_pending_transactions` 对区块内**每笔**交易都执行一次
`product_registry[product_id].append(block.index)`。一个含 4 笔同产品交易的区块得到下标列表
`[1, 1, 1, 1]`，而 `trace_product` 又对列表里每个下标遍历区块内**全部**交易 ⇒ 4 × 4 = **16 条记录**
（应为 4 条）。

**现在**：索引改为精确的 `(区块下标, 交易下标)` 并去重，实测 4 笔交易返回 4 条。
（回归测试：`TestBlockchain.test_trace_product_returns_each_record_once`）

### 3. 创世区块未挖矿，且校验跳过了它

创世区块的哈希 `bc6d59e7…` 并不以 `0000` 开头，但 `is_chain_valid` 从 `i = 1` 开始循环，
恰好掩盖了这个问题；`verify_chain` 也用链级难度而不是每块自己的难度。

**现在**：创世区块按 `GENESIS_DIFFICULTY = 4` 真正挖矿，校验从 `index 0` 开始并使用每块自身的 `difficulty`，
降难度重算哈希也会被检出。

### 其他修复

| 问题 | 处理 |
|------|------|
| `app.py` 编码损坏：201 个 U+FFFD 分布在 151 行，字符串闭合引号被吞，文件无法解析 | 中文原文已永久丢失，整文件重写 |
| 演示数据产地错误（苹果与茶叶都写成"黑龙江省五常市"）| 改为洛川县 / 五常市 / 西湖区 / 寿光市 |
| 演示数据日期硬编码在 2025 年，全部显示"已过期 268 天" | 改为相对今天生成，覆盖四种预警级别 |
| `st.components.v1.html` 已废弃，会刷警告 | 全部改用 `st.html` |
| Streamlit 1.61 中 `use_container_width` 已弃用、`st.components.v1.html` 已废弃 | 统一改用 `width="stretch"` 与 `st.html` |
| `parse_temperature_range("5-10°C")` 返回 `(-10.0, 5.0)` | 改为"分隔符优先"解析，并规范化 低≤高 |
| `cold_chain_report` 不适用分支缺 `min`/`max`/`average`，页面抛 `KeyError` | 两种分支返回同一组键 |
| `expiry_status` 按时刻相减，"明天到期"显示"仅剩 1 天" | 改按自然日相减，新增"今日到期" |
| `get_chain_stats().avg_block_seconds` 把固定时间戳的创世块算进间隔，得到 22717183 秒 | 从第 3 块起算间隔 |
| 参与方额外字段塞在 `extra` 子字典里，界面按平铺读取 ⇒ 永远显示空 | 改为平铺存储并补 `registered_at` |
| 创世区块那笔合成交易被当成真实业务记录，交易总数虚增 1、环节分布多一条 | 新增 `Transaction.is_genesis`，统计与列表默认排除（`chain_transactions` 保留全量） |
| `is_dir_writable` 只接受 `Path`，传 `str` 会 `AttributeError` | 内部先 `Path(path)` 归一化 |
| `save_to_file` 直接覆写，写入中断会毁掉数据 | `*.tmp` + `fsync` + `os.replace` 原子写 |
| 数据文件无版本标记，schema 变更后旧文件硬加载出错 | 加 `schema_version`；不兼容文件自动归档为 `*.bak` |
| 重复提交同一笔交易无人拦截 | `add_transaction` 校验并拒绝重复 `tx_id` |
| 无 `requirements.txt`，README 却要求 `pip install -r requirements.txt` | 已补齐；另加 `.gitignore` 与测试目录 |
| README 项目结构写成 `blockchained_FL/`，与实际不符 | 本文件已按实际结构重写 |

---

## 🛠️ 技术栈

| 技术 | 用途 |
|------|------|
| **Python 3.10+** | 开发语言 |
| **Streamlit** | 前端界面框架 |
| **SHA-256** | 交易 ID、Merkle 树、区块哈希 |
| **PoW（前导零）** | 工作量证明共识，难度可调 |
| **Merkle 树** | 交易集合摘要与存在性证明 |
| **Plotly** | 交互式图表 |
| **pandas** | 表格数据处理 |
| **JSON** | 链数据持久化（原子写 + schema 版本） |
| **unittest** | 单元测试（无第三方测试依赖） |

---

## 📄 许可证

本项目仅供学习和研究使用。

> ⚠️ **免责声明**：这是一个教学/演示性质的单节点链，不含 P2P 网络、共识竞争与数字签名，
> 因此它演示的是"哈希链 + PoW"的**数据不可篡改**特性，不等同于生产级联盟链/公链方案。

---

<p align="center">
  <sub>🌾 从田间到餐桌，用区块链守护食品安全</sub>
</p>
