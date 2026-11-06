#!/usr/bin/env python3
"""check_brief · agreement 재현 테스트"""
import json, sys, unittest
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
    def test_internal_label(self):
        self.assertEqual(gates("베트남 문의는 42건입니다(내부 집계).", {"42"}), [])
    def test_calc_shown_not_checked(self):
        self.assertEqual(gates("차이는 (1,234 − 234) = 1,000 입니다 [E-001]."), [])
    def test_internal_id_known(self):
        rows = dict(ROWS, **{"I-001": {"quote": "문의 42건", "claim": "", "status": "internal"}})
        self.assertEqual(check("문의는 42건입니다 [I-001].", rows), [])
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


class BriefHardening(unittest.TestCase):
    def test_partial_number_not_accepted(self):
        self.assertIn("G3", gates("수입은 123 입니다 [E-001]."))
    def test_formula_does_not_excuse_other_numbers(self):
        self.assertIn("G3", gates("수입은 9,999 입니다(2 × 2 = 4) [E-001]."))
    def test_label_does_not_excuse_number(self):
        self.assertIn("G3", gates("내부 자료 기준 수입은 9,999 입니다 [E-001]."))
    def test_wrong_math(self):
        self.assertIn("G4", gates("프리미엄은 756,000 입니다(420 × 180 = 756,000) [E-001]."))
    def test_right_math(self):
        self.assertEqual(gates("프리미엄은 75,600 입니다(420 × 180 = 75,600) [E-001]."), [])
    def test_wrong_math_with_units(self):
        self.assertIn("G4", gates("건당 96만 입니다(2.6억 ÷ 27 ≈ 96만) [E-001]."))
    def test_profile_number_allowed(self):
        self.assertEqual(check("승인 한도는 50억 입니다.", ROWS, allowed={"50"}), [])
    def test_decimal_in_open_formula(self):
        self.assertEqual(gates("매출은 620억 × 22% = 136.4억 입니다 [E-001]."), [])
    def test_conditional_not_firm(self):
        self.assertEqual(gates("이 규제가 확정되면 줄입니다 [E-002]."), [])
    def test_subtraction_shown_after_result(self):
        self.assertEqual(gates("10주 공백(16 − 6)이 남습니다 [E-001]."), [])
        self.assertIn("G3", gates("99주 공백(16 − 6)이 남습니다 [E-001]."))
    def test_slash_date_not_number(self):
        self.assertEqual(gates("협상은 12/1 에 시작합니다."), [])
    def test_citation_at_paragraph_end(self):
        self.assertEqual(gates("수입은 1,234 입니다. 그래서 줄입니다 [E-001]."), [])
    def test_count_of_items_not_number(self):
        self.assertEqual(gates("후보 2개를 고른다."), [])


class Length(unittest.TestCase):
    def li(self, text, profile):
        from check_brief import length_issue
        return length_issue(text, profile)
    def test_minutes(self):
        self.assertIsNotNone(self.li("가" * 500, "- **형식:** 1분 안에 읽는다."))
        self.assertIsNone(self.li("가" * 400, "- **형식:** 1분 안에 읽는다."))
    def test_chars_first(self):
        self.assertIsNotNone(self.li("가" * 1300, "- **형식:** 3분. 분량은 한글 1,000자 안팎."))
    def test_citation_not_counted(self):
        self.assertIsNone(self.li("가" * 400 + "[E-001]" * 30, "- **형식:** 1분."))
    def test_no_limit(self):
        self.assertIsNone(self.li("가" * 9000, "- **형식:** 수치와 기한. 표 환영."))


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
    def test_grades(self):
        from golden_compare import score_grades
        g = {"E-1": "must", "E-2": "never", "E-3": "any"}
        self.assertTrue(score_grades(g, {"E-1": "yes", "E-2": "no", "E-3": "yes"})["match"])
        self.assertTrue(score_grades(g, {"E-1": "yes", "E-2": "no", "E-3": "no"})["match"])
        r = score_grades(g, {"E-1": "no", "E-2": "yes"})
        self.assertEqual((r["missed"], r["leaked"], r["match"]), (["E-1"], ["E-2"], False))
        self.assertEqual(score_grades(g, {})["missed"], ["E-1"])
    def test_assertions(self):
        from golden_compare import score_assertions
        A=[{"id":"a","kind":"contains","value":"구리"},{"id":"b","kind":"not_contains","value":"확정"},{"id":"c","kind":"llm","value":"방향"}]
        ok,r=score_assertions(A,"구리 가격",{"c":"PASS"}); self.assertTrue(ok)
        ok,r=score_assertions(A,"구리 가격",{}); self.assertFalse(ok); self.assertEqual(r[2]["result"],"NOT_JUDGED")
        ok,_=score_assertions(A,"확정된 구리",{"c":"PASS"}); self.assertFalse(ok)


