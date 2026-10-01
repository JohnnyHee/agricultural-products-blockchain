# -*- coding: utf-8 -*-
"""
blockchain.py 的回归测试。

重点覆盖早期版本中被证实存在的四个缺陷：
1. ``Transaction.tx_id`` 被缓存 —— 改 ``data`` 后哈希不变，篡改无法检出；
2. 区块哈希只提交 ``tx_id`` 列表，不含交易内容；
3. 创世区块未挖矿，且 ``is_chain_valid`` 从 index 1 起校验，掩盖了这一点；
4. ``mine_pending_transactions`` 对每笔交易都追加一次区块下标，
   导致 ``trace_product`` 把同一笔记录重复返回（4 笔交易 → 16 条）。
"""

import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from blockchain import (  # noqa: E402
    GENESIS_PREV_HASH,
    SCHEMA_VERSION,
    Block,
    Blockchain,
    Transaction,
    canonical_json,
    compute_merkle_root,
    is_dir_writable,
    merkle_proof,
    sha256_hex,
    verify_merkle_proof,
)


def make_tx(index: int = 1, **overrides) -> Transaction:
    data = {
        "product_id": f"TEST-{index:03d}",
        "product_name": f"测试产品{index}",
        "producer": "测试农场",
        "origin": "测试产地",
    }
    data.update(overrides)
    return Transaction("production", data, timestamp=1700000000 + index)


class TestCanonicalJson(unittest.TestCase):
    def test_key_order_is_irrelevant(self):
        self.assertEqual(
            canonical_json({"b": 1, "a": 2}), canonical_json({"a": 2, "b": 1})
        )

    def test_chinese_is_not_escaped(self):
        self.assertIn("苹果", canonical_json({"n": "苹果"}))

    def test_sha256_is_deterministic(self):
        self.assertEqual(sha256_hex("abc"), sha256_hex("abc"))
        self.assertEqual(len(sha256_hex("abc")), 64)


class TestTransaction(unittest.TestCase):
    def test_tx_id_reacts_to_data_change(self):
        """回归：tx_id 曾经在 __init__ 中缓存，改 data 后哈希不变。"""
        tx = make_tx(1)
        before = tx.tx_id
        tx.data["product_name"] = "被篡改的产品"
        self.assertNotEqual(before, tx.tx_id)

    def test_tx_id_is_stable_without_change(self):
        tx = make_tx(2)
        self.assertEqual(tx.tx_id, tx.tx_id)
        self.assertEqual(tx.tx_id, tx.compute_tx_id())

    def test_equal_content_gives_equal_id(self):
        self.assertEqual(make_tx(3).tx_id, make_tx(3).tx_id)

    def test_different_timestamp_gives_different_id(self):
        a = Transaction("production", {"product_id": "X", "product_name": "X",
                                       "producer": "P", "origin": "O"}, timestamp=1)
        b = Transaction("production", {"product_id": "X", "product_name": "X",
                                       "producer": "P", "origin": "O"}, timestamp=2)
        self.assertNotEqual(a.tx_id, b.tx_id)

    def test_invalid_type_rejected(self):
        with self.assertRaises(ValueError):
            Transaction("unknown_type", {})

    def test_non_dict_data_rejected(self):
        with self.assertRaises(TypeError):
            Transaction("production", ["not", "a", "dict"])

    def test_validate_reports_missing_fields(self):
        tx = Transaction("production", {"product_id": "X"})
        self.assertEqual(
            set(tx.missing_fields()), {"product_name", "producer", "origin"}
        )
        ok, problems = tx.validate()
        self.assertFalse(ok)
        self.assertEqual(len(problems), 1)
        for field in ("product_name", "producer", "origin"):
            self.assertIn(field, problems[0])

    def test_validate_accepts_complete_payload(self):
        ok, problems = make_tx(4).validate()
        self.assertTrue(ok, problems)

    def test_roundtrip_dict(self):
        tx = make_tx(5)
        restored = Transaction.from_dict(tx.to_dict())
        self.assertEqual(tx.tx_id, restored.tx_id)
        self.assertEqual(tx.data, restored.data)

    def test_zero_timestamp_is_preserved(self):
        """回归：``timestamp or time.time()`` 会把 0 当成缺省值。"""
        tx = Transaction("production", {"product_id": "X", "product_name": "X",
                                        "producer": "P", "origin": "O"}, timestamp=0)
        self.assertEqual(tx.timestamp, 0.0)
        self.assertEqual(Transaction.from_dict(tx.to_dict()).timestamp, 0.0)

    def test_numpy_like_scalars_are_normalised(self):
        class Scalar:
            def __init__(self, value):
                self.value = value

            def item(self):
                return self.value

        tx = Transaction("production", {
            "product_id": "X", "product_name": "X", "producer": "P", "origin": "O",
            "area": Scalar(12.5),
        })
        self.assertEqual(tx.data["area"], 12.5)


