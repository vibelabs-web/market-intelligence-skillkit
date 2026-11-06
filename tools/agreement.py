#!/usr/bin/env python3
"""agreement.py — 평가기 판정이 사람과 얼마나 일치하고, 반복해도 같은지 잰다

  python3 tools/agreement.py golden/g.jsonl runs/judge-1/*.csv

골든 줄: case_id, expected, criterion, kind. 판정 CSV: case_id,verdict (파일 하나 = 1회 실행).
종료 코드: 계산 완료 0 · 입력 오류 2. 합격선은 사람이 정한다.
"""
from __future__ import annotations
import collections, csv, json, sys
from pathlib import Path


def measure(golden: dict[str, dict], runs: list[dict[str, str]]) -> dict:
    per = {}
    for cid, g in golden.items():
        seen = [r.get(cid) for r in runs]
        given = [v for v in seen if v]
        per[cid] = {"criterion": g.get("criterion"), "expected": g["expected"], "seen": seen,
                    "match": sum(v == g["expected"] for v in given), "n": len(given),
                    "stable": len(set(given)) <= 1 and len(given) == len(runs)}
    total = sum(p["n"] for p in per.values())
    missing = sum(len(runs) - p["n"] for p in per.values())
    by = collections.defaultdict(lambda: [0, 0])
    for p in per.values():
        by[p["criterion"]][0] += p["match"]
        by[p["criterion"]][1] += p["n"]
    return {"cases": len(per), "runs": len(runs), "missing_verdicts": missing,
            "agreement": round(sum(p["match"] for p in per.values()) / total, 3) if total else None,
            "stability": round(sum(p["stable"] for p in per.values()) / len(per), 3) if per else None,
            "by_criterion": {k: {"match": a, "n": b} for k, (a, b) in sorted(by.items(), key=lambda x: str(x[0]))},
            "disagreements": [dict(case_id=c, **p) for c, p in per.items() if p["match"] != len(runs)]}


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        golden = {}
        for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
            if line.strip():
                g = json.loads(line)
                golden[g["case_id"]] = g
        runs = []
        for p in sys.argv[2:]:
            with open(p, encoding="utf-8", newline="") as f:
                runs.append({r["case_id"]: r["verdict"] for r in csv.DictReader(f)})
    except (OSError, KeyError, json.JSONDecodeError) as e:
        print(f"입력 오류: {e}", file=sys.stderr)
        return 2
    print(json.dumps(measure(golden, runs), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