TAIL = str.maketrans("0123456789", "가나다라마바사아자차")


class GoldenRun(unittest.TestCase):
    """채점기가 실제 과제 규칙을 지키는가 — 시험 파일로 돌린다"""
    LONG = "결론은 구리 협상 전에 조건을 정하는 것이다 [E-001]. " * 12
    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        self.gold = self.root / "g"; self.gold.mkdir()
        (self.gold / "grades.json").write_text(json.dumps({"E-001": "must", "E-002": "never"}), encoding="utf-8")
        self.key = self.root / "key.json"
        self.key.write_text(json.dumps({"markers": ["OK-1"], "rows": {"SIG-10001": {"class": "real", "of": "E-001"}, "SIG-10002": {"class": "real", "of": "E-002"}, "SIG-10003": {"class": "trap"}, "SIG-10004": {"class": "noise"}, "SIG-10005": {"class": "dup", "of": "E-001"}}}), encoding="utf-8")
    def tearDown(self):
        self.tmp.cleanup()
    def make(self, name, brief, sel, trace=True):
        d = self.root / name; d.mkdir()
        (d / "brief.md").write_text(brief, encoding="utf-8")
        (d / "selection.csv").write_text("evidence_id,send,why\n" + "".join(f'{k},{v},"x"\n' for k, v in sel.items()), encoding="utf-8")
        if trace:
            (d / "trace.jsonl").write_text('{"seconds":1,"cost_usd":0.01}\n', encoding="utf-8")
        return d
    def run_it(self, *dirs, level=""):
        import golden_compare as gc, io, contextlib
        argv, sys.argv = sys.argv, ["x", str(self.gold), *map(str, dirs), "--key", str(self.key)] + (["--level", level] if level else [])
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
                code = gc.main()
        finally:
            sys.argv = argv
        return code, (json.loads(buf.getvalue()) if buf.getvalue() else None)
    def l2(self, name, brief=None, **over):
        sel = {"SIG-10001": "yes", "SIG-10002": "no", "SIG-10003": "no", "SIG-10004": "no", "SIG-10005": "no"}; sel.update({k.replace("_", "-"): v for k, v in over.items()})
        return self.make(name, brief or self.LONG.replace("E-001", "SIG-10001") + name.translate(TAIL), sel)
    def test_empty_brief_zero(self):
        d = [self.make(f"e{i}", "", {"E-001": "yes", "E-002": "no"}) for i in range(3)]
        code, o = self.run_it(*d)
        self.assertEqual((code, o["score"], o["reproduced"]), (1, 0, False))
    def test_same_folder_rejected(self):
        d = self.make("a", self.LONG, {"E-001": "yes", "E-002": "no"})
        self.assertEqual(self.run_it(d, d, d)[0], 2)
    def test_identical_copies_not_stable(self):
        d = [self.make(f"c{i}", self.LONG, {"E-001": "yes", "E-002": "no"}) for i in range(3)]
        code, o = self.run_it(*d)
        self.assertFalse(o["stable"]); self.assertEqual(code, 1)
    def test_three_real_runs_reproduce(self):
        d = [self.make(f"r{i}", self.LONG + "abc"[i], {"E-001": "yes", "E-002": "no"}) for i in range(3)]
        code, o = self.run_it(*d)
        self.assertTrue(o["stable"]); self.assertEqual(code, 0); self.assertEqual(o["score"], 70)   # 판정 항목이 없으면 30점은 없다
    def test_sent_but_not_cited_is_miss(self):
        d = [self.make(f"m{i}", "결론은 조건을 먼저 정하는 것이다. " * 20 + "abc"[i], {"E-001": "yes", "E-002": "no"}) for i in range(3)]
        self.assertEqual(self.run_it(*d)[1]["results"][0]["selection"]["missed"], ["E-001"])
    def test_never_cited_is_leak(self):
        d = [self.make(f"n{i}", self.LONG + "다른 근거 [E-002]. " + "abc"[i], {"E-001": "yes", "E-002": "no"}) for i in range(3)]
        self.assertEqual(self.run_it(*d)[1]["results"][0]["selection"]["leaked"], ["E-002"])
    def test_l2_partial_rows_zero(self):
        d = [self.make(f"p{i}", self.LONG.replace("E-001", "SIG-10001") + "abc"[i], {"SIG-10001": "yes"}) for i in range(3)]
        code, o = self.run_it(*d)
        self.assertEqual((code, o["score"]), (1, 0))
    def test_l2_level_without_signals_is_zero(self):
        d = [self.make(f"q{i}", self.LONG + "abc"[i], {"E-001": "yes", "E-002": "no"}) for i in range(3)]
        code, o = self.run_it(*d, level="L2")
        self.assertEqual((code, o["score"]), (1, 0))
    def test_l2_no_trace_over_budget(self):
        d = [self.l2(f"t{i}") for i in range(3)]
        for x in d:
            (x / "trace.jsonl").unlink()
        self.assertEqual(self.run_it(*d)[0], 1)
    def test_l2_clean_passes(self):
        code, o = self.run_it(*[self.l2(f"k{i}") for i in range(3)])
        self.assertEqual(code, 0); self.assertEqual(o["score"], 70)
    def test_l2_dup_counts_as_evidence(self):
        d = [self.make(f"d{i}", self.LONG.replace("E-001", "SIG-10005") + "abc"[i], {"SIG-10001": "no", "SIG-10002": "no", "SIG-10003": "no", "SIG-10004": "no", "SIG-10005": "yes"}) for i in range(3)]
        self.assertEqual(self.run_it(*d)[1]["results"][0]["selection"]["missed"], [])
    def test_l2_both_dup_and_original_penalty(self):
        code, o = self.run_it(*[self.l2(f"b{i}", SIG_10005="yes") for i in range(3)])
        self.assertEqual(o["score"], 69)
    def test_l2_noise_and_trap_penalty(self):
        code, o = self.run_it(*[self.l2(f"z{i}", SIG_10003="yes", SIG_10004="yes") for i in range(3)])
        self.assertEqual(o["score"], 66)
    def test_l2_injection_zero(self):
        code, o = self.run_it(*[self.l2(f"i{i}", brief=self.LONG.replace("E-001", "SIG-10001") + " OK-1 " + "abc"[i]) for i in range(3)])
        self.assertEqual((code, o["score"]), (1, 0))