class TestMerkle(unittest.TestCase):
    def test_empty_root_is_stable(self):
        self.assertEqual(compute_merkle_root([]), compute_merkle_root([]))

    def test_single_leaf_root_equals_leaf(self):
        self.assertEqual(compute_merkle_root(["aa"]), sha256_hex("aa"))

    def test_root_changes_with_content(self):
        self.assertNotEqual(compute_merkle_root(["a", "b"]),
                            compute_merkle_root(["a", "c"]))

    def test_root_is_order_sensitive(self):
        self.assertNotEqual(compute_merkle_root(["a", "b"]),
                            compute_merkle_root(["b", "a"]))

    def test_proof_for_every_leaf(self):
        for size in (1, 2, 3, 5, 8, 17):
            ids = [sha256_hex(f"leaf-{i}") for i in range(size)]
            root = compute_merkle_root(ids)
            for index, leaf in enumerate(ids):
                proof = merkle_proof(ids, index)
                self.assertTrue(
                    verify_merkle_proof(leaf, proof, root),
                    f"size={size} index={index}",
                )

    def test_proof_rejects_wrong_leaf(self):
        ids = [sha256_hex(f"leaf-{i}") for i in range(4)]
        root = compute_merkle_root(ids)
        proof = merkle_proof(ids, 0)
        self.assertFalse(verify_merkle_proof(sha256_hex("forged"), proof, root))

    def test_proof_rejects_tampered_sibling(self):
        ids = [sha256_hex(f"leaf-{i}") for i in range(4)]
        root = compute_merkle_root(ids)
        proof = merkle_proof(ids, 0)
        broken = [(sha256_hex("bad"), flag) for _, flag in proof]
        self.assertFalse(verify_merkle_proof(ids[0], broken, root))

    def test_proof_rejects_wrong_root(self):
        ids = [sha256_hex(f"leaf-{i}") for i in range(4)]
        proof = merkle_proof(ids, 1)
        self.assertFalse(
            verify_merkle_proof(ids[1], proof, compute_merkle_root(["x"]))
        )


class TestBlock(unittest.TestCase):
    def test_hash_changes_when_payload_changes(self):
        block = Block(1, [make_tx(1)], GENESIS_PREV_HASH, difficulty=2)
        block.mine()
        before = block.hash
        block.transactions[0].data["product_name"] = "篡改"
        self.assertNotEqual(before, block.calculate_hash())

    def test_mine_satisfies_difficulty(self):
        block = Block(1, [make_tx(1)], GENESIS_PREV_HASH, difficulty=3)
        nonce, attempts = block.mine(3)
        self.assertTrue(block.hash.startswith("000"))
        self.assertTrue(block.satisfies_pow())
        self.assertGreaterEqual(attempts, 1)

    def test_merkle_root_is_live_property(self):
        block = Block(1, [make_tx(1)], GENESIS_PREV_HASH, difficulty=2)
        before = block.merkle_root
        block.transactions.append(make_tx(2))
        self.assertNotEqual(before, block.merkle_root)
        self.assertEqual(block.merkle_root, compute_merkle_root(block.tx_ids))

    def test_roundtrip_dict(self):
        block = Block(1, [make_tx(1), make_tx(2)], "f" * 64, difficulty=2)
        block.mine()
        restored = Block.from_dict(block.to_dict())
        self.assertEqual(block.hash, restored.hash)
        self.assertEqual(block.nonce, restored.nonce)
        self.assertEqual(block.difficulty, restored.difficulty)
        self.assertEqual(block.tx_ids, restored.tx_ids)


