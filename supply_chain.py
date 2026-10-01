"""
供应链业务层 —— 农产品溯源领域知识
==================================

本模块把「业务语义」从「区块链机制」中分离出来：

* :data:`FIELD_LABELS` —— 交易字段的中文标签与单位
* :data:`ROLES`        —— 参与方角色定义与配色
* :data:`SEED_PRODUCTS` —— 演示数据集（**已修正早期版本的地理错误**）
* :func:`build_seed_transactions` —— 生成初始上链交易
* 领域规则：冷链温控合规、保质期预警、质量等级
* :func:`build_trace_html` —— 生成可下载的溯源证书（自包含 HTML）
"""

from __future__ import annotations

import html
import re
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple

from blockchain import Blockchain, Transaction, TRANSACTION_TYPES

__all__ = [
    "FIELD_LABELS",
    "ROLES",
    "ROLE_COLORS",
    "STAGE_ICONS",
    "STAGE_COLORS",
    "SEED_PARTICIPANTS",
    "SEED_PRODUCTS",
    "build_seed_transactions",
    "seed_blockchain",
    "merged_stage",
    "product_id_of",
    "label_for",
    "parse_temperature_range",
    "cold_chain_report",
    "expiry_status",
    "stage_icon",
    "build_trace_html",
]

# ── 展示元数据 ──────────────────────────────────────────────────────────────

STAGE_ICONS: Dict[str, str] = {
    "production": "🌱",
    "processing": "🏭",
    "logistics": "🚚",
    "sale": "🏪",
}

STAGE_COLORS: Dict[str, str] = {
    "production": "#2e7d32",
    "processing": "#1565c0",
    "logistics": "#ef6c00",
    "sale": "#6a1b9a",
}

#: 交易字段 → (中文标签, 单位)
FIELD_LABELS: Dict[str, Tuple[str, str]] = {
    # 公共
    "product_id": ("产品编号", ""),
    "product_name": ("产品名称", ""),
    "category": ("产品类别", ""),
    "notes": ("备注", ""),
    # 生产
    "producer": ("生产者", ""),
    "producer_id": ("生产者编号", ""),
    "origin": ("产地", ""),
    "planting_date": ("种植日期", ""),
    "harvest_date": ("采收日期", ""),
    "batch_number": ("批次号", ""),
    "quality_grade": ("质量等级", ""),
    "certification": ("认证信息", ""),
    "planting_area_mu": ("种植面积", "亩"),
    "soil_ph": ("土壤 pH", ""),
    # 加工
    "processor": ("加工商", ""),
    "processor_id": ("加工商编号", ""),
    "process_type": ("加工类型", ""),
    "processing_date": ("加工日期", ""),
    "expiry_date": ("保质期至", ""),
    "facility": ("加工车间", ""),
    "supervisor": ("负责人", ""),
    "quality_check": ("质检结论", ""),
    "additives": ("添加剂", ""),
    # 物流
    "logistics_provider": ("物流商", ""),
    "logistics_id": ("物流商编号", ""),
    "transport_mode": ("运输方式", ""),
    "departure": ("起运地", ""),
    "destination": ("目的地", ""),
    "shipment_date": ("发运日期", ""),
    "estimated_arrival": ("预计到达", ""),
    "tracking_number": ("运单号", ""),
    "temperature_range": ("温控范围", ""),
    "temperature_readings": ("在途温度采样", "°C"),
    "vehicle_number": ("车牌号", ""),
    # 销售
    "seller": ("销售商", ""),
    "seller_id": ("销售商编号", ""),
    "store": ("销售门店", ""),
    "shelf_date": ("上架日期", ""),
    "selling_price": ("销售价格", ""),
    "stock_quantity": ("库存数量", ""),
    "promotion": ("促销信息", ""),
}

