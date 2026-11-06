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
    def test_citation_after_period(self):
        self.assertEqual(gates("수입은 1,234 입니다. [E-001]"), [])
    def test_citation_not_taken_from_next_line(self):
        self.assertIn("G1", gates("시장은 500 규모입니다.\n다음 문장입니다 [E-001]."))
    def test_korean_date_not_number(self):
        self.assertEqual(gates("11월 10일까지 확인하고 90일 안에 끝냅니다.", {"11"}), [])
    def test_real_number_still_caught_next_to_date(self):
        self.assertIn("G1", gates("11월 10일 기준 시장은 500 규모입니다."))
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


class Golden(unittest.TestCase):
    def test_selection(self):
        from golden_compare import score_selection
        g={"E-1":"yes","E-2":"no"}
        self.assertTrue(score_selection(g,dict(g))["match"])
        r=score_selection(g,{"E-1":"no","E-2":"yes"})
        self.assertFalse(r["match"]); self.assertEqual(r["precision"],0.0); self.assertEqual(r["recall"],0.0)
        self.assertFalse(score_selection(g,{"E-1":"yes"})["match"])
        self.assertFalse(score_selection(g,{**g,"E-3":"yes"})["match"])
    def test_assertions(self):
        from golden_compare import score_assertions
        A=[{"id":"a","kind":"contains","value":"구리"},{"id":"b","kind":"not_contains","value":"확정"},{"id":"c","kind":"llm","value":"방향"}]
        ok,r=score_assertions(A,"구리 가격",{"c":"PASS"}); self.assertTrue(ok)
        ok,r=score_assertions(A,"구리 가격",{}); self.assertFalse(ok); self.assertEqual(r[2]["result"],"NOT_JUDGED")
        ok,_=score_assertions(A,"확정된 구리",{"c":"PASS"}); self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