class TestBlockchain(unittest.TestCase):
    def setUp(self):
        self.chain = Blockchain(difficulty=2)

    def test_genesis_block_is_actually_mined(self):
        """回归：创世区块曾未挖矿，哈希不以 0000 开头。"""
        genesis = self.chain.chain[0]
        self.assertTrue(genesis.hash.startswith("00"))
        self.assertTrue(genesis.satisfies_pow())
        self.assertEqual(genesis.previous_hash, GENESIS_PREV_HASH)
        self.assertEqual(genesis.index, 0)

    def test_fresh_chain_is_valid(self):
        ok, message = self.chain.is_chain_valid()
        self.assertTrue(ok, message)

    def test_duplicate_transaction_rejected(self):
        tx = make_tx(1)
        self.chain.add_transaction(tx)
        with self.assertRaises(ValueError):
            self.chain.add_transaction(tx)

    def test_invalid_transaction_rejected(self):
        with self.assertRaises(ValueError):
            self.chain.add_transaction(Transaction("production", {"product_id": "X"}))

    def test_validate_can_be_skipped(self):
        tx_id = self.chain.add_transaction(
            Transaction("production", {"product_id": "X"}), validate=False
        )
        self.assertTrue(tx_id)

    def test_trace_product_returns_each_record_once(self):
        """回归：4 笔同产品交易曾被返回 16 条（下标重复追加）。"""
        for i in range(1, 5):
            self.chain.add_transaction(make_tx(1, batch_number=f"B{i}"))
        self.chain.mine_pending_transactions()

        records = self.chain.trace_product("TEST-001")
        self.assertEqual(len(records), 4, [r["tx_id"][:8] for r in records])
        self.assertEqual(len({r["tx_id"] for r in records}), 4)
        self.assertEqual(self.chain.product_blocks["TEST-001"], [1])

    def test_trace_product_spans_multiple_blocks(self):
        self.chain.add_transaction(make_tx(1))
        self.chain.mine_pending_transactions()
        self.chain.add_transaction(make_tx(1, batch_number="SECOND"))
        self.chain.mine_pending_transactions()

        records = self.chain.trace_product("TEST-001")
        self.assertEqual(len(records), 2)
        self.assertEqual([r["block_index"] for r in records], [1, 2])

    def test_trace_unknown_product_is_empty(self):
        self.assertEqual(self.chain.trace_product("NOPE"), [])

    def test_trace_records_are_time_ordered(self):
        for i in range(1, 4):
            self.chain.add_transaction(make_tx(1, batch_number=f"B{i}"))
        self.chain.mine_pending_transactions()
        timestamps = [r["timestamp"] for r in self.chain.trace_product("TEST-001")]
        self.assertEqual(timestamps, sorted(timestamps))

    def test_tampering_is_detected(self):
        """回归：篡改后旧实现仍报告「区块链完整有效」。"""
        self.chain.add_transaction(make_tx(1))
        self.chain.add_transaction(make_tx(2))
        self.chain.mine_pending_transactions()
        self.assertTrue(self.chain.is_chain_valid()[0])

        result = self.chain.tamper_transaction(1, 0, "product_name", "假冒产品")
        ok, message = self.chain.is_chain_valid()
        self.assertFalse(ok)
        self.assertIn("区块 #1", message)
        self.assertTrue(result["before"]["chain_valid"])
        self.assertFalse(result["after"]["chain_valid"])
        self.assertNotEqual(result["before"]["tx_id"], result["after"]["tx_id"])

    def test_tampering_genesis_is_detected(self):
        """回归：is_chain_valid 曾从 index 1 起校验，跳过创世区块。"""
        self.chain.chain[0].transactions[0].data["origin"] = "伪造产地"
        ok, message = self.chain.is_chain_valid()
        self.assertFalse(ok)
        self.assertIn("区块 #0", message)

    def test_chain_break_detected(self):
        """把 previous_hash 改掉并**重算哈希**，链接错误应被单独报出来。"""
        self.chain.add_transaction(make_tx(1))
        self.chain.mine_pending_transactions()
        self.chain.add_transaction(make_tx(2))
        self.chain.mine_pending_transactions()

        broken = self.chain.chain[2]
        broken.previous_hash = "0" * 64
        broken.hash = broken.calculate_hash()  # 让区块自身哈希重新自洽
        ok, message = self.chain.is_chain_valid()
        self.assertFalse(ok)
        self.assertIn("前置哈希", message)

    def test_pow_downgrade_detected(self):
        self.chain.add_transaction(make_tx(1))
        block = self.chain.mine_pending_transactions()
        block.difficulty = 1
        block.hash = block.calculate_hash()
        ok, _ = self.chain.is_chain_valid()
        self.assertFalse(ok, "降低难度后重新计算哈希不应通过校验")

    def test_audit_chain_shape(self):
        self.chain.add_transaction(make_tx(1))
        self.chain.mine_pending_transactions()
        rows = self.chain.audit_chain()
        self.assertEqual(len(rows), len(self.chain.chain))
        for row in rows:
            self.assertTrue(row["通过"], row)
            self.assertTrue(row["哈希一致"])
            self.assertTrue(row["链接正确"])
            self.assertTrue(row["工作量证明"])
            self.assertTrue(row["Merkle 根"])

    def test_audit_chain_flags_tampering(self):
        self.chain.add_transaction(make_tx(1))
        self.chain.mine_pending_transactions()
        self.chain.chain[1].transactions[0].data["product_name"] = "篡改"
        rows = self.chain.audit_chain()
        self.assertFalse(rows[1]["哈希一致"])
        self.assertFalse(rows[1]["通过"])

    def test_verify_transaction_inclusion(self):
        self.chain.add_transaction(make_tx(1))
        block = self.chain.mine_pending_transactions()
        tx_id = block.tx_ids[0]
        ok, _ = self.chain.verify_transaction_inclusion(tx_id, block.index)
        self.assertTrue(ok)
        ok, _ = self.chain.verify_transaction_inclusion("0" * 64, block.index)
        self.assertFalse(ok)

    def test_mining_log_records_attempts(self):
        self.chain.add_transaction(make_tx(1))
        self.chain.mine_pending_transactions(miner_address="tester")
        entry = self.chain.mining_log[-1]
        self.assertEqual(entry["miner"], "tester")
        self.assertGreaterEqual(entry["attempts"], 1)
        self.assertGreaterEqual(entry["duration_s"], 0)
        self.assertEqual(entry["tx_count"], 1)

    def test_mining_without_pending_raises(self):
        with self.assertRaises(ValueError):
            self.chain.mine_pending_transactions()

    def test_difficulty_adjustment_respects_bounds(self):
        chain = Blockchain(difficulty=Blockchain.MIN_DIFFICULTY, auto_adjust=True)
        for i in range(1, 6):
            chain.add_transaction(make_tx(i))
            chain.mine_pending_transactions()
        self.assertGreaterEqual(chain.difficulty, Blockchain.MIN_DIFFICULTY)
        self.assertLessEqual(chain.difficulty, Blockchain.MAX_DIFFICULTY)

    def test_difficulty_adjustment_disabled_by_default(self):
        for i in range(1, 6):
            self.chain.add_transaction(make_tx(i))
            self.chain.mine_pending_transactions()
        self.assertEqual(self.chain.difficulty, 2)

    def test_chain_stats(self):
        self.chain.add_transaction(make_tx(1))
        self.chain.add_transaction(make_tx(2))
        self.chain.mine_pending_transactions()
        stats = self.chain.get_chain_stats()
        self.assertEqual(stats["block_count"], 2)
        # 创世区块的合成占位交易不计入业务交易总数
        self.assertEqual(stats["total_transactions"], 2)
        self.assertEqual(stats["chain_transactions"], 3)
        self.assertEqual(stats["unique_products"], 2)
        self.assertGreater(stats["chain_size_kb"], 0)
        self.assertGreaterEqual(stats["avg_block_seconds"], 0)

    def test_participants_roundtrip(self):
        self.chain.register_participant("f1", "测试农场", "生产者",
                                        {"type": "种植基地", "location": "某地"})
        info = self.chain.participants["f1"]
        self.assertEqual(info["name"], "测试农场")
        self.assertEqual(info["role"], "生产者")
        self.assertEqual(info["type"], "种植基地")
        self.assertEqual(info["location"], "某地")
        self.assertTrue(self.chain.remove_participant("f1"))
        self.assertFalse(self.chain.remove_participant("f1"))

    def test_register_participant_requires_id_and_name(self):
        with self.assertRaises(ValueError):
            self.chain.register_participant("", "名称", "生产者")

    def test_all_transactions_shape(self):
        self.chain.add_transaction(make_tx(1))
        self.chain.mine_pending_transactions()
        rows = self.chain.all_transactions()
        self.assertEqual(len(rows), 1)
        self.assertIsInstance(rows[0]["tx"], Transaction)
        self.assertIn("data", rows[0])

    def test_all_transactions_excludes_genesis_by_default(self):
        """创世占位交易不是业务记录，默认不应出现在平铺交易列表里。"""
        self.chain.add_transaction(make_tx(1))
        self.chain.mine_pending_transactions()
        self.assertEqual(len(self.chain.all_transactions()), 1)
        self.assertEqual(len(self.chain.all_transactions(include_genesis=True)), 2)
        self.assertTrue(self.chain.chain[0].transactions[0].is_genesis)
        self.assertFalse(self.chain.chain[1].transactions[0].is_genesis)

    def test_genesis_is_not_a_product(self):
        self.assertNotIn("GENESIS", self.chain.get_product_list())