#: 角色定义
ROLES: Dict[str, List[str]] = {
    "生产者": ["种植基地", "养殖场", "家庭农场", "合作社"],
    "加工商": ["初加工厂", "深加工厂", "包装车间", "冷链分拣中心"],
    "物流商": ["冷链物流", "干线运输", "城市配送"],
    "销售商": ["连锁商超", "生鲜电商", "农贸市场", "社区团购"],
    "监管机构": ["市场监管局", "农业农村局", "第三方检测机构"],
}

ROLE_COLORS: Dict[str, str] = {
    "生产者": "#2e7d32",
    "加工商": "#1565c0",
    "物流商": "#ef6c00",
    "销售商": "#6a1b9a",
    "监管机构": "#c62828",
}


def stage_icon(tx_type: str) -> str:
    return STAGE_ICONS.get(tx_type, "📄")


def label_for(field: str) -> str:
    """字段中文标签，未知字段则回退为原始键名。"""
    label, unit = FIELD_LABELS.get(field, (field, ""))
    return f"{label}（{unit}）" if unit else label


# ── 演示数据集 ──────────────────────────────────────────────────────────────
#
# 早期版本的种子数据把「西湖龙井茶叶」的产地写成了黑龙江省五常市，把
# 「有机红富士苹果」也写成五常市 —— 五常以大米闻名，并非苹果与茶叶产区。
# 这里按真实地理重新整理，并补充了温控采样、保质期等可用于分析的字段。

SEED_PARTICIPANTS: List[Dict[str, Any]] = [
    {"id": "farm_001", "name": "阳光生态农场", "role": "生产者", "type": "种植基地", "location": "陕西省延安市洛川县"},
    {"id": "farm_002", "name": "绿源有机农场", "role": "生产者", "type": "种植基地", "location": "黑龙江省哈尔滨市五常市"},
    {"id": "farm_003", "name": "西湖龙井茶园", "role": "生产者", "type": "种植基地", "location": "浙江省杭州市西湖区"},
    {"id": "farm_004", "name": "寿光蔬菜合作社", "role": "生产者", "type": "合作社", "location": "山东省潍坊市寿光市"},
    {"id": "processor_001", "name": "鲜品加工厂", "role": "加工商", "type": "初加工厂", "location": "陕西省延安市"},
    {"id": "processor_002", "name": "绿农食品加工公司", "role": "加工商", "type": "深加工厂", "location": "黑龙江省哈尔滨市"},
    {"id": "logistics_001", "name": "顺达冷链物流", "role": "物流商", "type": "冷链物流", "location": "陕西省西安市"},
    {"id": "logistics_002", "name": "京东冷链运输", "role": "物流商", "type": "冷链物流", "location": "北京市"},
    {"id": "seller_001", "name": "盒马鲜生", "role": "销售商", "type": "生鲜电商", "location": "北京市朝阳区"},
    {"id": "seller_002", "name": "永辉超市", "role": "销售商", "type": "连锁商超", "location": "上海市浦东新区"},
    {"id": "regulator_001", "name": "省农产品质量安全检测中心", "role": "监管机构", "type": "第三方检测机构", "location": "陕西省西安市"},
]

#: 演示数据中的日期一律相对「今天」生成，避免示例一经写死就全部"已过期"。
def _day(offset: int) -> str:
    """相对于今天的日期字符串（负数为过去）。"""
    return (datetime.now() + timedelta(days=offset)).strftime("%Y-%m-%d")


