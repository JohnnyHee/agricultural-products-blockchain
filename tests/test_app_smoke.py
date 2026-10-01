# -*- coding: utf-8 -*-
"""
app.py 的无头冒烟测试。

用 Streamlit 官方的 ``AppTest`` 在**不启动浏览器**的情况下真实执行 app.py，
逐个切换侧边栏页面并断言没有任何异常抛出。这能挡住绝大多数"某个页面在
某个数据状态下直接崩掉"的问题（例如早期版本的冷链页因为报告结构不齐而
抛 ``KeyError: 'min'``）。

为了让测试不碰用户真实的链数据，测试期间通过环境变量
``AGRI_CHAIN_DATA_DIR`` 把数据目录指向一个临时目录。
"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app.py")

#: 侧边栏里应该出现的页面（顺序与 app.py 的 PAGES 一致）
EXPECTED_PAGES = [
    "📊 总览看板",
    "🔍 产品溯源",
    "🧊 冷链与保质期",
    "➕ 添加交易",
    "⛏️ 挖矿中心",
    "🧱 区块浏览器",
    "🛡️ 链验证与篡改实验",
    "🏢 参与方管理",
    "📈 数据分析",
]


def _load_app_test():
    try:
        from streamlit.testing.v1 import AppTest
    except ImportError:  # pragma: no cover - 老版本 streamlit
        return None
    return AppTest


class TestAppSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.AppTest = _load_app_test()
        cls.tmpdir = tempfile.mkdtemp(prefix="agri-app-test-")
        cls._previous = os.environ.get("AGRI_CHAIN_DATA_DIR")
        os.environ["AGRI_CHAIN_DATA_DIR"] = cls.tmpdir
        cls.at = cls.AppTest.from_file(APP, default_timeout=180)
        cls.at.run()

    @classmethod
    def tearDownClass(cls):
        if cls._previous is None:
            os.environ.pop("AGRI_CHAIN_DATA_DIR", None)
        else:
            os.environ["AGRI_CHAIN_DATA_DIR"] = cls._previous
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def setUp(self):
        if self.AppTest is None:
            self.skipTest("当前 streamlit 版本没有 streamlit.testing.v1.AppTest")

    def _goto(self, page):
        self.at.sidebar.radio[0].set_value(page).run()
        return self.at

    def test_streamlit_available(self):
        from streamlit.testing.v1 import AppTest  # noqa: F401

    def test_data_dir_is_the_isolated_temp_dir(self):
        self.assertTrue(
            os.path.exists(os.path.join(self.tmpdir, "blockchain.json")),
            "app.py 应该在建链后把数据写进 AGRI_CHAIN_DATA_DIR",
        )

    def test_current_page_has_no_exception(self):
        self.assertEqual([str(e) for e in self.at.exception], [])

    def test_sidebar_lists_every_page(self):
        options = list(self.at.sidebar.radio[0].options)
        self.assertEqual(options, EXPECTED_PAGES)

    def test_demo_data_loaded(self):
        """首屏应已生成演示链：5 个区块（创世 + 4 个产品）。"""
        from blockchain import Blockchain
        from blockchain import resolve_data_dir

        chain = Blockchain.load_from_file(
            str(resolve_data_dir(os.environ["AGRI_CHAIN_DATA_DIR"]) / "blockchain.json")
        )
        self.assertIsNotNone(chain)
        self.assertEqual(len(chain.chain), 5)
        self.assertTrue(chain.is_chain_valid()[0])
        self.assertEqual(len(chain.get_product_list()), 4)

    def test_every_page_renders_without_exception(self):
        problems = []
        for page in EXPECTED_PAGES:
            at = self._goto(page)
            errors = [str(e) for e in at.exception]
            if errors:
                problems.append(f"{page}: {errors}")
        self.assertEqual(problems, [])

    def test_no_replacement_characters_in_rendered_titles(self):
        """回归：早期 app.py 有 201 个 U+FFFD，中文全部损坏。"""
        for page in EXPECTED_PAGES:
            self.assertNotIn("\ufffd", page)
        for at_page in list(self.at.sidebar.radio[0].options):
            self.assertNotIn("\ufffd", at_page)

    def test_mining_page_exposes_controls(self):
        at = self._goto("⛏️ 挖矿中心")
        self.assertGreaterEqual(len(at.slider), 1)
        self.assertGreaterEqual(len(at.checkbox), 1)

    def test_tamper_lab_has_controls(self):
        at = self._goto("🛡️ 链验证与篡改实验")
        self.assertGreaterEqual(len(at.button), 1)
        self.assertGreaterEqual(len(at.selectbox) + len(at.multiselect), 1)

    def test_add_transaction_page_has_form(self):
        at = self._goto("➕ 添加交易")
        self.assertGreaterEqual(len(at.text_input), 1)

    def test_analytics_page_builds_dataframes(self):
        at = self._goto("📈 数据分析")
        self.assertEqual([str(e) for e in at.exception], [])
        self.assertGreaterEqual(len(at.dataframe) + len(at.table), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
