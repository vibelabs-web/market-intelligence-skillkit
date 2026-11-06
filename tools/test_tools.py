#!/usr/bin/env python3
"""check_brief · agreement 재현 테스트"""
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from check_brief import check
from agreement import measure

ROWS = {"E-001": {"quote": "imports reached 1,234 million in 2024", "claim": "수입 1,234", "status": "confirmed"},
        "E-002": {"quote": "the draft rule is under review", "claim": "초안", "status": "proposed"}}


def gates(text, syn=frozenset()):
    return sorted({i["gate"] for i in check(text, ROWS, syn)})


class Brief(unittest.TestCase):
    def test_ok(self):
        self.assertEqual(gates("수입은 1,234 입니다 [E-001]."), [])
    def test_unknown_id(self):
        self.assertIn("G1", gates("수입이 늘었습니다 [E-099]."))
    def test_number_without_source(self):
        self.assertIn("G1", gates("시장은 500 규모입니다."))
    def test_number_not_in_source(self):
        self.assertIn("G3", gates("수입은 9,999 입니다 [E-001]."))
    def test_proposed_as_firm(self):
        self.assertIn("G2", gates("이 규제는 시행 중입니다 [E-002]."))
    def test_proposed_hedged(self):
        self.assertEqual(gates("이 규제는 초안이며 시행 중인지 확인 필요합니다 [E-002]."), [])
    def test_synthetic_marked(self):
        self.assertEqual(gates("베트남 문의는 42건입니다 (synthetic).", {"42"}), [])
    def test_synthetic_unmarked(self):
        self.assertIn("G5", gates("베트남 문의는 42건입니다 [E-001].", {"42"}))
    def test_year_and_list_ignored(self):
        self.assertEqual(gates("1. 2024년 자료입니다."), [])


class Agreement(unittest.TestCase):
    G = {"a": {"expected": "PASS", "criterion": "G1"}, "b": {"expected": "FAIL", "criterion": "G2"}}
    def test_full(self):
        m = measure(self.G, [{"a": "PASS", "b": "FAIL"}] * 3)
        self.assertEqual((m["agreement"], m["stability"], m["disagreements"]), (1.0, 1.0, []))
    def test_flip(self):
        m = measure(self.G, [{"a": "PASS", "b": "FAIL"}, {"a": "PASS", "b": "PASS"}, {"a": "PASS", "b": "FAIL"}])
        self.assertEqual(m["stability"], 0.5)
        self.assertEqual([d["case_id"] for d in m["disagreements"]], ["b"])
    def test_missing_not_counted_as_match(self):
        m = measure(self.G, [{"a": "PASS"}, {"a": "PASS", "b": "FAIL"}])
        self.assertEqual(m["missing_verdicts"], 1)
        self.assertEqual(m["stability"], 0.5)
    def test_empty(self):
        self.assertIsNone(measure({}, [])["agreement"])


if __name__ == "__main__":
    unittest.main()