SEED_PRODUCTS: List[Dict[str, Any]] = [
    {
        "production": {
            "product_id": "ORG-APPLE-2025-001",
            "product_name": "有机红富士苹果",
            "category": "水果",
            "producer": "阳光生态农场",
            "producer_id": "farm_001",
            "origin": "陕西省延安市洛川县",
            "planting_date": _day(-300),
            "harvest_date": _day(-25),
            "batch_number": "BATCH-APPLE-1008",
            "quality_grade": "特级",
            "certification": "有机认证 GB/T 19630",
            "planting_area_mu": 120,
            "soil_ph": 7.2,
            "notes": "黄土高原优生区，昼夜温差大，糖度可达 16 度以上",
        },
        "processing": {
            "processor": "鲜品加工厂",
            "processor_id": "processor_001",
            "process_type": "分拣·清洗·打蜡·包装",
            "processing_date": _day(-24),
            "expiry_date": _day(45),
            "facility": "A 区无菌加工车间",
            "batch_number": "PROC-APPLE-1009",
            "supervisor": "李明",
            "quality_check": "已通过食品安全检测",
            "additives": "食品级果蜡（符合 GB 2760）",
        },
        "logistics": {
            "logistics_provider": "顺达冷链物流",
            "logistics_id": "logistics_001",
            "transport_mode": "冷链运输 (0-4°C)",
            "departure": "陕西省延安市",
            "destination": "北京市朝阳区",
            "shipment_date": _day(-23),
            "estimated_arrival": _day(-21),
            "tracking_number": "SF-APPLE-10012",
            "temperature_range": "0~4°C",
            "temperature_readings": [2.4, 1.8, 0.9, 3.2, 2.7],
            "vehicle_number": "陕A·8F2K1",
        },
        "sale": {
            "seller": "盒马鲜生",
            "seller_id": "seller_001",
            "store": "盒马鲜生·北京朝阳店",
            "shelf_date": _day(-20),
            "selling_price": "35元/1kg",
            "stock_quantity": 480,
            "promotion": "新品上市·有机专区",
        },
    },
    {
        "production": {
            "product_id": "ORG-RICE-2025-001",
            "product_name": "五常有机大米",
            "category": "粮食",
            "producer": "绿源有机农场",
            "producer_id": "farm_002",
            "origin": "黑龙江省哈尔滨市五常市",
            "planting_date": _day(-200),
            "harvest_date": _day(-40),
            "batch_number": "BATCH-RICE-0928",
            "quality_grade": "一级",
            "certification": "有机认证 GB/T 19630",
            "planting_area_mu": 300,
            "soil_ph": 6.4,
            "notes": "五常稻花香 2 号，一年一季，采用稻鸭共作模式",
        },
        "processing": {
            "processor": "绿农食品加工公司",
            "processor_id": "processor_002",
            "process_type": "脱壳·碾米·色选·真空包装",
            "processing_date": _day(-38),
            "expiry_date": _day(8),
            "facility": "B 区精米加工车间",
            "batch_number": "PROC-RICE-1002",
            "supervisor": "王强",
            "quality_check": "已通过食品安全检测",
            "additives": "无",
        },
        "logistics": {
            "logistics_provider": "京东冷链运输",
            "logistics_id": "logistics_002",
            "transport_mode": "常温干线运输",
            "departure": "黑龙江省哈尔滨市",
            "destination": "上海市浦东新区",
            "shipment_date": _day(-36),
            "estimated_arrival": _day(-34),
            "tracking_number": "JD-RICE-10047",
            "temperature_range": "常温",
            "temperature_readings": [18.5, 21.2, 19.8, 22.4],
            "vehicle_number": "黑A·3T7Q9",
        },
        "sale": {
            "seller": "永辉超市",
            "seller_id": "seller_002",
            "store": "永辉超市·上海浦东店",
            "shelf_date": _day(-33),
            "selling_price": "12.8元/500g",
            "stock_quantity": 1200,
            "promotion": "满 100 减 20",
        },
    },
    {
        "production": {
            "product_id": "ORG-TEA-2025-001",
            "product_name": "西湖龙井茶叶",
            "category": "茶叶",
            "producer": "西湖龙井茶园",
            "producer_id": "farm_003",
            "origin": "浙江省杭州市西湖区",
            "planting_date": _day(-120),
            "harvest_date": _day(-60),
            "batch_number": "BATCH-TEA-0405",
            "quality_grade": "特级",
            "certification": "地理标志保护产品 GB/T 18650",
            "planting_area_mu": 85,
            "soil_ph": 5.6,
            "notes": "明前头采，一芽一叶初展，手工辉锅",
        },
        "processing": {
            "processor": "绿农食品加工公司",
            "processor_id": "processor_002",
            "process_type": "摊放·杀青·揉捻·辉锅·提香",
            "processing_date": _day(-58),
            "expiry_date": _day(2),
            "facility": "C 区茶叶精制车间",
            "batch_number": "PROC-TEA-0406",
            "supervisor": "陈静",
            "quality_check": "已通过食品安全检测",
            "additives": "无",
        },
        "logistics": {
            "logistics_provider": "顺达冷链物流",
            "logistics_id": "logistics_001",
            "transport_mode": "恒温运输 (5-10°C)",
            "departure": "浙江省杭州市",
            "destination": "北京市朝阳区",
            "shipment_date": _day(-56),
            "estimated_arrival": _day(-54),
            "tracking_number": "SF-TEA-04081",
            "temperature_range": "5~10°C",
            "temperature_readings": [6.2, 7.8, 5.4, 9.6, 8.1],
            "vehicle_number": "浙A·6H4M2",
        },
        "sale": {
            "seller": "盒马鲜生",
            "seller_id": "seller_001",
            "store": "盒马鲜生·北京朝阳店",
            "shelf_date": _day(-53),
            "selling_price": "880元/250g",
            "stock_quantity": 150,
            "promotion": "春茶尝鲜",
        },
    },
    {
        "production": {
            "product_id": "ORG-TOMATO-2025-001",
            "product_name": "有机圣女果",
            "category": "蔬菜",
            "producer": "寿光蔬菜合作社",
            "producer_id": "farm_004",
            "origin": "山东省潍坊市寿光市",
            "planting_date": _day(-90),
            "harvest_date": _day(-6),
            "batch_number": "BATCH-TOMATO-1102",
            "quality_grade": "一级",
            "certification": "绿色食品认证",
            "planting_area_mu": 60,
            "soil_ph": 6.8,
            "notes": "日光温室越冬栽培，熊蜂授粉",
        },
        "processing": {
            "processor": "鲜品加工厂",
            "processor_id": "processor_001",
            "process_type": "分拣·清洗·气调包装",
            "processing_date": _day(-5),
            "expiry_date": _day(-1),
            "facility": "C 区鲜切车间",
            "batch_number": "PROC-TOMATO-1103",
            "supervisor": "赵磊",
            "quality_check": "已通过食品安全检测",
            "additives": "无",
        },
        "logistics": {
            "logistics_provider": "京东冷链运输",
            "logistics_id": "logistics_002",
            "transport_mode": "冷链运输 (0-4°C)",
            "departure": "山东省潍坊市",
            "destination": "上海市浦东新区",
            "shipment_date": _day(-4),
            "estimated_arrival": _day(-3),
            "tracking_number": "JD-TOMATO-11047",
            "temperature_range": "0~4°C",
            "temperature_readings": [3.8, 4.6, 2.1, 5.2, 3.3, 1.7],
            "vehicle_number": "鲁G·9K5D3",
        },
        "sale": {
            "seller": "永辉超市",
            "seller_id": "seller_002",
            "store": "永辉超市·上海浦东店",
            "shelf_date": _day(-2),
            "selling_price": "16.9元/500g",
            "stock_quantity": 320,
            "promotion": "产地直供",
        },
    },
]

