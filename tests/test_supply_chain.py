# -*- coding: utf-8 -*-
"""
supply_chain.py（业务/领域层）的回归测试。

覆盖三块容易出错的地方：
* 种子演示数据本身是否自洽（地理、上下游字段继承、每个产品四段齐全）；
* 温控区间解析与冷链合规判定的边界（负数、区间符 vs 负号、常温）；
* 保质期预警分级是否按自然日计算（曾经被时刻截断，导致"仅剩 1 天"）。
"""

import os
import re
import sys
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from blockchain import Blockchain, Transaction  # noqa: E402
from supply_chain import (  # noqa: E402
    FIELD_LABELS,
    SEED_PARTICIPANTS,
    SEED_PRODUCTS,
    build_seed_transactions,
    build_trace_html,
    cold_chain_report,
    expiry_status,
    label_for,
    merged_stage,
    parse_temperature_range,
    product_id_of,
    seed_blockchain,
    stage_icon,
)

class TestFieldLabels(unittest.TestCase):
    def test_every_seed_field_has_a_label(self):
        """Any field rendered in the UI must have a Chinese label + unit."""
        missing = set()
        for product in SEED_PRODUCTS:
            for tx_type in ("production", "processing", "logistics", "sale"):
                for field in merged_stage(product, tx_type):
                    if field not in FIELD_LABELS:
                        missing.add(field)
        self.assertEqual(missing, set(), f"缺少中文标签的字段: {sorted(missing)}")

    def test_label_includes_unit(self):
        self.assertEqual(label_for("temperature_readings"), "在途温度采样（°C）")
        self.assertNotIn("（", label_for("notes"))

    def test_unknown_field_falls_back_to_raw_name(self):
        self.assertEqual(label_for("totally_unknown_key"), "totally_unknown_key")

    def test_stage_icon_has_default(self):
        self.assertEqual(stage_icon("production"), "🌱")
        self.assertEqual(stage_icon("nope"), "📄")


class TestSeedData(unittest.TestCase):
    def test_four_products(self):
        self.assertEqual(len(SEED_PRODUCTS), 4)
        ids = [product_id_of(p) for p in SEED_PRODUCTS]
        self.assertEqual(len(set(ids)), 4, "产品编号必须唯一")

    def test_origins_are_geographically_correct(self):
        """回归：早期版本把苹果和茶叶的产地都写成「黑龙江省五常市」。"""
        origins = {product_id_of(p): p["production"]["origin"] for p in SEED_PRODUCTS}
        self.assertIn("陕西", origins["ORG-APPLE-2025-001"])
        self.assertIn("浙江", origins["ORG-TEA-2025-001"])
        self.assertIn("黑龙江", origins["ORG-RICE-2025-001"])
        self.assertIn("山东", origins["ORG-TOMATO-2025-001"])

    def test_stage_dates_are_chronological(self):
        for product in SEED_PRODUCTS:
            dates = [
                merged_stage(product, t)[field]
                for t, field in (
                    ("production", "harvest_date"),
                    ("processing", "processing_date"),
                    ("logistics", "shipment_date"),
                    ("sale", "shelf_date"),
                )
            ]
            self.assertEqual(
                dates, sorted(dates), f"{product_id_of(product)} 环节顺序颠倒"
            )

    def test_producer_participants_exist(self):
        known = {p["id"] for p in SEED_PARTICIPANTS}
        for product in SEED_PRODUCTS:
            for tx_type in ("production", "processing", "logistics", "sale"):
                data = merged_stage(product, tx_type)
                for key in ("producer_id", "processor_id", "logistics_id", "seller_id"):
                    if key in data and data[key]:
                        self.assertIn(data[key], known, f"{key}={data[key]} 不在参与方清单")


class TestMergedStage(unittest.TestCase):
    def test_identity_fields_are_inherited(self):
        """下游环节必须继承 product_id / product_name / category。"""
        product = SEED_PRODUCTS[0]
        for tx_type in ("processing", "logistics", "sale"):
            data = merged_stage(product, tx_type)
            self.assertEqual(data["product_id"], product_id_of(product))
            self.assertEqual(data["product_name"], product["production"]["product_name"])
            self.assertEqual(data["category"], product["production"]["category"])

    def test_merged_stage_passes_validation(self):
        for product in SEED_PRODUCTS:
            for tx_type in ("production", "processing", "logistics", "sale"):
                tx = Transaction(tx_type, merged_stage(product, tx_type))
                ok, problems = tx.validate()
                self.assertTrue(ok, f"{product_id_of(product)}/{tx_type}: {problems}")

    def test_merged_stage_does_not_mutate_source(self):
        product = SEED_PRODUCTS[0]
        before = len(product["processing"])
        merged_stage(product, "processing")
        self.assertEqual(len(product["processing"]), before)