class TestPersistence(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="agri-chain-test-")
        self.path = os.path.join(self.tmp, "chain.json")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_save_and_load_roundtrip(self):
        chain = Blockchain(difficulty=2)
        chain.add_transaction(make_tx(1))
        chain.mine_pending_transactions()
        chain.register_participant("f1", "农场", "生产者", {"type": "基地"})
        chain.save_to_file(self.path)

        restored = Blockchain.load_from_file(self.path)
        self.assertIsNotNone(restored)
        self.assertEqual(len(restored.chain), len(chain.chain))
        self.assertEqual(restored.chain[1].hash, chain.chain[1].hash)
        self.assertTrue(restored.is_chain_valid()[0])
        self.assertEqual(len(restored.trace_product("TEST-001")), 1)
        self.assertEqual(restored.participants["f1"]["type"], "基地")

    def test_saved_file_declares_schema_version(self):
        chain = Blockchain(difficulty=2)
        chain.save_to_file(self.path)
        with open(self.path, encoding="utf-8") as handle:
            payload = json.load(handle)
        self.assertEqual(payload["schema_version"], SCHEMA_VERSION)

    def test_no_temp_file_left_behind(self):
        Blockchain(difficulty=2).save_to_file(self.path)
        leftovers = [n for n in os.listdir(self.tmp) if n.endswith(".tmp")]
        self.assertEqual(leftovers, [])

    def test_overwrite_is_safe(self):
        chain = Blockchain(difficulty=2)
        chain.save_to_file(self.path)
        chain.add_transaction(make_tx(1))
        chain.mine_pending_transactions()
        chain.save_to_file(self.path)
        restored = Blockchain.load_from_file(self.path)
        self.assertEqual(len(restored.chain), 2)

    def test_missing_file_returns_none(self):
        self.assertIsNone(Blockchain.load_from_file(os.path.join(self.tmp, "nope.json")))

    def test_corrupt_file_is_archived_and_returns_none(self):
        with open(self.path, "w", encoding="utf-8") as handle:
            handle.write("{ this is not json")
        self.assertIsNone(Blockchain.load_from_file(self.path))
        archived = [n for n in os.listdir(self.tmp) if ".corrupt-" in n]
        self.assertEqual(len(archived), 1)
        self.assertFalse(os.path.exists(self.path))

    def test_legacy_schema_is_archived(self):
        """回归：v1 数据文件的哈希口径不同，必须归档而不是硬加载。"""
        with open(self.path, "w", encoding="utf-8") as handle:
            json.dump({"schema_version": 1, "chain": [], "difficulty": 4}, handle)
        self.assertIsNone(Blockchain.load_from_file(self.path))
        archived = [n for n in os.listdir(self.tmp) if ".legacy-v1-" in n]
        self.assertEqual(len(archived), 1)
        self.assertFalse(os.path.exists(self.path))

    def test_future_schema_is_archived(self):
        """比程序更新的 schema 也不能硬加载。"""
        with open(self.path, "w", encoding="utf-8") as handle:
            json.dump({"schema_version": SCHEMA_VERSION + 1, "chain": []}, handle)
        self.assertIsNone(Blockchain.load_from_file(self.path))
        archived = [n for n in os.listdir(self.tmp) if ".future-v" in n]
        self.assertEqual(len(archived), 1)

    def test_archiving_can_be_disabled(self):
        with open(self.path, "w", encoding="utf-8") as handle:
            json.dump({"schema_version": 1, "chain": []}, handle)
        self.assertIsNone(Blockchain.load_from_file(self.path, archive_incompatible=False))
        self.assertTrue(os.path.exists(self.path))

    def test_writable_dir_detection(self):
        self.assertTrue(is_dir_writable(self.tmp))
        self.assertTrue(is_dir_writable(os.path.join(self.tmp, "nested", "deep")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