#: 每个环节都需要携带的产品身份字段（从 production 环节继承）
_IDENTITY_FIELDS = ("product_id", "product_name", "category")


#: 各环节用于生成交易时间戳的日期字段与时刻
_STAGE_DATE_FIELD = {
    "production": "harvest_date",
    "processing": "processing_date",
    "logistics": "shipment_date",
    "sale": "shelf_date",
}
_STAGE_CLOCK = {
    "production": (9, 0),
    "processing": (10, 30),
    "logistics": (14, 0),
    "sale": (17, 30),
}


def _stage_timestamp(data: Dict[str, Any], tx_type: str) -> float:
    """由业务日期推出交易时间戳，使时间线与数据本身一致。"""
    raw = data.get(_STAGE_DATE_FIELD[tx_type])
    hour, minute = _STAGE_CLOCK[tx_type]
    try:
        base = datetime.strptime(str(raw)[:10], "%Y-%m-%d")
    except (TypeError, ValueError):
        base = datetime.now()
    return base.replace(hour=hour, minute=minute, second=0, microsecond=0).timestamp()


def merged_stage(product: Dict[str, Any], tx_type: str) -> Dict[str, Any]:
    """
    取出某产品某环节的交易数据，并补上产品身份字段。

    种子数据里只有 ``production`` 环节写了 ``product_id``/``product_name``，
    下游环节必须继承这些字段，否则无法按产品建立索引。
    """
    identity = {
        field: product["production"][field]
        for field in _IDENTITY_FIELDS
        if field in product["production"]
    }
    return {**identity, **product[tx_type]}