class TestSeedBlockchain(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.chain = seed_blockchain()
        cls.stats = cls.chain.get_chain_stats()

    def test_chain_is_valid(self):
        ok, message = self.chain.is_chain_valid()
        self.assertTrue(ok, message)

    def test_one_block_per_product(self):
        self.assertEqual(self.stats["block_count"], len(SEED_PRODUCTS) + 1)

    def test_every_product_has_four_records(self):
        for product in SEED_PRODUCTS:
            records = self.chain.trace_product(product_id_of(product))
            self.assertEqual(len(records), 4, product_id_of(product))
            self.assertEqual(
                [r["tx_type"] for r in records],
                ["production", "processing", "logistics", "sale"],
            )

    def test_business_transaction_count(self):
        """4 个产品 × 4 个环节；创世占位交易不应计入。"""
        self.assertEqual(self.stats["total_transactions"], len(SEED_PRODUCTS) * 4)

    def test_participants_registered_flat(self):
        self.assertEqual(len(self.chain.participants), len(SEED_PARTICIPANTS))
        for participant in SEED_PARTICIPANTS:
            record = self.chain.participants[participant["id"]]
            self.assertEqual(record["name"], participant["name"])
            self.assertEqual(record["role"], participant["role"])
            self.assertIn("registered_at", record)

    def test_demo_covers_all_expiry_levels(self):
        levels = set()
        for product in SEED_PRODUCTS:
            expiry = merged_stage(product, "processing").get("expiry_date")
            levels.add(expiry_status(expiry)["level"])
        self.assertTrue(
            {"ok", "warning", "critical", "expired"} <= levels,
            f"演示数据应覆盖全部预警等级，实际只有 {sorted(levels)}",
        )

    def test_demo_includes_a_cold_chain_violation(self):
        complaints = [
            cold_chain_report(self._last("logistics", product))
            for product in SEED_PRODUCTS
        ]
        self.assertTrue(
            any(r["applicable"] and not r["compliant"] for r in complaints),
            "演示数据应至少包含一例冷链违规，否则看不出告警效果",
        )

    def _last(self, tx_type, product):
        for record in reversed(self.chain.trace_product(product_id_of(product))):
            if record["tx_type"] == tx_type:
                return record["tx"]
        raise AssertionError(f"未找到 {product_id_of(product)} 的 {tx_type} 记录")

    def test_build_seed_transactions_is_pure(self):
        self.assertEqual(len(build_seed_transactions()), len(SEED_PRODUCTS) * 4)


class TestParseTemperatureRange(unittest.TestCase):
    def test_common_formats(self):
        cases = {
            "0~4°C": (0.0, 4.0),
            "0-4℃": (0.0, 4.0),
            "0—4°C": (0.0, 4.0),
            "5-10°C": (5.0, 10.0),   # 回归：曾被解析成 (-10.0, 5.0)
            "-18--2℃": (-18.0, -2.0),
            "-18~-2℃": (-18.0, -2.0),
            "18到22°C": (18.0, 22.0),
            " 0 ~ 4 °C ": (0.0, 4.0),
        }
        for text, expected in cases.items():
            self.assertEqual(parse_temperature_range(text), expected, text)

    def test_single_sided_returns_none(self):
        for text in ("常温", "", None, "低温", "0°C", "abc"):
            self.assertIsNone(parse_temperature_range(text), repr(text))

    def test_reversed_range_is_normalised(self):
        self.assertEqual(parse_temperature_range("10~0°C"), (0.0, 10.0))


class TestColdChainReport(unittest.TestCase):
    def _make(self, **data):
        payload = {
            "product_id": "P1",
            "product_name": "产品",
            "logistics_provider": "物流",
            "departure": "A",
            "destination": "B",
        }
        payload.update(data)
        return Transaction("logistics", payload)

    def test_shape_is_identical_when_not_applicable(self):
        """回归：不适用分支曾经缺少 min/max/average，页面直接 KeyError。"""
        report = cold_chain_report(self._make(temperature_range="常温"))
        for key in (
            "applicable", "compliant", "range", "range_text", "low", "high",
            "readings", "min", "max", "average", "violations", "note",
        ):
            self.assertIn(key, report)
        self.assertFalse(report["applicable"])
        self.assertIsNone(report["min"])
        self.assertIsNone(report["max"])
        self.assertIsNone(report["average"])
        self.assertIsNone(report["range"])

    def test_compliant_readings(self):
        report = cold_chain_report(
            self._make(temperature_range="0~4°C", temperature_readings=[1.0, 2.5, 3.9])
        )
        self.assertTrue(report["applicable"])
        self.assertTrue(report["compliant"])
        self.assertEqual(report["violations"], [])
        self.assertEqual(report["range_text"], "0~4°C")
        self.assertAlmostEqual(report["average"], 2.47, places=2)
        self.assertAlmostEqual(report["min"], 1.0)
        self.assertAlmostEqual(report["max"], 3.9)

    def test_violations_are_listed(self):
        report = cold_chain_report(
            self._make(temperature_range="0~4°C", temperature_readings=[1.0, 8.0, -3.0])
        )
        self.assertFalse(report["compliant"])
        self.assertEqual(report["violations"], [8.0, -3.0])

    def test_missing_readings_cannot_be_judged(self):
        """没有采样数据就没有结论：applicable=False 且 compliant=None。"""
        report = cold_chain_report(self._make(temperature_range="0~4°C"))
        self.assertFalse(report["applicable"])
        self.assertIsNone(report["compliant"])
        self.assertEqual(report["readings"], [])
        self.assertIn("没有温度采样数据", report["note"])

    def test_string_readings_are_coerced(self):
        report = cold_chain_report(
            self._make(temperature_range="0~4°C", temperature_readings=["2.0", "3"])
        )
        self.assertEqual(report["readings"], [2.0, 3.0])


class TestExpiryStatus(unittest.TestCase):
    def setUp(self):
        self.today = datetime(2026, 5, 10, 23, 30)

    def _status(self, day_offset):
        target = (self.today + timedelta(days=day_offset)).strftime("%Y-%m-%d")
        return expiry_status(target, reference=self.today)

    def test_levels_by_offset(self):
        expected = {
            30: "ok",
            15: "ok",
            14: "warning",
            4: "warning",
            3: "critical",
            1: "critical",
            0: "critical",
            -1: "expired",
            -40: "expired",
        }
        for offset, level in expected.items():
            self.assertEqual(self._status(offset)["level"], level, f"offset={offset}")

    def test_days_are_natural_days(self):
        """回归：按时刻相减会把「明天到期」算成仅剩 1 天、当天算成负数。"""
        self.assertEqual(self._status(0)["days"], 0)
        self.assertEqual(self._status(1)["days"], 1)
        self.assertEqual(self._status(-2)["days"], -2)

    def test_today_is_critical_with_its_own_label(self):
        status = self._status(0)
        self.assertEqual(status["label"], "今日到期")
        self.assertEqual(status["level"], "critical")

    def test_expired_label_shows_magnitude(self):
        self.assertEqual(self._status(-5)["label"], "已过期 5 天")

    def test_missing_or_bad_date(self):
        for value in (None, ""):
            self.assertEqual(expiry_status(value)["level"], "unknown")
        self.assertEqual(expiry_status("not-a-date")["level"], "unknown")

    def test_iso_datetime_is_accepted(self):
        self.assertEqual(
            expiry_status("2026-05-15T00:00:00", reference=self.today)["days"], 5
        )


class TestTraceHtml(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.chain = seed_blockchain()
        cls.product = SEED_PRODUCTS[0]
        cls.product_id = product_id_of(cls.product)

    def test_html_is_self_contained(self):
        records = self.chain.trace_product(self.product_id)
        html = build_trace_html(self.chain, self.product_id, records)
        self.assertTrue(html.lstrip().lower().startswith("<!doctype html"))
        self.assertIn("<style", html)
        self.assertNotIn("<script src=", html.lower())
        self.assertNotIn("http://", html)

    def test_html_mentions_product_and_stages(self):
        records = self.chain.trace_product(self.product_id)
        html = build_trace_html(self.chain, self.product_id, records)
        self.assertIn(self.product["production"]["product_name"], html)
        for label in ("生产记录", "加工记录", "物流记录", "销售记录"):
            self.assertIn(label, html)
        self.assertIn(self.chain.chain[1].hash[:16], html)

    def test_html_has_no_replacement_characters(self):
        """整个项目曾因编码损坏出现大量 U+FFFD，这里做一次兜底体检。"""
        records = self.chain.trace_product(self.product_id)
        html = build_trace_html(self.chain, self.product_id, records)
        self.assertNotIn("\ufffd", html)

    def test_html_escapes_untrusted_values(self):
        tx = Transaction(
            "production",
            {
                "product_id": "EVIL-001",
                "product_name": "<img src=x onerror=alert(1)>",
                "producer": "农场",
                "origin": "产地",
            },
            timestamp=1700000000,
        )
        chain = Blockchain()
        chain.add_transaction(tx)
        chain.mine_pending_transactions()
        html = build_trace_html(chain, "EVIL-001", chain.trace_product("EVIL-001"))
        self.assertNotIn("<img src=x", html)
        self.assertIn("&lt;img", html)


class TestNoEncodingDamage(unittest.TestCase):
    def test_source_files_have_no_replacement_character(self):
        """回归：早期 app.py 含 201 个 U+FFFD，全部中文丢失且无法恢复。"""
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for name in ("app.py", "blockchain.py", "supply_chain.py"):
            with open(os.path.join(root, name), encoding="utf-8") as handle:
                text = handle.read()
            self.assertNotIn("\ufffd", text, f"{name} 出现替换字符（编码损坏）")

    def test_no_escaped_unicode_sequences_in_source(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for name in ("app.py", "blockchain.py", "supply_chain.py"):
            with open(os.path.join(root, name), encoding="utf-8") as handle:
                text = handle.read()
            bad = re.findall(r"\\u[0-9a-fA-F]{4}", text)
            self.assertEqual(bad, [], f"{name} 含转义的中文序列: {bad[:5]}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