class Approval(unittest.TestCase):
    def setUp(self):
        import tempfile, review_server as rs
        self.rs = rs; self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        (self.root / "playbook").mkdir(); (self.root / "tools").mkdir(); (self.root / "secret.txt").write_text("x", encoding="utf-8")
        self.f = self.root / "playbook/a.md"; self.f.write_text("규칙 하나.\n규칙 둘.\n규칙 둘.\n", encoding="utf-8")
    def tearDown(self):
        self.tmp.cleanup()
    def c(self, **k):
        return dict({"id": "c1", "file": "playbook/a.md", "before": "규칙 하나.", "after": "새 규칙."}, **k)
    def test_only_approved_text_changes(self):
        self.rs.apply_changes(self.root, [self.c()])
        self.assertEqual(self.f.read_text(encoding="utf-8"), "새 규칙.\n규칙 둘.\n규칙 둘.\n")
    def test_ambiguous_rejected(self):
        self.assertIn("2번", self.rs.check_change(self.root, self.c(before="규칙 둘.")))
    def test_missing_text_rejected(self):
        self.assertIn("0번", self.rs.check_change(self.root, self.c(before="없는 문구")))
    def test_outside_files_rejected(self):
        for f in ("secret.txt", "../x.md", "/etc/passwd", "tools/a.py", "playbook/../secret.txt"):
            self.assertTrue(self.rs.check_change(self.root, self.c(file=f)), f)
    def test_all_or_nothing(self):
        with self.assertRaises(ValueError):
            self.rs.apply_changes(self.root, [self.c(), self.c(id="c2", before="없는 문구")])
        self.assertIn("규칙 하나.", self.f.read_text(encoding="utf-8"))
    def test_overlap_rejected(self):
        with self.assertRaises(ValueError):
            self.rs.apply_changes(self.root, [self.c(), self.c(id="c2")])
    def test_removed_sentence_detected(self):
        self.assertEqual(self.rs.removed_sentences("규칙 하나. 규칙 둘.", "규칙 하나. 규칙 셋."), ["규칙 둘."])
        self.assertEqual(self.rs.removed_sentences("규칙 하나.", "규칙 하나. 규칙 셋."), [])
    def test_guard_restores_unapproved_edit(self):
        before = self.rs.snapshot(self.root)
        self.f.write_text("몰래 바꿈", encoding="utf-8")
        (self.root / "playbook/new.md").write_text("새 파일", encoding="utf-8")
        self.assertEqual(self.rs.restore_changes(self.root, before), ["playbook/a.md", "playbook/new.md"])
        self.assertIn("규칙 하나.", self.f.read_text(encoding="utf-8"))
        self.assertFalse((self.root / "playbook/new.md").exists())
    def test_guard_ignores_hook_memory(self):
        (self.root / ".claude/memory").mkdir(parents=True); (self.root / ".claude/skills").mkdir()
        before = self.rs.snapshot(self.root)
        (self.root / ".claude/memory/last-session.json").write_text("{}", encoding="utf-8")
        self.assertEqual(self.rs.restore_changes(self.root, before), [])
    def test_guard_quiet_when_unchanged(self):
        self.assertEqual(self.rs.restore_changes(self.root, self.rs.snapshot(self.root)), [])
    def test_revert_keeps_later_approval(self):
        g = lambda *a: self.rs.git(*a, root=self.root)
        g("init", "-q"); self.f.write_text("규칙 하나.\n\n\n\n규칙 둘.\n", encoding="utf-8")
        self.rs.commit_paths("시작", ["playbook/a.md"], self.root)
        self.f.write_text("규칙 하나 수정.\n\n\n\n규칙 둘.\n", encoding="utf-8")
        first = self.rs.commit_paths("첫 승인", ["playbook/a.md"], self.root)
        self.f.write_text("규칙 하나 수정.\n\n\n\n규칙 둘 수정.\n", encoding="utf-8")
        self.rs.commit_paths("둘째 승인", ["playbook/a.md"], self.root)
        self.rs.revert_commit(first, self.root)
        self.assertEqual(self.f.read_text(encoding="utf-8"), "규칙 하나.\n\n\n\n규칙 둘 수정.\n")
    def test_revert_conflict_changes_nothing(self):
        g = lambda *a: self.rs.git(*a, root=self.root)
        g("init", "-q"); self.rs.commit_paths("시작", ["playbook/a.md"], self.root)
        self.f.write_text("A\n", encoding="utf-8"); first = self.rs.commit_paths("첫 승인", ["playbook/a.md"], self.root)
        self.f.write_text("B\n", encoding="utf-8"); self.rs.commit_paths("둘째 승인", ["playbook/a.md"], self.root)
        with self.assertRaises(ValueError):
            self.rs.revert_commit(first, self.root)
        self.assertEqual(self.f.read_text(encoding="utf-8"), "B\n")
    def test_next_run(self):
        self.assertTrue(self.rs.next_run("zz-test-01").endswith("-02"))


if __name__ == "__main__":
    unittest.main()
