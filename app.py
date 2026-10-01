# -*- coding: utf-8 -*-
"""
农产品区块链溯源系统 —— Streamlit 前端

本文件只负责「界面 + 交互」，链的实现位于 ``blockchain.py``，
业务语义（字段标签、冷链规则、保质期、溯源证书）位于 ``supply_chain.py``。
"""

from __future__ import annotations

import copy
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import supply_chain as sc
from blockchain import (
    REQUIRED_FIELDS,
    SCHEMA_VERSION,
    TRANSACTION_TYPES,
    Blockchain,
    Transaction,
    compute_merkle_root,
    resolve_data_dir,
    verify_merkle_proof,
)

# ── 页面配置 ────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="农产品区块链溯源系统",
    page_icon="🌾",
    layout="wide",
    initial_sidebar_state="expanded",
)

DATA_DIR = resolve_data_dir()
DATA_FILE = DATA_DIR / "blockchain.json"

CHAIN_ICON = {"production": "🌱", "processing": "🏭", "logistics": "🚚", "sale": "🏪"}

CUSTOM_CSS = """
<style>
    .block-container { padding-top: 2.2rem; padding-bottom: 3rem; }
    .hero {
        background: linear-gradient(120deg, #1b5e20 0%, #2e7d32 45%, #43a047 100%);
        border-radius: 16px; padding: 1.6rem 2rem; color: #fff;
        margin-bottom: 1.4rem; box-shadow: 0 6px 20px rgba(27, 94, 32, .28);
    }
    .hero h1 { margin: 0; font-size: 1.85rem; font-weight: 700; letter-spacing: .5px; }
    .hero p  { margin: .5rem 0 0; opacity: .92; font-size: .95rem; }
    .stage-card {
        border-left: 6px solid #2e7d32; background: #fafafa;
        border-radius: 10px; padding: .9rem 1.1rem; margin-bottom: .6rem;
    }
    .stage-card h4 { margin: 0 0 .5rem; font-size: 1.02rem; }
    .stage-card table { width: 100%; border-collapse: collapse; font-size: .87rem; }
    .stage-card th {
        text-align: left; color: #607d8b; font-weight: 500;
        padding: 2px 10px 2px 0; white-space: nowrap; vertical-align: top;
        width: 34%;
    }
    .stage-card td { padding: 2px 0; color: #263238; word-break: break-all; }
    .pill {
        display: inline-block; padding: 2px 11px; border-radius: 999px;
        font-size: .76rem; font-weight: 600; margin-right: 6px;
    }
    .mono { font-family: ui-monospace, Consolas, monospace; font-size: .8rem; color: #455a64; }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# ── 链的生命周期管理 ────────────────────────────────────────────────────────


def _new_chain() -> Blockchain:
    """创建一条带演示数据的新链。"""
    chain = sc.seed_blockchain()
    try:
        chain.save_to_file(str(DATA_FILE))
    except OSError as error:  # 只读挂载等极端情况下仍可使用内存中的链
        st.session_state["persist_error"] = str(error)
    return chain


def get_chain() -> Blockchain:
    """取得当前会话的链对象（首次访问时从磁盘加载或新建）。"""
    if "chain" not in st.session_state:
        loaded = Blockchain.load_from_file(str(DATA_FILE))
        st.session_state["chain"] = loaded if loaded is not None else _new_chain()
    return st.session_state["chain"]


def persist_chain() -> None:
    """把当前链写回磁盘（原子写）。"""
    try:
        get_chain().save_to_file(str(DATA_FILE))
        st.toast("已保存到本地文件", icon="💾")
    except OSError as error:
        st.error(f"保存失败：{error}")


def reset_chain(with_demo_data: bool) -> None:
    """重建链（可选是否写入演示数据）。"""
    chain = sc.seed_blockchain() if with_demo_data else Blockchain()
    chain.save_to_file(str(DATA_FILE))
    st.session_state["chain"] = chain
    st.session_state.pop("chain_backup", None)
    st.rerun()


# ── 通用展示辅助 ────────────────────────────────────────────────────────────


def fmt_value(field: str, value: Any) -> str:
    """按字段标签给值补上单位，并做可读化处理。"""
    if value is None or value == "":
        return "—"
    if isinstance(value, (list, tuple)):
        parts = [f"{v}°C" if isinstance(v, (int, float)) else str(v) for v in value]
        return "、".join(parts)
    label, unit = sc.FIELD_LABELS.get(field, (field, ""))
    text = str(value)
    if unit and unit not in text:
        text = f"{text}{unit}"
    return text


def bool_cell(flag: bool) -> str:
    return "✅" if flag else "❌"


def stage_card_html(record: Dict[str, Any]) -> str:
    """渲染单个环节的卡片 HTML。"""
    tx_type = record["tx_type"]
    color = sc.STAGE_COLORS.get(tx_type, "#455a64")
    icon = sc.stage_icon(tx_type)
    label = TRANSACTION_TYPES.get(tx_type, tx_type)

    rows: List[str] = []
    for field, value in record["data"].items():
        if field in ("product_id", "product_name", "category"):
            continue
        field_label, _ = sc.FIELD_LABELS.get(field, (field, ""))
        rows.append(
            f"<tr><th>{field_label}</th><td>{fmt_value(field, value)}</td></tr>"
        )

    return (
        f'<div class="stage-card" style="border-left-color:{color}">'
        f"<h4>{icon} {label}</h4>"
        f'<div class="mono">区块 #{record["block_index"]} · '
        f'交易 {record["tx_id"][:16]}… · 上链时间 {record["block_time"]}</div>'
        f"<table>{''.join(rows)}</table></div>"
    )


def status_banner() -> None:
    """侧边栏顶部的链状态提示。"""
    chain = get_chain()
    ok, message = chain.is_chain_valid()
    if ok:
        st.success(f"✅ {message}", icon="🔒")
    else:
        st.error(f"⚠️ {message}", icon="🚨")


# ── 页面 1：总览看板 ────────────────────────────────────────────────────────


def page_overview() -> None:
    st.markdown(
        '<div class="hero"><h1>🌾 农产品区块链溯源系统</h1>'
        "<p>从田间到餐桌的全链路可信存证 —— 生产、加工、物流、销售四环节上链，"
        "支持完整性校验、Merkle 证明与篡改检测。</p></div>",
        unsafe_allow_html=True,
    )

    chain = get_chain()
    stats = chain.get_chain_stats()
    ok, message = chain.is_chain_valid()

    if ok:
        st.success(message, icon="🔒")
    else:
        st.error(message, icon="🚨")

    row = st.columns(6)
    row[0].metric("区块总数", stats["block_count"])
    row[1].metric("交易总数", stats["total_transactions"])
    row[2].metric("已溯源产品", stats["unique_products"])
    row[3].metric("参与方", stats["participants"])
    row[4].metric("当前难度", stats["difficulty"])
    row[5].metric(
        "待打包交易", stats["pending_transactions"], delta_color="off"
    )

    row2 = st.columns(4)
    row2[0].metric("平均出块间隔", f"{stats['avg_block_seconds']:.2f} s")
    row2[1].metric("平均挖矿耗时", f"{stats['avg_mine_seconds']:.3f} s")
    row2[2].metric("累计哈希尝试", f"{stats['total_pow_attempts']:,}")
    row2[3].metric("链数据体积", f"{stats['chain_size_kb']:.2f} KB")

    st.divider()
    left, right = st.columns([3, 2])

    with left:
        st.subheader("📦 各区块交易构成")
        blocks = chain.chain
        fig = go.Figure()
        for tx_type, label in TRANSACTION_TYPES.items():
            counts = [
                sum(1 for tx in block.transactions if tx.tx_type == tx_type)
                for block in blocks
            ]
            fig.add_bar(
                x=[f"#{b.index}" for b in blocks],
                y=counts,
                name=label,
                marker_color=sc.STAGE_COLORS.get(tx_type),
            )
        fig.update_layout(
            barmode="stack",
            height=340,
            margin=dict(l=10, r=10, t=20, b=10),
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
            yaxis_title="交易数",
            xaxis_title="区块",
        )
        st.plotly_chart(fig, width="stretch")

    with right:
        st.subheader("🥧 产品类别分布")
        categories: Dict[str, int] = {}
        for pid in chain.get_product_list():
            records = chain.trace_product(pid)
            category = records[0]["data"].get("category", "未分类") if records else "未分类"
            categories[category] = categories.get(category, 0) + 1
        if categories:
            pie = go.Figure(
                go.Pie(
                    labels=list(categories),
                    values=list(categories.values()),
                    hole=0.45,
                )
            )
            pie.update_layout(height=340, margin=dict(l=10, r=10, t=20, b=10))
            st.plotly_chart(pie, width="stretch")
        else:
            st.info("暂无产品数据")

    st.divider()
    st.subheader("⛏️ 最近挖矿记录")
    if chain.mining_log:
        log_rows = [
            {
                "区块": entry["index"],
                "矿工": entry["miner"],
                "难度": entry["difficulty"],
                "Nonce": entry["nonce"],
                "尝试次数": entry["attempts"],
                "耗时(秒)": entry["duration_s"],
                "交易数": entry["tx_count"],
                "时间": datetime.fromtimestamp(entry["timestamp"]).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
            }
            for entry in reversed(chain.mining_log[-10:])
        ]
        st.dataframe(pd.DataFrame(log_rows), width="stretch", hide_index=True)
    else:
        st.info("暂无挖矿记录")


# ── 页面 2：产品溯源 ────────────────────────────────────────────────────────


def page_trace() -> None:
    st.header("🔍 产品溯源查询")
    chain = get_chain()
    products = chain.get_product_list()

    if not products:
        st.warning("链上暂无产品记录，请先到「添加交易」页面上链数据。")
        return

    labels: Dict[str, str] = {}
    for pid in products:
        records = chain.trace_product(pid)
        name = records[0]["data"].get("product_name", "") if records else ""
        labels[pid] = f"{name}（{pid}）" if name else pid

    selected = st.selectbox(
        "选择要溯源的产品", products, format_func=lambda p: labels.get(p, p)
    )
    records = chain.trace_product(selected)
    first = records[0]["data"] if records else {}

    info = st.columns(4)
    info[0].metric("产品名称", first.get("product_name", "—"))
    info[1].metric("产品编号", selected)
    info[2].metric("类别", first.get("category", "—"))
    info[3].metric("溯源记录数", len(records))

    with st.expander("🔗 产品身份与链上索引", expanded=False):
        product_blocks = chain.product_blocks.get(selected, [])
        st.write(f"**所在区块：** {', '.join(f'#{i}' for i in product_blocks) or '—'}")
        st.write(f"**交易条数：** {len(records)}")
        st.write(
            f"**索引方式：** `product_index` 记录每笔交易的 (区块号, 交易下标)，"
            f"因此同一产品多笔交易不会被重复统计。"
        )

    st.divider()
    st.subheader("🕓 全链路时间线")

    for record in records:
        st.markdown(stage_card_html(record), unsafe_allow_html=True)

    st.divider()
    left, right = st.columns(2)

    with left:
        st.subheader("🧊 冷链温控核验")
        logistics = next((r for r in records if r["tx_type"] == "logistics"), None)
        if logistics is None:
            st.info("该产品没有物流环节记录")
        else:
            report = sc.cold_chain_report(logistics["tx"])
            if not report["applicable"]:
                st.info(report["note"])
            else:
                if report["compliant"]:
                    st.success(
                        f"全程温控达标（要求 {report['range'][0]}~{report['range'][1]}°C，"
                        f"采样均值 {report['average']:.2f}°C）",
                        icon="✅",
                    )
                else:
                    st.error(
                        f"检出 {len(report['violations'])} 次超出温控范围 "
                        f"（要求 {report['range'][0]}~{report['range'][1]}°C，"
                        f"越限采样 {report['violations']}）",
                        icon="🌡️",
                    )
                if report["readings"]:
                    temp_fig = go.Figure()
                    temp_fig.add_scatter(
                        y=report["readings"],
                        mode="lines+markers",
                        name="在途温度",
                        line=dict(color="#1565c0", width=2),
                    )
                    temp_fig.add_hrect(
                        y0=report["range"][0],
                        y1=report["range"][1],
                        fillcolor="#43a047",
                        opacity=0.12,
                        line_width=0,
                        annotation_text="允许区间",
                    )
                    temp_fig.update_layout(
                        height=260,
                        margin=dict(l=10, r=10, t=20, b=10),
                        yaxis_title="温度 (°C)",
                        xaxis_title="采样点",
                    )
                    st.plotly_chart(temp_fig, width="stretch")

    with right:
        st.subheader("⏳ 保质期状态")
        processing = next((r for r in records if r["tx_type"] == "processing"), None)
        expiry = processing["data"].get("expiry_date") if processing else None
        status = sc.expiry_status(expiry)
        st.markdown(
            f'<span class="pill" style="background:{status["color"]}22;'
            f'color:{status["color"]}">{status["label"]}</span>',
            unsafe_allow_html=True,
        )
        st.caption(f"保质期截止日：{status['expiry_date'] or '—'}")

        if len(records) >= 2:
            st.subheader("🌡️ 环节间温度/日期序列")
            timeline_rows = [
                {
                    "环节": TRANSACTION_TYPES.get(r["tx_type"], r["tx_type"]),
                    "上链时间": r["block_time"],
                    "所在区块": r["block_index"],
                }
                for r in records
            ]
            st.dataframe(
                pd.DataFrame(timeline_rows), width="stretch", hide_index=True
            )

    st.divider()
    st.subheader("🧾 溯源证书")
    html = sc.build_trace_html(chain, selected, records)
    dl, preview = st.columns([1, 1])
    with dl:
        st.download_button(
            "⬇️ 下载溯源证书（HTML）",
            data=html.encode("utf-8"),
            file_name=f"溯源证书-{selected}.html",
            mime="text/html",
            width="stretch",
        )
    with preview:
        st.caption("证书为自包含 HTML，可离线查看或打印为 PDF。")
    with st.expander("👁️ 预览证书"):
        st.html(html)

    st.divider()
    st.subheader("🔐 Merkle 存在性证明")
    st.caption(
        "Merkle 树让「某笔交易确实被打包进某个区块」可以在不下载整块数据的前提下被验证。"
    )
    pick = st.selectbox(
        "选择要验证的交易",
        options=list(range(len(records))),
        format_func=lambda i: (
            f"{TRANSACTION_TYPES.get(records[i]['tx_type'], records[i]['tx_type'])}"
            f" · {records[i]['tx_id'][:20]}…"
        ),
    )
    record = records[pick]
    block = chain.get_block(record["block_index"])
    if block is None:
        st.error("区块不存在")
        return

    tx_ids = block.tx_ids
    proof = block.proof_for(record["tx_index"])
    root = compute_merkle_root(tx_ids)
    verified = verify_merkle_proof(record["tx_id"], proof, root)

    proof_rows = [
        {"层级": level, "兄弟哈希": sibling[:32] + "…", "位置": "左" if is_left else "右"}
        for level, (sibling, is_left) in enumerate(proof)
    ]
    pc = st.columns([1, 2])
    pc[0].metric("验证结果", "通过 ✅" if verified else "失败 ❌")
    pc[0].metric("证明路径长度", len(proof))
    with pc[1]:
        st.write(f"**区块 Merkle 根：** `{root}`")
        st.write(f"**区块记录哈希：** `{block.hash}`")
        st.caption(f"Merkle 根是否与区块一致：{'✅' if block.merkle_root == root else '❌'}")
    if proof_rows:
        st.dataframe(pd.DataFrame(proof_rows), width="stretch", hide_index=True)


# ── 页面 3：冷链与保质期 ────────────────────────────────────────────────────


def page_cold_chain() -> None:
    st.header("🧊 冷链温控与保质期预警")
    st.caption("基于链上物流与加工记录计算，属于业务侧派生指标，不改变链上数据。")

    chain = get_chain()
    products = chain.get_product_list()
    if not products:
        st.warning("链上暂无产品记录。")
        return

    logistics_rows: List[Dict[str, Any]] = []
    expiry_rows: List[Dict[str, Any]] = []

    for pid in products:
        records = chain.trace_product(pid)
        name = records[0]["data"].get("product_name", pid) if records else pid
        logistics = next((r for r in records if r["tx_type"] == "logistics"), None)
        processing = next((r for r in records if r["tx_type"] == "processing"), None)

        if logistics is not None:
            report = sc.cold_chain_report(logistics["tx"])
            logistics_rows.append(
                {
                    "产品": name,
                    "产品编号": pid,
                    "温控要求": report["range_text"] if report["applicable"] else "—",
                    "采样数": len(report["readings"]),
                    "最低": report["min"],
                    "最高": report["max"],
                    "均值": (
                        round(report["average"], 2)
                        if report["average"] is not None
                        else None
                    ),
                    "越限次数": len(report["violations"]),
                    "是否合规": (
                        bool_cell(report["compliant"]) if report["applicable"] else "—"
                    ),
                    "_compliant": report["compliant"] if report["applicable"] else None,
                }
            )

        if processing is not None:
            status = sc.expiry_status(processing["data"].get("expiry_date"))
            expiry_rows.append(
                {
                    "产品": name,
                    "产品编号": pid,
                    "截止日": status["expiry_date"] or "—",
                    "剩余天数": status["days"],
                    "预警等级": status["label"],
                    "_level": status["level"],
                }
            )

    tab1, tab2 = st.tabs(["🌡️ 冷链合规", "⏳ 保质期预警"])

    with tab1:
        if not logistics_rows:
            st.info("暂无物流记录")
        else:
            compliant = sum(1 for r in logistics_rows if r["_compliant"] is True)
            total = sum(1 for r in logistics_rows if r["_compliant"] is not None)
            cols = st.columns(3)
            cols[0].metric("受检产品", total)
            cols[1].metric("合规产品", compliant)
            cols[2].metric(
                "合规率", f"{(compliant / total * 100):.0f}%" if total else "—"
            )
            display = [
                {k: v for k, v in row.items() if not k.startswith("_")}
                for row in logistics_rows
            ]
            st.dataframe(pd.DataFrame(display), width="stretch", hide_index=True)

            chart_rows = [r for r in logistics_rows if r["采样数"] > 0]
            if chart_rows:
                fig = go.Figure()
                for row in chart_rows:
                    records = chain.trace_product(row["产品编号"])
                    logistics = next(
                        (r for r in records if r["tx_type"] == "logistics"), None
                    )
                    if logistics is None:
                        continue
                    report = sc.cold_chain_report(logistics["tx"])
                    fig.add_scatter(
                        y=report["readings"],
                        mode="lines+markers",
                        name=row["产品"],
                    )
                fig.update_layout(
                    height=340,
                    margin=dict(l=10, r=10, t=20, b=10),
                    yaxis_title="温度 (°C)",
                    xaxis_title="采样点",
                )
                st.plotly_chart(fig, width="stretch")

    with tab2:
        if not expiry_rows:
            st.info("暂无加工记录")
        else:
            order = {"expired": 0, "critical": 1, "warning": 2, "ok": 3, "unknown": 4}
            expiry_rows.sort(key=lambda r: order.get(r["_level"], 9))
            counts = {"expired": 0, "critical": 0, "warning": 0, "ok": 0}
            for row in expiry_rows:
                if row["_level"] in counts:
                    counts[row["_level"]] += 1
            cols = st.columns(4)
            cols[0].metric("已过期", counts["expired"])
            cols[1].metric("3 天内到期", counts["critical"])
            cols[2].metric("14 天内到期", counts["warning"])
            cols[3].metric("状态正常", counts["ok"])

            display = [
                {k: v for k, v in row.items() if not k.startswith("_")}
                for row in expiry_rows
            ]
            st.dataframe(
                pd.DataFrame(display),
                width="stretch",
                hide_index=True,
                column_config={
                    "剩余天数": st.column_config.NumberColumn("剩余天数", format="%d 天"),
                },
            )


# ── 页面 4：添加交易 ────────────────────────────────────────────────────────

#: 表单字段按类型的区分（核心字段来自 blockchain.REQUIRED_FIELDS）
CORE_FIELDS: Dict[str, List[str]] = {
    "production": ["product_id", "product_name", "producer", "producer_id", "origin"],
    "processing": ["product_id", "product_name", "processor", "processor_id", "process_type"],
    "logistics": [
        "product_id",
        "product_name",
        "logistics_provider",
        "logistics_id",
        "departure",
        "destination",
    ],
    "sale": ["product_id", "product_name", "seller", "seller_id", "store"],
}

OPTIONAL_FIELDS: Dict[str, List[str]] = {
    "production": [
        "category",
        "planting_date",
        "harvest_date",
        "batch_number",
        "quality_grade",
        "certification",
        "planting_area_mu",
        "soil_ph",
        "notes",
    ],
    "processing": [
        "category",
        "processing_date",
        "expiry_date",
        "facility",
        "batch_number",
        "supervisor",
        "quality_check",
        "additives",
        "notes",
    ],
    "logistics": [
        "category",
        "transport_mode",
        "shipment_date",
        "estimated_arrival",
        "tracking_number",
        "temperature_range",
        "temperature_readings",
        "vehicle_number",
        "notes",
    ],
    "sale": [
        "category",
        "shelf_date",
        "selling_price",
        "stock_quantity",
        "promotion",
        "notes",
    ],
}

DATE_FIELDS = {
    "planting_date",
    "harvest_date",
    "processing_date",
    "expiry_date",
    "shipment_date",
    "estimated_arrival",
    "shelf_date",
}
NUMBER_FIELDS = {"planting_area_mu", "soil_ph", "stock_quantity"}
LIST_FIELDS = {"temperature_readings"}
TEXTAREA_FIELDS = {"notes"}

#: 参与方下拉框按交易类型匹配的角色
ROLE_BY_TYPE = {
    "production": "生产者",
    "processing": "加工商",
    "logistics": "物流商",
    "sale": "销售商",
}
#: 核心字段里可以直接由参与方选择填充的映射
PARTICIPANT_BINDING = {
    "producer": ("name", None),
    "producer_id": ("id", None),
    "processor": ("name", None),
    "processor_id": ("id", None),
    "logistics_provider": ("name", None),
    "logistics_id": ("id", None),
    "seller": ("name", None),
    "seller_id": ("id", None),
    "store": ("name", None),
}
BINDING_FIELD = {
    "production": "producer",
    "processing": "processor",
    "logistics": "logistics_provider",
    "sale": "seller",
}


def _parse_date(text: Any) -> Optional[date]:
    try:
        return datetime.strptime(str(text)[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _render_field(field: str, tx_type: str, key: str, default: Any) -> Any:
    """按字段类型渲染合适的输入控件。"""
    label, unit = sc.FIELD_LABELS.get(field, (field, ""))
    shown = f"{label}（{unit}）" if unit else label

    if field in DATE_FIELDS:
        parsed = _parse_date(default) or date.today()
        picked = st.date_input(shown, value=parsed, key=key)
        return picked.strftime("%Y-%m-%d")
    if field in NUMBER_FIELDS:
        base = float(default) if isinstance(default, (int, float)) else 0.0
        step = 0.1 if field == "soil_ph" else 1.0
        value = st.number_input(shown, value=base, step=step, key=key)
        return int(value) if field != "soil_ph" else float(value)
    if field in LIST_FIELDS:
        text = st.text_input(
            f"{shown}（逗号分隔）",
            value=", ".join(str(v) for v in default) if isinstance(default, list) else "",
            key=key,
            placeholder="例如：2.1, 1.8, 3.4",
        )
        values: List[float] = []
        for piece in text.replace("，", ",").split(","):
            piece = piece.strip()
            if not piece:
                continue
            try:
                values.append(float(piece))
            except ValueError:
                st.warning(f"无法解析温度采样值：{piece}")
        return values
    if field in TEXTAREA_FIELDS:
        return st.text_area(shown, value=str(default or ""), key=key, height=80)

    return st.text_input(shown, value=str(default or ""), key=key)


def page_add_transaction() -> None:
    st.header("➕ 上链新交易")
    st.caption("提交后进入待处理池，需到「挖矿中心」打包进区块才算真正上链。")

    chain = get_chain()
    tx_type = st.radio(
        "交易类型",
        options=list(TRANSACTION_TYPES),
        format_func=lambda t: f"{CHAIN_ICON.get(t, '')} {TRANSACTION_TYPES[t]}",
        horizontal=True,
    )

    role = ROLE_BY_TYPE[tx_type]
    candidates = [
        (pid, info)
        for pid, info in chain.participants.items()
        if info.get("role") == role
    ]
    known_products = chain.get_product_list()

    with st.form("add_tx_form", clear_on_submit=False):
        st.subheader("必填信息")
        core_cols = st.columns(2)
        core_values: Dict[str, Any] = {}

        for index, field in enumerate(CORE_FIELDS[tx_type]):
            column = core_cols[index % 2]
            with column:
                if field in ("product_id", "product_name") and known_products:
                    if field == "product_id":
                        choice = st.selectbox(
                            sc.label_for(field),
                            options=["<新建产品>"] + known_products,
                            key=f"core_{tx_type}_{field}",
                        )
                        if choice == "<新建产品>":
                            core_values[field] = st.text_input(
                                "新产品编号", key=f"core_{tx_type}_{field}_new"
                            )
                        else:
                            core_values[field] = choice
                    else:
                        pid_selected = core_values.get("product_id", "")
                        guess = ""
                        if pid_selected and pid_selected in known_products:
                            recs = chain.trace_product(pid_selected)
                            if recs:
                                guess = recs[0]["data"].get("product_name", "")
                        core_values[field] = st.text_input(
                            sc.label_for(field),
                            value=guess,
                            key=f"core_{tx_type}_{field}",
                        )
                    continue

                if field in PARTICIPANT_BINDING and candidates:
                    bound = BINDING_FIELD.get(tx_type)
                    options = ["<手动输入>"] + [
                        f"{info['name']}（{pid}）" for pid, info in candidates
                    ]
                    picked = st.selectbox(
                        sc.label_for(field), options=options, key=f"core_{tx_type}_{field}"
                    )
                    if picked == "<手动输入>":
                        core_values[field] = st.text_input(
                            "手动填写", key=f"core_{tx_type}_{field}_manual"
                        )
                    else:
                        # 「名称」类字段取括号前的名称，「编号」类字段取括号内的 ID
                        as_name = field in ("store", bound)
                        core_values[field] = (
                            picked.split("（")[0]
                            if as_name
                            else picked.split("（")[-1].rstrip("）")
                        )
                    continue

                core_values[field] = st.text_input(
                    sc.label_for(field), key=f"core_{tx_type}_{field}"
                )

        st.subheader("可选信息")
        optional_values: Dict[str, Any] = {}
        opt_cols = st.columns(2)
        for index, field in enumerate(OPTIONAL_FIELDS[tx_type]):
            column = opt_cols[index % 2]
            with column:
                optional_values[field] = _render_field(
                    field, tx_type, f"opt_{tx_type}_{field}", None
                )

        pending = st.checkbox("直接送入待处理池（不上链，稍后手动挖矿）", value=True)
        submitted = st.form_submit_button("📥 提交交易", width="stretch")

    if submitted:
        data = {k: v for k, v in core_values.items() if v not in ("", None)}
        for key, value in optional_values.items():
            if value in ("", None, []):
                continue
            data[key] = value

        missing = [
            field
            for field in REQUIRED_FIELDS[tx_type]
            if not data.get(field)
        ]
        if missing:
            st.error(
                "缺少必填字段：" + "、".join(sc.label_for(f) for f in missing)
            )
            return

        try:
            tx = Transaction(tx_type, data)
        except (TypeError, ValueError) as error:
            st.error(f"交易构造失败：{error}")
            return

        try:
            tx_id = chain.add_transaction(tx)
        except ValueError as error:
            st.error(f"上链被拒绝：{error}")
            return

        st.success(f"交易已送入待处理池，交易 ID：`{tx_id}`")

        if not pending:
            with st.spinner("正在挖矿打包…"):
                block = chain.mine_pending_transactions()
            st.success(f"已打包进区块 #{block.index}，Nonce={block.nonce}")
        persist_chain()
        st.rerun()

    st.divider()
    st.subheader("📋 待处理池")
    if chain.pending_transactions:
        st.caption(f"当前有 {len(chain.pending_transactions)} 笔交易等待打包。")
        for position, tx in enumerate(chain.pending_transactions):
            with st.expander(
                f"{CHAIN_ICON.get(tx.tx_type, '')} {tx.tx_type_label} · "
                f"{tx.data.get('product_name', tx.tx_id[:16])}"
            ):
                st.json(tx.to_dict())
    else:
        st.info("待处理池为空。")


# ── 页面 5：挖矿中心 ────────────────────────────────────────────────────────


def page_mining() -> None:
    st.header("⛏️ 挖矿中心")
    st.caption("工作量证明（PoW）通过暴力搜索 nonce 使区块哈希满足前导零要求。")

    chain = get_chain()
    pending = chain.pending_transactions

    cols = st.columns(4)
    cols[0].metric("待打包交易", len(pending))
    cols[1].metric("当前难度", chain.difficulty)
    cols[2].metric("目标前导零", "0" * chain.difficulty)
    cols[3].metric("自动调难度", "开" if chain.auto_adjust else "关")

    st.divider()
    config_col, action_col = st.columns([2, 1])

    with config_col:
        difficulty = st.slider(
            "挖矿难度（前导零个数）",
            min_value=1,
            max_value=6,
            value=int(chain.difficulty),
            help="每增加 1，期望哈希尝试次数约变为 16 倍。",
        )
        miner = st.text_input("矿工标识", value="system")
        auto = st.checkbox(
            "自动调整难度（按出块速度）",
            value=chain.auto_adjust,
            help=f"目标出块时间 {Blockchain.TARGET_BLOCK_SECONDS}s，"
            f"每 {Blockchain.ADJUST_EVERY} 块评估一次，"
            f"难度限定在 {Blockchain.MIN_DIFFICULTY}~{Blockchain.MAX_DIFFICULTY}。",
        )

    with action_col:
        st.write("")
        st.write("")
        if st.button("⚙️ 应用难度设置", width="stretch"):
            chain.difficulty = int(difficulty)
            chain.auto_adjust = bool(auto)
            persist_chain()
            st.rerun()

    st.divider()
    if st.button(
        f"⛏️ 打包 {len(pending)} 笔交易并挖矿",
        type="primary",
        width="stretch",
        disabled=not pending,
    ):
        progress = st.progress(0, text="正在计算工作量证明…")
        try:
            started = datetime.now()
            block = chain.mine_pending_transactions(miner or "system")
            elapsed = (datetime.now() - started).total_seconds()
            progress.progress(100, text="挖矿完成")
        except ValueError as error:
            progress.empty()
            st.error(str(error))
            return

        entry = chain.mining_log[-1]
        st.success(
            f"新区块 #{block.index} 已上链！Nonce={block.nonce}，"
            f"尝试 {entry['attempts']:,} 次，耗时 {elapsed:.3f}s"
        )
        st.code(f"区块哈希：{block.hash}\n前一区块：{block.previous_hash}\nMerkle 根：{block.merkle_root}")
        persist_chain()
        st.rerun()

    if not pending:
        st.info("待处理池为空。可到「添加交易」页面提交数据。")

    st.divider()
    st.subheader("📊 挖矿历史")
    if chain.mining_log:
        frame = pd.DataFrame(
            [
                {
                    "区块": e["index"],
                    "矿工": e["miner"],
                    "难度": e["difficulty"],
                    "Nonce": e["nonce"],
                    "尝试次数": e["attempts"],
                    "耗时(秒)": e["duration_s"],
                    "交易数": e["tx_count"],
                }
                for e in chain.mining_log
            ]
        )
        st.dataframe(frame, width="stretch", hide_index=True)
        if len(frame) > 1:
            fig = go.Figure(
                go.Bar(
                    x=frame["区块"].astype(str),
                    y=frame["尝试次数"],
                    marker_color="#ef6c00",
                    name="尝试次数",
                )
            )
            fig.update_layout(
                height=300,
                margin=dict(l=10, r=10, t=20, b=10),
                xaxis_title="区块",
                yaxis_title="哈希尝试次数",
            )
            st.plotly_chart(fig, width="stretch")
    else:
        st.info("暂无挖矿记录")


# ── 页面 6：区块浏览器 ──────────────────────────────────────────────────────


def page_explorer() -> None:
    st.header("🧱 区块浏览器")
    chain = get_chain()

    rows = []
    for position, block in enumerate(chain.chain):
        rows.append(
            {
                "高度": position,
                "区块": block.index,
                "交易数": len(block.transactions),
                "难度": block.difficulty,
                "Nonce": block.nonce,
                "时间": datetime.fromtimestamp(block.timestamp).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                "哈希": block.hash[:24] + "…",
                "前一哈希": block.previous_hash[:24] + "…",
            }
        )
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    st.divider()
    options = [b.index for b in chain.chain]
    picked = st.selectbox(
        "查看区块详情", options, format_func=lambda i: f"区块 #{i}"
    )
    block = chain.get_block(picked)
    if block is None:
        st.error("区块不存在")
        return

    cols = st.columns(4)
    cols[0].metric("区块高度", block.index)
    cols[1].metric("交易数", len(block.transactions))
    cols[2].metric("难度", block.difficulty)
    cols[3].metric("Nonce", block.nonce)

    st.markdown("**区块哈希**")
    st.code(block.hash)
    st.markdown("**前一区块哈希**")
    st.code(block.previous_hash)
    st.markdown("**Merkle 根**")
    st.code(block.merkle_root)

    detail = {
        "哈希一致": block.hash == block.calculate_hash(),
        "工作量证明有效": block.satisfies_pow(),
        "Merkle 根一致": block.merkle_root == compute_merkle_root(block.tx_ids),
    }
    st.write(
        " · ".join(f"{key} {bool_cell(value)}" for key, value in detail.items())
    )

    with st.expander("🔬 哈希原文（可复算）", expanded=False):
        st.caption("修改任意字段都会改变下列内容，从而改变区块哈希。")
        st.json(block._hash_payload(block.nonce, block.merkle_root))

    st.divider()
    st.subheader(f"📄 区块内 {len(block.transactions)} 笔交易")
    for position, tx in enumerate(block.transactions):
        with st.expander(
            f"{CHAIN_ICON.get(tx.tx_type, '')} {tx.tx_type_label} · "
            f"{tx.data.get('product_name', '—')} · {tx.tx_id[:16]}…"
        ):
            st.json(tx.to_dict())
            proof = block.proof_for(position)
            st.caption(
                f"Merkle 证明路径长度 {len(proof)}，"
                f"验证结果：{'✅ 通过' if verify_merkle_proof(tx.tx_id, proof, block.merkle_root) else '❌ 失败'}"
            )


# ── 页面 7：链验证与篡改实验 ────────────────────────────────────────────────


def page_verify() -> None:
    st.header("🛡️ 链完整性验证与篡改实验")
    chain = get_chain()

    ok, message = chain.is_chain_valid()
    if ok:
        st.success(message, icon="🔒")
    else:
        st.error(message, icon="🚨")

    st.subheader("🔎 逐块审计")
    audit = chain.audit_chain()
    display = [
        {**row, "哈希": row["哈希"][:24] + "…", "哈希一致": bool_cell(row["哈希一致"]),
         "链接正确": bool_cell(row["链接正确"]), "工作量证明": bool_cell(row["工作量证明"]),
         "Merkle 根": bool_cell(row["Merkle 根"]), "交易合法": bool_cell(row["交易合法"]),
         "通过": bool_cell(row["通过"])}
        for row in audit
    ]
    st.dataframe(pd.DataFrame(display), width="stretch", hide_index=True)

    st.divider()
    st.subheader("🧪 篡改实验")
    st.caption(
        "直接修改链上某笔交易的字段，观察哈希与校验结果如何变化 —— "
        "这就是「不可篡改」的实际含义：内容变则哈希变，哈希变则链断。"
    )

    blocks_with_tx = [b.index for b in chain.chain if b.transactions]
    if not blocks_with_tx:
        st.info("链上没有可篡改的交易")
        return

    col1, col2, col3 = st.columns(3)
    with col1:
        block_index = st.selectbox("选择区块", blocks_with_tx, key="tamper_block")
    block = chain.get_block(block_index)
    if block is None:
        st.error("区块不存在")
        return

    with col2:
        position = st.selectbox(
            "选择交易",
            options=list(range(len(block.transactions))),
            format_func=lambda i: (
                f"{TRANSACTION_TYPES.get(block.transactions[i].tx_type, '')} · "
                f"{block.transactions[i].data.get('product_name', '—')}"
            ),
            key="tamper_pos",
        )
    target = block.transactions[position]

    with col3:
        field = st.selectbox(
            "选择字段", sorted(target.data.keys()), key="tamper_field"
        )

    new_value = st.text_input(
        "篡改为", value="【已被篡改】假冒商品", key="tamper_value"
    )

    act = st.columns(4)
    if act[0].button("💥 执行篡改", type="primary", width="stretch"):
        st.session_state["chain_backup"] = copy.deepcopy(chain)
        result = chain.tamper_transaction(block_index, position, field, new_value)
        st.session_state["tamper_result"] = result
        st.rerun()

    if act[1].button("🔁 恢复篡改前快照", width="stretch"):
        backup = st.session_state.pop("chain_backup", None)
        if backup is None:
            st.warning("没有可恢复的快照")
        else:
            st.session_state["chain"] = backup
            st.session_state.pop("tamper_result", None)
            st.toast("已恢复到篡改前的状态", icon="🔁")
            st.rerun()

    if act[2].button("⛏️ 攻击者重挖本块", width="stretch"):
        with st.spinner("攻击者重算本块的工作量证明…"):
            nonce, attempts = block.mine(block.difficulty)
        st.toast(f"本块已重挖：Nonce={nonce}，尝试 {attempts:,} 次", icon="⛏️")
        st.rerun()

    if act[3].button("💾 保存当前链", width="stretch"):
        persist_chain()

    result = st.session_state.get("tamper_result")
    if result:
        before, after = result["before"], result["after"]
        st.divider()
        st.markdown(f"#### 篡改字段：`{field}`")
        compare = pd.DataFrame(
            [
                {"阶段": "篡改前", "字段值": fmt_value(field, before["value"]),
                 "交易 ID": before["tx_id"][:24] + "…",
                 "区块哈希": before["block_hash"][:24] + "…",
                 "链是否有效": bool_cell(before["chain_valid"])},
                {"阶段": "篡改后", "字段值": fmt_value(field, after["value"]),
                 "交易 ID": after["tx_id"][:24] + "…",
                 "区块哈希": after["block_hash"][:24] + "…",
                 "链是否有效": bool_cell(after["chain_valid"])},
            ]
        )
        st.dataframe(compare, width="stretch", hide_index=True)

        info = st.columns(3)
        tx_changed = before["tx_id"] != after["tx_id"]
        info[0].metric("交易 ID 变化", bool_cell(tx_changed))
        info[1].metric(
            "区块哈希变化",
            bool_cell(before["block_hash"] != after["block_hash"]),
        )
        info[2].metric("链校验结果", bool_cell(after["chain_valid"]))

        if after.get("recalculated_hash"):
            st.markdown("**按篡改后内容重算出的区块哈希**")
            st.code(after["recalculated_hash"])
            st.caption(
                "该哈希与区块中记录的哈希不一致，所以校验立即失败。"
                "若攻击者想让链重新有效，必须重挖本块，并且把后续所有区块的"
                " `previous_hash` 一并重算 —— 这就是篡改成本极高的原因。"
            )


# ── 页面 8：参与方管理 ──────────────────────────────────────────────────────


def page_participants() -> None:
    st.header("🏢 参与方管理")
    chain = get_chain()

    rows = [
        {
            "编号": pid,
            "名称": info.get("name", ""),
            "角色": info.get("role", ""),
            "类型": info.get("type", ""),
            "所在地": info.get("location", ""),
        }
        for pid, info in sorted(chain.participants.items())
    ]
    if rows:
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
        counts: Dict[str, int] = {}
        for row in rows:
            counts[row["角色"]] = counts.get(row["角色"], 0) + 1
        fig = go.Figure(
            go.Bar(
                x=list(counts),
                y=list(counts.values()),
                marker_color="#2e7d32",
                text=list(counts.values()),
                textposition="auto",
            )
        )
        fig.update_layout(
            height=300, margin=dict(l=10, r=10, t=20, b=10), yaxis_title="数量"
        )
        st.plotly_chart(fig, width="stretch")
    else:
        st.info("暂无参与方")

    st.divider()
    st.subheader("➕ 新增参与方")
    with st.form("add_participant"):
        cols = st.columns(2)
        pid = cols[0].text_input("编号", placeholder="例如 farm_005")
        name = cols[1].text_input("名称", placeholder="例如 青山果园")
        cols2 = st.columns(3)
        role = cols2[0].selectbox("角色", options=list(sc.ROLES))
        kind = cols2[1].text_input("类型", placeholder="例如 种植基地")
        location = cols2[2].text_input("所在地", placeholder="例如 山东省烟台市")
        if st.form_submit_button("注册参与方", width="stretch"):
            if not pid or not name:
                st.error("编号与名称必填")
            elif pid in chain.participants:
                st.error(f"参与方 {pid} 已存在")
            else:
                chain.register_participant(
                    pid, name, role, {"type": kind, "location": location}
                )
                persist_chain()
                st.rerun()

    st.subheader("🗑️ 移除参与方")
    removable = sorted(chain.participants)
    if removable:
        pick = st.selectbox(
            "选择要移除的参与方",
            removable,
            format_func=lambda p: f"{chain.participants[p].get('name', '')}（{p}）",
        )
        if st.button("移除", width="stretch"):
            if chain.remove_participant(pick):
                persist_chain()
                st.rerun()
            else:
                st.error("移除失败")


# ── 页面 9：数据分析 ────────────────────────────────────────────────────────


def page_analytics() -> None:
    st.header("📈 数据分析")
    chain = get_chain()

    all_tx = chain.all_transactions()
    if not all_tx:
        st.info("暂无交易数据")
        return

    frame = pd.DataFrame(
        [
            {
                "交易类型": TRANSACTION_TYPES.get(row["tx_type"], row["tx_type"]),
                "产品": row["data"].get("product_name", "—"),
            }
            for row in all_tx
        ]
    )

    left, right = st.columns(2)
    with left:
        st.subheader("交易环节分布")
        counts = frame["交易类型"].value_counts()
        fig = go.Figure(
            go.Bar(
                x=list(counts.index),
                y=list(counts.values),
                marker_color="#1565c0",
                text=list(counts.values),
                textposition="auto",
            )
        )
        fig.update_layout(
            height=320, margin=dict(l=10, r=10, t=20, b=10), yaxis_title="交易数"
        )
        st.plotly_chart(fig, width="stretch")

    with right:
        st.subheader("产品上链完整度")
        completeness = []
        for pid in chain.get_product_list():
            records = chain.trace_product(pid)
            stages = {r["tx_type"] for r in records}
            completeness.append(
                {
                    "产品": records[0]["data"].get("product_name", pid) if records else pid,
                    "环节数": len(stages),
                }
            )
        frame2 = pd.DataFrame(completeness).sort_values("环节数", ascending=False)
        fig2 = go.Figure(
            go.Bar(
                x=frame2["产品"],
                y=frame2["环节数"],
                marker_color="#2e7d32",
                text=frame2["环节数"],
                textposition="auto",
            )
        )
        fig2.update_layout(
            height=320,
            margin=dict(l=10, r=10, t=20, b=10),
            yaxis_title="已上链环节数（满 4）",
        )
        st.plotly_chart(fig2, width="stretch")

    st.divider()
    st.subheader("🌡️ 各产品在途温度曲线")
    temp_fig = go.Figure()
    has_temp = False
    for pid in chain.get_product_list():
        records = chain.trace_product(pid)
        logistics = next((r for r in records if r["tx_type"] == "logistics"), None)
        if logistics is None:
            continue
        report = sc.cold_chain_report(logistics["tx"])
        if not report["readings"]:
            continue
        has_temp = True
        name = logistics["data"].get("product_name", pid)
        temp_fig.add_scatter(
            y=report["readings"], mode="lines+markers", name=name
        )
    if has_temp:
        temp_fig.update_layout(
            height=340,
            margin=dict(l=10, r=10, t=20, b=10),
            yaxis_title="温度 (°C)",
            xaxis_title="采样点",
        )
        st.plotly_chart(temp_fig, width="stretch")
    else:
        st.info("暂无温度采样数据")

    st.divider()
    st.subheader("⛏️ 挖矿效率趋势")
    if chain.mining_log:
        log_frame = pd.DataFrame(chain.mining_log)
        fig3 = go.Figure()
        fig3.add_bar(
            x=log_frame["index"].astype(str),
            y=log_frame["attempts"],
            name="哈希尝试次数",
            marker_color="#ef6c00",
        )
        fig3.add_scatter(
            x=log_frame["index"].astype(str),
            y=log_frame["duration_s"],
            name="耗时（秒）",
            yaxis="y2",
            mode="lines+markers",
            line=dict(color="#6a1b9a", width=2),
        )
        fig3.update_layout(
            height=340,
            margin=dict(l=10, r=10, t=20, b=10),
            yaxis=dict(title="尝试次数"),
            yaxis2=dict(title="耗时（秒）", overlaying="y", side="right"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
            xaxis_title="区块",
        )
        st.plotly_chart(fig3, width="stretch")
    else:
        st.info("暂无挖矿记录")

    st.divider()
    st.subheader("🗂️ 全量交易明细")
    detail_rows = []
    for row in all_tx:
        detail_rows.append(
            {
                "区块": row.get("block_index", "—"),
                "环节": TRANSACTION_TYPES.get(row["tx_type"], row["tx_type"]),
                "产品": row["data"].get("product_name", "—"),
                "交易 ID": row["tx_id"][:20] + "…",
                "时间": row.get("timestamp_str", ""),
            }
        )
    st.dataframe(pd.DataFrame(detail_rows), width="stretch", hide_index=True)


# ── 侧边栏与入口 ────────────────────────────────────────────────────────────

PAGES = {
    "📊 总览看板": page_overview,
    "🔍 产品溯源": page_trace,
    "🧊 冷链与保质期": page_cold_chain,
    "➕ 添加交易": page_add_transaction,
    "⛏️ 挖矿中心": page_mining,
    "🧱 区块浏览器": page_explorer,
    "🛡️ 链验证与篡改实验": page_verify,
    "🏢 参与方管理": page_participants,
    "📈 数据分析": page_analytics,
}


def sidebar() -> str:
    with st.sidebar:
        st.markdown("### 🌾 农产品区块链溯源")
        status_banner()

        chain = get_chain()
        stats = chain.get_chain_stats()
        st.caption(
            f"区块 {stats['block_count']} · 交易 {stats['total_transactions']} · "
            f"产品 {stats['unique_products']} · 待打包 {stats['pending_transactions']}"
        )

        st.divider()
        choice = st.radio("导航", options=list(PAGES), label_visibility="collapsed")

        st.divider()
        with st.expander("⚙️ 链管理", expanded=False):
            if st.button("💾 保存到磁盘", width="stretch"):
                persist_chain()
            if st.button("🔄 从磁盘重新加载", width="stretch"):
                st.session_state.pop("chain", None)
                st.session_state.pop("chain_backup", None)
                st.session_state.pop("tamper_result", None)
                st.rerun()
            st.caption("重建链（当前数据将丢失）")
            if st.button("♻️ 重置为空链", width="stretch"):
                reset_chain(with_demo_data=False)
            if st.button("🌱 重置为演示数据", width="stretch"):
                reset_chain(with_demo_data=True)

        st.divider()
        st.caption(f"📁 数据文件\n\n`{DATA_FILE}`")
        if "persist_error" in st.session_state:
            st.warning(f"持久化不可用：{st.session_state['persist_error']}")

        st.caption(
            f"schema v{SCHEMA_VERSION} · "
            f"难度 {chain.difficulty} · "
            f"{'自动调难度' if chain.auto_adjust else '固定难度'}"
        )
    return choice


def main() -> None:
    choice = sidebar()
    PAGES[choice]()


if __name__ == "__main__":
    main()
