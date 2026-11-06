#!/usr/bin/env python3
"""judge_cases.py — 컨설턴트의 동의 · 반대 기록을 평가 에이전트 시험 문제로 바꾼다

  python3 tools/judge_cases.py golden/<이름> > 문제.jsonl
동의 = PASS(진짜 문제다) · 반대 = FAIL(문제가 아니다). 평가기의 판정 CSV(case_id,verdict)와 tools/agreement.py 로 일치율을 잰다.
"""
import json, sys
from pathlib import Path

p = Path(sys.argv[1]) / "judge-labels.jsonl"
if not p.exists():
    sys.exit(f"없습니다: {p}")
for i, l in enumerate(x for x in p.read_text(encoding="utf-8").splitlines() if x.strip()):
    s = json.loads(l)
    print(json.dumps({"case_id": f"J-{i + 1:03d}", "run": s.get("run"), "file": s.get("file"), "quote": s.get("quote"), "claim": s.get("comment"), "criterion": s.get("who") or "판정", "expected": "PASS" if s.get("state") == "accepted" else "FAIL", "human_note": s.get("note", "")}, ensure_ascii=False))