def product_id_of(product: Dict[str, Any]) -> str:
    """
    取演示产品的主键。

    种子数据的每个产品是一个"按环节分组"的字典
    （``{"production": {...}, "processing": {...}, ...}``），产品编号只写在
    生产环节里；这个方法把那个容易写错的 ``product["production"]["product_id"]``
    收成一个有名字的入口。
    """
    return str(product["production"]["product_id"])


def build_seed_transactions() -> List[Transaction]:
    """按「生产 → 加工 → 物流 → 销售」顺序生成全部演示交易。"""
    transactions: List[Transaction] = []
    for product in SEED_PRODUCTS:
        for tx_type in ("production", "processing", "logistics", "sale"):
            data = merged_stage(product, tx_type)
            transactions.append(
                Transaction(tx_type, data, timestamp=_stage_timestamp(data, tx_type))
            )
    return transactions


def seed_blockchain(miner: str = "system") -> Blockchain:
    """
    创建一条已写入演示数据的新链。

    为了让每个产品恰好落在一个区块里（便于观察），按产品分批挖矿。
    """
    chain = Blockchain()
    for product in SEED_PRODUCTS:
        for tx_type in ("production", "processing", "logistics", "sale"):
            data = merged_stage(product, tx_type)
            chain.add_transaction(
                Transaction(tx_type, data, timestamp=_stage_timestamp(data, tx_type))
            )
        chain.mine_pending_transactions(miner)

    for participant in SEED_PARTICIPANTS:
        chain.register_participant(
            participant["id"],
            participant["name"],
            participant["role"],
            {
                "type": participant.get("type", ""),
                "location": participant.get("location", ""),
            },
        )
    return chain


# ── 领域规则：冷链温控 ──────────────────────────────────────────────────────


def parse_temperature_range(text: Any) -> Optional[Tuple[float, float]]:
    """
    解析 ``"0~4°C"`` / ``"5-10°C"`` / ``"-18--2℃"`` 形式的温控范围。

    .. note::
       ``-`` 既可能是区间分隔符（``5-10``）也可能是负号（``-18--2``），
       因此优先按 ``~`` 等无歧义分隔符切分；只有在没有这类分隔符时，才用
       正则整体匹配「有符号数 - 有符号数」，避免把 ``5-10`` 误读成 ``5`` 和 ``-10``。

    :return: ``(下限, 上限)``，顺序已规范化；"常温" 或无法解析时返回 ``None``。
    """
    if not isinstance(text, str):
        return None

    cleaned = text.replace("℃", "").replace("°C", "").replace("°", "").strip()
    if not cleaned or "常温" in cleaned:
        return None

    for word in ("～", "—", "–", "至", "到"):
        cleaned = cleaned.replace(word, "~")

    if "~" in cleaned:
        left, _, right = cleaned.partition("~")
        try:
            low, high = float(left.strip()), float(right.strip())
        except ValueError:
            return None
    else:
        match = re.fullmatch(
            r"\s*(-?\d+(?:\.\d+)?)\s*-\s*(-?\d+(?:\.\d+)?)\s*", cleaned
        )
        if not match:
            return None
        low, high = float(match.group(1)), float(match.group(2))

    if low > high:
        low, high = high, low
    return low, high


