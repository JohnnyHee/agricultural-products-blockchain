"""
Streamlit 区块链系统 - 农产品供应链溯源系统
提供直观的界面进行区块链浏览、交易创建、产品追溯与链验�?
"""

import streamlit as st
import pandas as pd
import time
import json
import random
from datetime import datetime
from pathlib import Path
from blockchain import Blockchain, Transaction

# ─── 数据持久化配�?─────────────────────────────────────────
DATA_DIR = Path(__file__).parent / "blockchain_data"
DATA_FILE = DATA_DIR / "blockchain_backup.json"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ─── 页面配置 ───────────────────────────────────────────────
st.set_page_config(
    page_title="区块链溯源系�?系统",
    page_icon="🔗",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── 初始�?Session State ───────────────────────────────────
if "product_filter" not in st.session_state:
    st.session_state.product_filter = "全部"


def _seed_init_data(bc: Blockchain):
    """生成演示用的供应链数�?""
    init_products = [
        {
            "product_id": "ORG-APPLE-2025-001",
            "product_name": "有机红富士苹�?,
            "category": "水果",
        },
        {
            "product_id": "ORG-RICE-2025-001",
            "product_name": "五常有机大米",
            "category": "粮食",
        },
        {
            "product_id": "ORG-TEA-2025-001",
            "product_name": "西湖龙井茶叶",
            "category": "茶叶",
        },
    ]

    for prod in init_products:
        pid = prod["product_id"]

        # 1. 生产记录
        tx1 = Transaction("production", {
            "product_id": pid,
            "product_name": prod["product_name"],
            "category": prod["category"],
            "producer": "阳光生态农�?,
            "producer_id": "farm_001",
            "origin": "黑龙江省五常�?,
            "planting_date": "2025-03-15",
            "harvest_date": "2025-05-10",
            "batch_number": f"BATCH-{random.randint(1000,9999)}",
            "quality_grade": "特级",
            "certification": "有机认证 GB/T 19630",
            "notes": "采用生态种植方式，无农药残�?,
        })
        bc.add_transaction(tx1)

        # 2. 加工记录
        tx2 = Transaction("processing", {
            "product_id": pid,
            "product_name": prod["product_name"],
            "processor": "鲜品加工�?,
            "processor_id": "processor_001",
            "process_type": "分拣·清洗·包装",
            "processing_date": "2025-05-12",
            "expiry_date": "2025-08-10",
            "facility": "A区无菌加工车�?,
            "batch_number": f"PROC-{random.randint(1000,9999)}",
            "supervisor": "李明",
            "quality_check": "已通过食品安全检�?,
        })
        bc.add_transaction(tx2)

        # 3. 物流记录
        tx3 = Transaction("logistics", {
            "product_id": pid,
            "product_name": prod["product_name"],
            "logistics_provider": "顺达冷链物流",
            "logistics_id": "logistics_001",
            "transport_mode": "冷链运输 (0-4°C)",
            "departure": "黑龙江省哈尔滨市",
            "destination": "北京市朝阳区",
            "shipment_date": "2025-05-13",
            "estimated_arrival": "2025-05-15",
            "tracking_number": f"SF-{random.randint(100000,999999)}",
            "temperature_range": "0~4°C",
            "vehicle_number": f"京A·{random.randint(10000,99999)}",
        })
        bc.add_transaction(tx3)

        # 4. 销售记�?
        tx4 = Transaction("sale", {
            "product_id": pid,
            "product_name": prod["product_name"],
            "seller": "盒马鲜生",
            "seller_id": "seller_001",
            "store": "盒马鲜生·北京朝阳�?,
            "shelf_date": "2025-05-16",
            "selling_price": f"{random.randint(20, 150)}�?{['500g','1kg','250g'][random.randint(0,2)]}",
            "stock_quantity": random.randint(500, 5000),
            "promotion": "新品上市",
        })
        bc.add_transaction(tx4)

        # 挖矿
        bc.mine_pending_transactions()


# ─── 区块链初始化（优先从本地加载）────────────────────────
if "blockchain" not in st.session_state:
    # 尝试从本地文件加�?
    loaded_bc = Blockchain.load_from_file(str(DATA_FILE))

    if loaded_bc is not None:
        bc_init = loaded_bc
        st.toast("📂 已从本地加载区块链数�?, icon="💾")
    else:
        bc_init = Blockchain()
        # 注册默认参与�?
        bc_init.register_participant("farm_001", "阳光生态农�?, "生产�?)
        bc_init.register_participant("farm_002", "绿源有机农场", "生产�?)
        bc_init.register_participant("processor_001", "鲜品加工�?, "加工�?)
        bc_init.register_participant("processor_002", "绿农食品加工公司", "加工�?)
        bc_init.register_participant("logistics_001", "顺达冷链物流", "物流�?)
        bc_init.register_participant("logistics_002", "京东冷链运输", "物流�?)
        bc_init.register_participant("seller_001", "盒马鲜生", "销售商")
        bc_init.register_participant("seller_002", "永辉超市", "销售商")

        # 预生成一些演示数�?
        _seed_init_data(bc_init)
        # 首次创建时保存到本地
        bc_init.save_to_file(str(DATA_FILE))

    st.session_state.blockchain = bc_init
    st.session_state.init_loaded = True


# ─── 工具函数 ───────────────────────────────────────────────
def _save_blockchain():
    """将当前区块链状态保存到本地文件"""
    bc = st.session_state.blockchain
    bc.save_to_file(str(DATA_FILE))


# ─── 侧边�?─────────────────────────────────────────────────
st.sidebar.markdown(
    """
    <div style="text-align:center;padding:1rem 0">
        <h1 style="font-size:2.5rem;margin:0">🔗</h1>
        <h3 style="margin:0.3rem 0">区块链溯源系�?/h3>
        <p style="font-size:0.8rem;color:#888">农产品供应链 系统</p>
    </div>
    """,
    unsafe_allow_html=True,
)

st.sidebar.divider()

page = st.sidebar.radio(
    "功能导航",
    [
        "📊 区块链总览",
        "🔍 产品追溯",
        "�?添加交易",
        "⛏️ 挖矿打包",
        "�?链验�?,
        "👥 参与方管�?,
    ],
    label_visibility="collapsed",
)

st.sidebar.divider()
bc: Blockchain = st.session_state.blockchain
stats = bc.get_chain_stats()

st.sidebar.markdown("### 📊 实时状�?)
col1, col2 = st.sidebar.columns(2)
col1.metric("区块�?, stats["block_count"])
col2.metric("总交易数", stats["total_transactions"])
col1.metric("产品�?, stats["unique_products"])
col2.metric("待处理交�?, stats["pending_transactions"])

st.sidebar.divider()
st.sidebar.caption("💡 本系统模拟了农产品从生产→加工→物流→销售的全链路区块链追溯")

# ─── 数据管理按钮 ──────────────────────────────────────────
st.sidebar.divider()
with st.sidebar.container():
    data_col1, data_col2 = st.columns(2)
    with data_col1:
        if st.button("💾 保存", width='stretch', key="sidebar_save"):
            _save_blockchain()
            st.toast("�?区块链已保存到本�?, icon="💾")
    with data_col2:
        if st.button("🔄 重载", width='stretch', key="sidebar_reload"):
            loaded = Blockchain.load_from_file(str(DATA_FILE))
            if loaded is not None:
                st.session_state.blockchain = loaded
                st.rerun()
            else:
                st.toast("⚠️ 本地无保存数�?, icon="�?)
st.sidebar.caption(f"📁 `{DATA_FILE.name}` ({stats['chain_size_kb']:.1f} KB)")


# ─── 工具函数 ───────────────────────────────────────────────
def get_product_list(bc: Blockchain) -> list:
    """获取所有产品列�?""
    products = set()
    for block in bc.chain:
        for tx in block.transactions:
            pid = tx.data.get("product_id")
            if pid and pid != "GENESIS":
                products.add(pid)
    return sorted(products)


def get_transaction_color(tx_type: str) -> str:
    colors = {
        "production": "#27AE60",
        "processing": "#2980B9",
        "logistics": "#F39C12",
        "sale": "#E74C3C",
    }
    return colors.get(tx_type, "#95A5A6")


def render_tx_card(tx_dict: dict, index: int):
    """渲染单个交易卡片"""
    tx_type = tx_dict["tx_type"]
    color = get_transaction_color(tx_type)
    icon_map = {"production": "🌾", "processing": "🏭", "logistics": "🚚", "sale": "🏪"}

    st.markdown(
        f"""
        <div style="
            border-left: 4px solid {color};
            background: {'#0E2D1A' if tx_type=='production' else '#0D253F' if tx_type=='processing' else '#2D1F0E' if tx_type=='logistics' else '#2D0E0E'};
            padding: 0.8rem 1rem;
            border-radius: 0 8px 8px 0;
            margin-bottom: 0.5rem;
        ">
            <div style="display:flex;justify-content:space-between;align-items:center">
                <span><strong>{icon_map[tx_type]} {tx_dict['tx_type_label']}</strong></span>
                <span style="font-size:0.75rem;color:#888">{tx_dict['timestamp_str']}</span>
            </div>
            <div style="font-size:0.85rem;margin-top:0.3rem">
                <span style="color:#ccc">交易ID:</span> <code style="font-size:0.75rem">{tx_dict['tx_id'][:16]}...</code>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.expander("📋 查看详情", expanded=False):
        data = tx_dict["data"]
        for k, v in data.items():
            label_map = {
                "product_id": "产品ID",
                "product_name": "产品名称",
                "category": "产品类别",
                "producer": "生产�?,
                "producer_id": "生产者ID",
                "origin": "产地",
                "planting_date": "种植日期",
                "harvest_date": "收获日期",
                "batch_number": "批号",
                "quality_grade": "品质等级",
                "certification": "认证信息",
                "processor": "加工�?,
                "processor_id": "加工商ID",
                "process_type": "加工类型",
                "processing_date": "加工日期",
                "expiry_date": "保质期至",
                "facility": "加工设施",
                "supervisor": "负责�?,
                "quality_check": "质检结果",
                "logistics_provider": "物流�?,
                "logistics_id": "物流商ID",
                "transport_mode": "运输方式",
                "departure": "出发�?,
                "destination": "目的�?,
                "shipment_date": "发货日期",
                "estimated_arrival": "预计到达",
                "tracking_number": "运单�?,
                "temperature_range": "温度范围",
                "vehicle_number": "车牌�?,
                "seller": "销售商",
                "seller_id": "销售商ID",
                "store": "销售门�?,
                "shelf_date": "上架日期",
                "selling_price": "售价",
                "stock_quantity": "库存�?,
                "promotion": "促销信息",
            }
            st.text(f"{label_map.get(k, k)}: {v}")


# ══════════════════════════════════════════════════════════�?
# 页面 1: 区块链总览
# ══════════════════════════════════════════════════════════�?
if page == "📊 区块链总览":
    st.title("📊 区块链总览")
    st.markdown("农产品供应链溯源区块链的全局概览，展示所有区块与交易数据�?)

    # 统计卡片
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("🧱 区块总数", stats["block_count"], delta="创世区块 + 已挖区块")
    with c2:
        st.metric("📝 交易总数", stats["total_transactions"])
    with c3:
        st.metric("📦 产品追溯", stats["unique_products"], delta="种产�?)
    with c4:
        st.metric("�?待处理交�?, stats["pending_transactions"])

    # 区块链可视化
    st.subheader("🗺�?区块链结�?)
    st.caption("每个区块包含多笔交易，通过哈希指针链接成不可篡改的链式结构")

    # 区块流水
    for i, block in enumerate(reversed(bc.chain)):
        bd = block.to_dict()
        is_genesis = bd["index"] == 0
        with st.container():
            cols = st.columns([1, 11])
            with cols[0]:
                if is_genesis:
                    st.markdown("#### 🪨")
                else:
                    st.markdown("#### 🧱")

            with cols[1]:
                block_color = "#8B4513" if is_genesis else "#1a6b3c"
                block_label = "🪨 创世区块" if is_genesis else f"区块 #{bd['index']}"

                st.markdown(
                    f"""
                    <div style="
                        background:{'#1a1a2e' if not is_genesis else '#2e1a0e'};
                        border:1px solid {block_color};
                        border-radius:10px;
                        padding:0.8rem 1.2rem;
                        margin-bottom:0.5rem;
                    ">
                        <div style="display:flex;justify-content:space-between;align-items:center">
                            <span style="font-size:1.1rem;font-weight:bold">{block_label}</span>
                            <span style="font-size:0.8rem;color:#888">{bd['timestamp_str']}</span>
                        </div>
                        <div style="display:flex;gap:1.5rem;font-size:0.8rem;margin-top:0.3rem;flex-wrap:wrap">
                            <span>📄 交易�? <strong>{bd['tx_count']}</strong></span>
                            <span>🔗 Nonce: <strong>{bd['nonce']}</strong></span>
                            <span style="color:#aaa">
                                哈希: <code>{bd['hash'][:20]}...</code>
                            </span>
                        </div>
                        <div style="font-size:0.75rem;color:#666;margin-top:0.2rem">
                            前置哈希: <code>{bd['previous_hash'][:20]}...</code>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                # 区块内交易列�?
                for j, tx in enumerate(bd["transactions"]):
                    render_tx_card(tx, j)

    st.info("🟢 所有区块通过哈希指针链接，任何数据的篡改都将导致后续所有区块哈希不一致，从而被系统检测到�?)

# ══════════════════════════════════════════════════════════�?
# 页面 2: 产品追溯
# ══════════════════════════════════════════════════════════�?
elif page == "🔍 产品追溯":
    st.title("🔍 产品追溯")
    st.markdown("输入产品ID，追溯该产品从生产到销售的全生命周期记录�?)

    products = get_product_list(bc)
    if not products:
        st.warning("暂无产品数据")
    else:
        selected_product = st.selectbox(
            "选择要追溯的产品",
            products,
            index=None,
            placeholder="请选择产品...",
        )

        if selected_product:
            trace = bc.trace_product(selected_product)
            if trace:
                product_info = trace[0]["data"]
                st.subheader(f"📦 {product_info.get('product_name', selected_product)}")

                c1, c2, c3 = st.columns(3)
                c1.metric("产品ID", selected_product)
                c2.metric("类别", product_info.get("category", "-"))
                c3.metric("追溯环节", f"{len(trace)} 个环�?)

                st.divider()

                # 时间线展�?
                st.subheader("📅 全链路追溯时间线")

                for idx, record in enumerate(trace):
                    tx_data = record["data"]
                    tx_type = record["tx_type"]
                    color = get_transaction_color(tx_type)
                    icon_map = {
                        "production": "🌾",
                        "processing": "🏭",
                        "logistics": "🚚",
                        "sale": "🏪",
                    }

                    # 时间线节�?
                    cols = st.columns([1, 2, 9])
                    with cols[0]:
                        if idx < len(trace) - 1:
                            st.markdown(
                                f"""<div style="text-align:center;font-size:1.8rem">{icon_map[tx_type]}</div>
                                <div style="width:2px;height:40px;background:{color};margin:0 auto"></div>""",
                                unsafe_allow_html=True,
                            )
                        else:
                            st.markdown(
                                f"""<div style="text-align:center;font-size:1.8rem">{icon_map[tx_type]}</div>""",
                                unsafe_allow_html=True,
                            )

                    with cols[1]:
                        st.markdown(
                            f"""<span style="background:{color};color:white;padding:2px 8px;border-radius:4px;font-size:0.75rem">{record['tx_type_label']}</span>""",
                            unsafe_allow_html=True,
                        )
                        st.caption(record["timestamp_str"])

                    with cols[2]:
                        st.markdown(
                            f"""<div style="background:#1a1a2e;padding:0.8rem;border-radius:8px;margin-bottom:0.5rem">""",
                            unsafe_allow_html=True,
                        )
                        # 显示关键信息
                        key_fields = {
                            "production": ["producer", "origin", "quality_grade", "certification"],
                            "processing": ["processor", "process_type", "quality_check", "facility"],
                            "logistics": ["logistics_provider", "transport_mode", "departure", "destination"],
                            "sale": ["seller", "store", "selling_price", "shelf_date"],
                        }
                        for field in key_fields.get(tx_type, []):
                            val = tx_data.get(field, "")
                            if val:
                                label_map = {
                                    "producer": "生产�?, "origin": "产地", "quality_grade": "品质等级",
                                    "certification": "认证", "processor": "加工�?, "process_type": "加工类型",
                                    "quality_check": "质检", "facility": "设施",
                                    "logistics_provider": "物流�?, "transport_mode": "运输方式",
                                    "departure": "出发�?, "destination": "目的�?,
                                    "seller": "销售商", "store": "门店", "selling_price": "售价",
                                    "shelf_date": "上架日期",
                                }
                                st.markdown(f"**{label_map.get(field, field)}**: {val}")
                        st.markdown(f"<div style='font-size:0.75rem;color:#666;margin-top:0.3rem'>区块 #{record['block_index']} | <code>{record['block_hash'][:16]}...</code></div>", unsafe_allow_html=True)
                        st.markdown("</div>", unsafe_allow_html=True)

                st.divider()
                st.subheader("📋 完整追溯数据")
                df = pd.DataFrame(
                    [
                        {
                            "环节": r["tx_type_label"],
                            "时间": r["timestamp_str"],
                            "区块": f"#{r['block_index']}",
                            "交易ID": r["tx_id"][:12] + "...",
                        }
                        for r in trace
                    ]
                )
                st.dataframe(df, width='stretch', hide_index=True)

                st.success(
                    f"�?该产品共经过 **{len(trace)} 个环�?*，所有记录均已上链存储，"
                    f"数据不可篡改，可完整追溯�?
                )
            else:
                st.warning("未找到该产品的追溯记�?)
    st.divider()
    st.caption("💡 提示：区块链溯源确保每一条记录都不可篡改，消费者可以放心查验产品的完整流通过程�?)

# ══════════════════════════════════════════════════════════�?
# 页面 3: 添加交易
# ══════════════════════════════════════════════════════════�?
elif page == "�?添加交易":
    st.title("�?添加交易")
    st.markdown("向区块链提交新的供应链交易记录（需要挖矿后才能打包入链�?)

    tx_type = st.selectbox(
        "选择交易类型",
        [
            ("production", "🌾 生产记录 - 农产品种�?养殖信息"),
            ("processing", "🏭 加工记录 - 分拣/加工/包装信息"),
            ("logistics", "🚚 物流记录 - 运输/仓储信息"),
            ("sale", "🏪 销售记�?- 销�?上架信息"),
        ],
        format_func=lambda x: x[1],
    )

    tx_type_key = tx_type[0]

    # 选择已有产品或新�?
    existing_products = get_product_list(bc)
    use_existing = st.checkbox("选择已有产品", value=True if existing_products else False)

    if use_existing and existing_products:
        product_id = st.selectbox("选择产品", existing_products)
    else:
        product_id = st.text_input("产品ID", value=f"PROD-{random.randint(1000,9999)}-{datetime.now().year}")

    product_name = st.text_input("产品名称")

    # 根据交易类型展示不同表单
    data = {"product_id": product_id, "product_name": product_name}

    if tx_type_key == "production":
        c1, c2 = st.columns(2)
        with c1:
            data["category"] = st.selectbox("产品类别", ["水果", "蔬菜", "粮食", "茶叶", "肉类", "乳制�?, "水产�?])
            data["producer"] = st.text_input("生产者名�?, value="阳光生态农�?)
            data["origin"] = st.text_input("产地", value="黑龙江省五常�?)
            data["planting_date"] = st.date_input("种植/生产日期").strftime("%Y-%m-%d")
        with c2:
            data["harvest_date"] = st.date_input("收获/采集日期").strftime("%Y-%m-%d")
            data["batch_number"] = st.text_input("批号", value=f"BATCH-{random.randint(1000,9999)}")
            data["quality_grade"] = st.selectbox("品质等级", ["特级", "一�?, "二级", "合格"])
            data["certification"] = st.text_input("认证信息", value="有机认证 GB/T 19630")
        data["notes"] = st.text_area("备注", value="采用生态种植方式，无农药残�?)

    elif tx_type_key == "processing":
        c1, c2 = st.columns(2)
        with c1:
            data["processor"] = st.text_input("加工商名�?, value="鲜品加工�?)
            data["process_type"] = st.text_input("加工类型", value="分拣·清洗·包装")
            data["facility"] = st.text_input("加工设施", value="A区无菌加工车�?)
        with c2:
            data["processing_date"] = st.date_input("加工日期").strftime("%Y-%m-%d")
            data["expiry_date"] = st.date_input("保质期至").strftime("%Y-%m-%d")
            data["supervisor"] = st.text_input("负责�?, value="李明")
        data["quality_check"] = st.text_area("质检结果", value="已通过食品安全检测，符合 GB 2762-2022 标准")

    elif tx_type_key == "logistics":
        c1, c2 = st.columns(2)
        with c1:
            data["logistics_provider"] = st.text_input("物流商名�?, value="顺达冷链物流")
            data["transport_mode"] = st.text_input("运输方式", value="冷链运输 (0-4°C)")
            data["departure"] = st.text_input("出发�?, value="黑龙江省哈尔滨市")
            data["vehicle_number"] = st.text_input("车牌�?, value=f"京A·{random.randint(10000,99999)}")
        with c2:
            data["destination"] = st.text_input("目的�?, value="北京市朝阳区")
            data["shipment_date"] = st.date_input("发货日期").strftime("%Y-%m-%d")
            data["estimated_arrival"] = st.date_input("预计到达").strftime("%Y-%m-%d")
            data["temperature_range"] = st.text_input("温度范围", value="0~4°C")
        data["tracking_number"] = st.text_input("运单�?, value=f"SF-{random.randint(100000,999999)}")

    elif tx_type_key == "sale":
        c1, c2 = st.columns(2)
        with c1:
            data["seller"] = st.text_input("销售商名称", value="盒马鲜生")
            data["store"] = st.text_input("销售门�?, value="盒马鲜生·北京朝阳�?)
            data["selling_price"] = st.text_input("售价", value="29.9�?500g")
        with c2:
            data["shelf_date"] = st.date_input("上架日期").strftime("%Y-%m-%d")
            data["stock_quantity"] = st.number_input("库存�?, min_value=1, value=1000)
            data["promotion"] = st.text_input("促销信息", value="新品上架促销")

    if st.button("📤 提交交易", type="primary", width='stretch'):
        tx = Transaction(tx_type_key, data)
        bc.add_transaction(tx)
        _save_blockchain()
        st.success(f"�?交易已提交！交易ID: `{tx.tx_id[:20]}...`")
        st.info("�?交易暂存在待处理池中，请前往「⛏�?挖矿打包」页面将交易打包入链�?)
        st.balloons()

# ══════════════════════════════════════════════════════════�?
# 页面 4: 挖矿打包
# ══════════════════════════════════════════════════════════�?
elif page == "⛏️ 挖矿打包":
    st.title("⛏️ 挖矿打包")
    st.markdown("将待处理的交易打包成新区块并加入区块链（工作量证�?PoW�?)

    pending = bc.pending_transactions
    if pending:
        st.warning(f"📦 当前�?**{len(pending)} �?* 交易等待打包")

        for i, tx in enumerate(pending):
            render_tx_card(tx.to_dict(), i)

        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button("⛏️ 开始挖�?, type="primary", width='stretch', key="mine_btn"):
                with st.status("⛏️ 正在挖矿中，请稍�?..", expanded=True) as status:
                    progress_bar = st.progress(0)
                    for pct in range(10, 101, 10):
                        time.sleep(0.15)
                        progress_bar.progress(pct)
                        if pct <= 30:
                            st.write(f"🔄 正在计算哈希... ({pct}%)")
                        elif pct <= 60:
                            st.write(f"🔍 寻找有效 Nonce... ({pct}%)")
                        elif pct <= 90:
                            st.write(f"�?满足难度目标! ({pct}%)")
                        else:
                            st.write(f"📦 打包完成! ({pct}%)")

                    new_block = bc.mine_pending_transactions()
                    _save_blockchain()
                    status.update(label="�?挖矿成功�?, state="complete")

                st.success(f"🎉 新区块已生成�?)
                c1, c2, c3 = st.columns(3)
                c1.metric("区块高度", f"#{new_block.index}")
                c2.metric("交易数量", len(new_block.transactions))
                c3.metric("Nonce", new_block.nonce)
                st.code(f"区块哈希: {new_block.hash}", language="text")
                st.code(f"前置哈希: {new_block.previous_hash}", language="text")
                st.balloons()

        with col2:
            if st.button("🗑�?清空待处�?, width='stretch'):
                bc.pending_transactions = []
                st.rerun()
    else:
        st.info("�?目前没有待处理的交易，请先前往「➕ 添加交易」页面创建交易�?)

    # 显示挖矿原理
    with st.expander("💡 什么是工作量证�?PoW)�?, expanded=False):
        st.markdown(
            """
            **工作量证�?(Proof of Work)** 是区块链的核心共识机制之一�?

            1. **数学难题**：矿工需要找到一�?`Nonce` 值，使得区块哈希以特定数量的 `0` 开�?
            2. **难度调整**：当前难度为 `4`，即哈希必须以前 `4` 个字符为 `0`
            3. **概率�?*：只能通过暴力枚举找到答案，无法取�?
            4. **不可逆�?*：验证极易（一次哈希计算），但求解极难（大量尝试）
            5. **安全意义**：篡改一个区块需要重新计算该区块及之后所有区块，成本极高

            ```
            目标: hash[:4] == "0000"
            示例: 0000a1b2c3d4e5f6...
            ```
            """
        )

# ══════════════════════════════════════════════════════════�?
# 页面 5: 链验�?
# ══════════════════════════════════════════════════════════�?
elif page == "�?链验�?:
    st.title("�?区块链完整性验�?)
    st.markdown("验证区块链的完整性和一致性，检测是否有数据被篡改�?)

    c1, c2, c3 = st.columns(3)
    c1.metric("区块总数", stats["block_count"])
    c2.metric("总交易数", stats["total_transactions"])
    c3.metric("挖矿难度", stats["difficulty"])

    if st.button("🔍 执行完整性验�?, type="primary", width='stretch'):
        with st.status("正在验证区块�?..", expanded=True) as status:
            time.sleep(0.5)
            st.write("📋 步骤 1/3: 验证区块哈希一致�?..")
            time.sleep(0.3)
            st.write("🔗 步骤 2/3: 验证链式哈希链接...")
            time.sleep(0.3)
            st.write("⛏️ 步骤 3/3: 验证工作量证�?..")
            time.sleep(0.3)

            is_valid, message = bc.is_chain_valid()
            status.update(label="验证完成", state="complete")

        if is_valid:
            st.success(f"## �?{message}")
            st.balloons()
        else:
            st.error(f"## �?{message}")

        st.markdown("### 📊 验证详情")
        details = []
        for i, block in enumerate(bc.chain):
            bd = block.to_dict()
            calc_hash = block.calculate_hash()
            hash_ok = bd["hash"] == calc_hash
            prev_ok = i == 0 or bd["previous_hash"] == bc.chain[i - 1].hash
            pow_ok = bd["hash"].startswith("0" * bc.difficulty)

            details.append({
                "区块": f"#{bd['index']}",
                "哈希一�?: "�? if hash_ok else "�?,
                "链式链接": "�? if prev_ok else "�?,
                "工作量证�?: "�? if pow_ok else "�?,
                "交易�?: bd["tx_count"],
                "Nonce": bd["nonce"],
            })

        st.dataframe(pd.DataFrame(details), width='stretch', hide_index=True)

    st.divider()

    st.subheader("🔬 篡改模拟")
    st.markdown("选择一个区块，模拟篡改其数据，观察区块链如何检测到异常�?)

    block_indices = [b.index for b in bc.chain if b.index > 0]
    if block_indices:
        target_block = st.selectbox(
            "选择要篡改的区块（模拟攻击）",
            block_indices,
            format_func=lambda x: f"区块 #{x}",
        )

        if st.button("⚠️ 模拟篡改", type="secondary", width='stretch'):
            block = bc.chain[target_block]
            block.transactions[0].data["product_name"] = "[已篡改] 假冒产品"

            is_valid_after, msg_after = bc.is_chain_valid()
            if not is_valid_after:
                st.error("### 🚨 篡改已检测到�?)
                st.markdown(
                    f"""
                    ```
                    检测结�? {msg_after}
                    
                    说明: 当区�?#{target_block} 的数据被篡改后，该区块的哈希发生变化�?
                    导致其后所有区块的"前置哈希"与之不匹配，区块链完整性被破坏�?
                    ```
                    """
                )
            st.warning("⚠️ 提示：篡改仅在当前内存中生效，本地保存的数据不受影响。点击「�?重新加载本地数据」可恢复�?)
    else:
        st.info("没有可篡改的区块（仅包含创世区块�?)

# ══════════════════════════════════════════════════════════�?
# 页面 6: 参与方管�?
# ══════════════════════════════════════════════════════════�?
elif page == "👥 参与方管�?:
    st.title("👥 供应链参与方管理")
    st.markdown("管理参与农产品供应链的所有实体（生产者、加工商、物流商、销售商�?)

    col_list, col_add = st.columns([3, 2])

    with col_list:
        st.subheader("📋 已注册参与方")
        if bc.participants:
            participants_df = pd.DataFrame(
                [
                    {
                        "ID": pid,
                        "名称": info["name"],
                        "角色": info["role"],
                        "注册时间": info["registered_at"],
                    }
                    for pid, info in bc.participants.items()
                ]
            )
            st.dataframe(participants_df, width='stretch', hide_index=True)

            # 角色分布
            role_counts = {}
            for info in bc.participants.values():
                role_counts[info["role"]] = role_counts.get(info["role"], 0) + 1

            st.subheader("📊 角色分布")
            role_df = pd.DataFrame(
                {"角色": k, "数量": v} for k, v in role_counts.items()
            )
            st.dataframe(role_df, width='stretch', hide_index=True)
        else:
            st.info("暂无注册的参与方")

    with col_add:
        st.subheader("�?注册新参与方")
        with st.form("register_form"):
            pid = st.text_input("参与方ID", value=f"party_{random.randint(100,999)}")
            name = st.text_input("名称", placeholder="例如: 阳光生态农�?)
            role = st.selectbox("角色", ["生产�?, "加工�?, "物流�?, "销售商", "质检机构", "监管机构"])
            submitted = st.form_submit_button("注册", type="primary", width='stretch')

            if submitted and pid and name:
                if pid in bc.participants:
                    st.error(f"参与方ID '{pid}' 已存�?)
                else:
                    bc.register_participant(pid, name, role)
                    _save_blockchain()
                    st.success(f"�?参与�?'{name}' 注册成功�?)
                    st.rerun()

    st.divider()
    st.subheader("🔗 供应链网络关系图")
    st.markdown(
        """
        本系统模拟了以下供应链网络：

        ```
        🌾 生产�?──�?🏭 加工�?──�?🚚 物流�?──�?🏪 销售商 ──�?👤 消费�?
        (农场)        (加工�?       (冷链物流)     (商超/电商)    (终端用户)
        ```

        **溯源链路**: 消费者扫描二维码 �?获取产品ID �?区块链查�?�?全链路展�?
        """
    )

# ─── 页脚 ──────────────────────────────────────────────────
st.sidebar.divider()
st.sidebar.caption(
    """
    🔗 **区块链溯源系�?v1.0**
    
    技术栈:
    - Python + Streamlit
    - SHA-256 哈希算法
    - 工作量证�?(PoW)
    
    �?仅供演示与学习使�?
    """
)