def _as_float(value: Any) -> Optional[float]:
    """
    把一次温度采样值转成 ``float``，无法转换时返回 ``None``。

    兼容表格导入 / 手工填写的字符串形式（``"2.5"``、``"3°C"``），
    并显式排除 ``bool``（它在 Python 里是 ``int`` 的子类，会把 True 当成 1.0）。
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().replace("℃", "").replace("°C", "").replace("°", "")
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _fmt_number(value: float) -> str:
    """用于拼温控范围文本：``0.0 → "0"``、``4.5 → "4.5"``。"""
    return f"{value:g}"


def cold_chain_report(transaction: Transaction) -> Dict[str, Any]:
    """
    冷链温控合规检查。

    无论是否适用，返回值都包含同一组键，不适用的键为 ``None``，
    以免调用方需要按 ``applicable`` 分支处理。

    注意 ``compliant`` 有**三种**取值：``True``（全部达标）、``False``
    （有超限采样）、``None``（没有采样或没有规定温控范围 —— 无法判定，
    既不算达标也不算违规）。

    :return: ``{"applicable", "compliant", "range", "range_text", "low", "high",
        "readings", "min", "max", "average", "violations", "note"}``
    """
    data = transaction.data
    raw_readings = data.get("temperature_readings") or []
    if not isinstance(raw_readings, (list, tuple)):
        raw_readings = []
    numbers = [n for n in (_as_float(r) for r in raw_readings) if n is not None]
    raw_range = data.get("temperature_range")

    bounds = parse_temperature_range(raw_range)
    if not numbers or bounds is None:
        reason = (
            "该环节没有温度采样数据"
            if not numbers
            else "温控范围未规定或无法解析"
        )
        return {
            "applicable": False,
            "compliant": None,
            "range": None,
            "range_text": str(raw_range) if raw_range else "未规定",
            "low": None,
            "high": None,
            "readings": numbers,
            "min": min(numbers) if numbers else None,
            "max": max(numbers) if numbers else None,
            "average": (sum(numbers) / len(numbers)) if numbers else None,
            "violations": [],
            "note": f"{reason}，不做冷链判定",
        }

    low, high = bounds
    violations = [value for value in numbers if value < low or value > high]
    return {
        "applicable": True,
        "compliant": not violations,
        "range": (low, high),
        "range_text": f"{_fmt_number(low)}~{_fmt_number(high)}°C",
        "low": low,
        "high": high,
        "readings": numbers,
        "min": min(numbers),
        "max": max(numbers),
        "average": sum(numbers) / len(numbers),
        "violations": violations,
        "note": (
            "全程温控达标"
            if not violations
            else f"检出 {len(violations)} 次超出温控范围：{violations}"
        ),
    }


# ── 领域规则：保质期 ────────────────────────────────────────────────────────


def expiry_status(expiry_date: Any, reference: Optional[datetime] = None) -> Dict[str, Any]:
    """
    根据保质期截止日期给出预警等级。

    :return: ``{"level", "label", "days", "color", "expiry_date"}``
    """
    reference = reference or datetime.now()
    if not expiry_date:
        return {"level": "unknown", "label": "无保质期信息", "days": None, "color": "#9e9e9e", "expiry_date": None}

    try:
        deadline = datetime.strptime(str(expiry_date)[:10], "%Y-%m-%d")
    except ValueError:
        return {"level": "unknown", "label": "保质期格式无法解析", "days": None, "color": "#9e9e9e", "expiry_date": str(expiry_date)}

    # 按「自然日」相减：到期日当天算 0 天，而不是被时刻截断成负数
    days = (deadline.date() - reference.date()).days
    if days < 0:
        level, label, color = "expired", f"已过期 {abs(days)} 天", "#c62828"
    elif days == 0:
        level, label, color = "critical", "今日到期", "#c62828"
    elif days <= 3:
        level, label, color = "critical", f"仅剩 {days} 天", "#c62828"
    elif days <= 14:
        level, label, color = "warning", f"剩余 {days} 天", "#ef6c00"
    else:
        level, label, color = "ok", f"剩余 {days} 天", "#2e7d32"

    return {"level": level, "label": label, "days": days, "color": color, "expiry_date": deadline.strftime("%Y-%m-%d")}


# ── 溯源证书（可下载 HTML）──────────────────────────────────────────────────


def _render_stage_card(record: Dict[str, Any]) -> str:
    tx_type = record["tx_type"]
    color = STAGE_COLORS.get(tx_type, "#455a64")
    icon = stage_icon(tx_type)

    rows: List[str] = []
    skip = {"product_id", "product_name", "category"}
    for field, value in record["data"].items():
        if field in skip:
            continue
        if isinstance(value, (list, tuple)):
            value = "，".join(f"{v}°C" if isinstance(v, (int, float)) else str(v) for v in value)
        label, unit = FIELD_LABELS.get(field, (field, ""))
        display = f"{value}{unit}" if unit and value not in (None, "") else value
        rows.append(
            f'<tr><th>{html.escape(str(label))}</th>'
            f"<td>{html.escape(str(display))}</td></tr>"
        )

    return f"""
    <div class="stage" style="border-left:5px solid {color}">
      <div class="stage-head">
        <span class="icon">{icon}</span>
        <span class="title" style="color:{color}">{html.escape(record['tx_type_label'])}</span>
        <span class="badge">区块 #{record['block_index']}</span>
        <span class="time">{html.escape(record['timestamp_str'])}</span>
      </div>
      <table class="fields">{''.join(rows)}</table>
      <div class="hashline">
        交易ID <code>{html.escape(record['tx_id'][:32])}…</code>
        &nbsp;·&nbsp; 区块哈希 <code>{html.escape(record['block_hash'][:32])}…</code>
      </div>
    </div>"""


def build_trace_html(
    blockchain: Blockchain,
    product_id: str,
    records: List[Dict[str, Any]],
) -> str:
    """
    生成一份自包含的溯源证书 HTML（可直接下载、离线查看、打印为 PDF）。

    证书内含每条记录的区块位置与哈希前缀，读者可回到系统中逐条核对。
    """
    if not records:
        raise ValueError(f"产品 {product_id} 没有溯源记录")

    head = records[0]["data"]
    valid, message = blockchain.is_chain_valid()
    generated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    integrity_color = "#2e7d32" if valid else "#c62828"
    integrity_text = "校验通过" if valid else "校验失败"

    # 冷链合规汇总
    cold_items: List[str] = []
    for record in records:
        if record["tx_type"] != "logistics":
            continue
        report = cold_chain_report(record["tx"])
        if report["applicable"]:
            color = "#2e7d32" if report["compliant"] else "#c62828"
            cold_items.append(
                f'<li style="color:{color}">温控范围 {html.escape(str(report["range_text"]))}：'
                f'{html.escape(report["note"])}'
                f'（实测 {min(report["readings"]):.1f}~{max(report["readings"]):.1f}°C，'
                f'均值 {report["average"]:.1f}°C）</li>'
            )
    cold_block = (
        f"<ul>{''.join(cold_items)}</ul>" if cold_items else "<p>该产品未采用温控运输。</p>"
    )

    # 保质期
    expiry_rows: List[str] = []
    for record in records:
        deadline = record["data"].get("expiry_date")
        if deadline:
            status = expiry_status(deadline)
            expiry_rows.append(
                f'<tr><th>保质期至</th><td>{html.escape(str(deadline))}</td>'
                f'<td style="color:{status["color"]}">{html.escape(status["label"])}</td></tr>'
            )

    stages = "".join(_render_stage_card(record) for record in records)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>溯源证书 · {html.escape(str(head.get("product_name", product_id)))}</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ font-family: "Microsoft YaHei", "PingFang SC", system-ui, sans-serif;
         margin: 0; padding: 40px 24px; background: #f4f6f8; color: #212121; }}
  .sheet {{ max-width: 920px; margin: 0 auto; background: #fff; border-radius: 12px;
            padding: 40px; box-shadow: 0 4px 24px rgba(0,0,0,.08); }}
  h1 {{ margin: 0 0 4px; font-size: 1.9rem; }}
  .sub {{ color: #607d8b; font-size: .9rem; margin-bottom: 24px; }}
  .meta {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
           gap: 12px; margin: 20px 0 28px; }}
  .meta div {{ background: #f7f9fa; border-radius: 8px; padding: 12px 14px; }}
  .meta b {{ display: block; color: #78909c; font-weight: 500; font-size: .78rem;
             letter-spacing: .04em; text-transform: uppercase; margin-bottom: 4px; }}
  .meta span {{ font-size: 1.05rem; font-weight: 600; }}
  h2 {{ font-size: 1.1rem; border-left: 4px solid #2e7d32; padding-left: 10px;
        margin: 32px 0 16px; }}
  .stage {{ background: #fbfcfd; border-radius: 8px; padding: 16px 18px;
            margin-bottom: 14px; }}
  .stage-head {{ display: flex; align-items: center; gap: 10px; margin-bottom: 10px;
                 flex-wrap: wrap; }}
  .icon {{ font-size: 1.3rem; }}
  .title {{ font-weight: 700; font-size: 1.05rem; }}
  .badge {{ background: #eceff1; color: #455a64; border-radius: 999px;
            padding: 2px 10px; font-size: .75rem; }}
  .time {{ color: #90a4ae; font-size: .8rem; margin-left: auto; }}
  table.fields {{ width: 100%; border-collapse: collapse; font-size: .88rem; }}
  table.fields th {{ text-align: left; color: #607d8b; font-weight: 500;
                     padding: 4px 12px 4px 0; width: 130px; vertical-align: top; }}
  table.fields td {{ padding: 4px 0; }}
  .hashline {{ margin-top: 10px; font-size: .72rem; color: #90a4ae; word-break: break-all; }}
  code {{ background: #eceff1; border-radius: 3px; padding: 1px 4px; }}
  .integrity {{ background: #f7f9fa; border-radius: 8px; padding: 14px 16px;
                font-size: .9rem; }}
  .footer {{ margin-top: 36px; padding-top: 16px; border-top: 1px dashed #cfd8dc;
             color: #90a4ae; font-size: .78rem; text-align: center; }}
</style>
</head>
<body>
<div class="sheet">
  <h1>🌾 农产品区块链溯源证书</h1>
  <div class="sub">Agricultural Product Blockchain Traceability Certificate</div>

  <div class="meta">
    <div><b>产品名称</b><span>{html.escape(str(head.get("product_name", "-")))}</span></div>
    <div><b>产品编号</b><span>{html.escape(str(head.get("product_id", "-")))}</span></div>
    <div><b>产品类别</b><span>{html.escape(str(head.get("category", "-")))}</span></div>
    <div><b>产地</b><span>{html.escape(str(head.get("origin", "-")))}</span></div>
    <div><b>溯源环节</b><span>{len(records)} 条记录</span></div>
    <div><b>生成时间</b><span>{generated}</span></div>
  </div>

  <h2>🔗 链上完整性</h2>
  <div class="integrity">
    整链状态：<b style="color:{integrity_color}">{integrity_text}</b> —— {html.escape(message)}<br>
    当前区块高度 <b>{len(blockchain.chain)}</b>，全网难度 <b>{blockchain.difficulty}</b>。
  </div>

  <h2>🕓 供应链全流程</h2>
  {stages}

  <h2>🌡️ 冷链温控合规</h2>
  {cold_block}

  <h2>⏳ 保质期信息</h2>
  <table class="fields">{''.join(expiry_rows) or '<tr><td>无保质期记录</td></tr>'}</table>

  <div class="footer">
    本证书由农产品区块链溯源系统自动生成 · 所有记录均以哈希方式锚定在区块链上<br>
    任何对历史数据的修改都会导致哈希校验失败，可通过系统「链验证」页面复核
  </div>
</div>
</body>
</html>"""
