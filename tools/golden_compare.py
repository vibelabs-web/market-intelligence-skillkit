#!/usr/bin/env python3
"""golden_compare.py — 에이전트 결과가 골든을 재현하는가

  python3 tools/golden_compare.py golden/<이름> 결과1 [결과2 결과3 ...]

결과 폴더: selection.csv · brief.md · (있으면) llm-judgments.csv
«같다»의 뜻 — 문장이 같은 것이 아니다.
  선별   : 근거마다 보낸다 · 뺀다가 골든과 같다
  사실   : 코드 검사 문제 0
  판정   : assertions.jsonl 항목 통과 (llm 항목은 판정 파일이 있어야 한다)
  안정성 : 여러 번 돌려도 선별이 같다
종료 코드: 전부 통과 0 · 실패 1 · 입력 오류 2
"""
from __future__ import annotations
import csv, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from check_brief import check

ROOT = Path(__file__).resolve().parent.parent


def selection(p: Path) -> dict[str, str]:
    with open(p, encoding="utf-8", newline="") as f:
        return {r["evidence_id"].strip(): r["send"].strip().lower() for r in csv.DictReader(f)}


def score_selection(gold: dict, got: dict) -> dict:
    wrong = [{"id": k, "golden": v, "got": got.get(k, "(없음)")} for k, v in sorted(gold.items()) if got.get(k) != v]
    extra = sorted(set(got) - set(gold))
    tp = sum(1 for k, v in gold.items() if v == "yes" and got.get(k) == "yes")
    fp = sum(1 for k, v in got.items() if v == "yes" and gold.get(k) != "yes")
    fn = sum(1 for k, v in gold.items() if v == "yes" and got.get(k) != "yes")
    prec = tp / (tp + fp) if tp + fp else None
    rec = tp / (tp + fn) if tp + fn else None
    return {"match": not wrong and not extra, "agree": f"{len(gold) - len(wrong)}/{len(gold)}", "precision": round(prec, 3) if prec is not None else None,
            "recall": round(rec, 3) if rec is not None else None, "wrong": wrong, "extra": extra}


def score_assertions(items: list[dict], text: str, llm: dict) -> tuple[bool, list[dict]]:
    out, ok = [], True
    for a in items:
        kind, val = a["kind"], str(a.get("value", ""))
        if kind == "contains":
            r = "PASS" if val in text else "FAIL"
        elif kind == "not_contains":
            r = "PASS" if val not in text else "FAIL"
        elif kind == "llm":
            r = llm.get(a["id"], "NOT_JUDGED")
        else:
            r = "UNKNOWN_KIND"
        ok = ok and r == "PASS"
        out.append({"id": a["id"], "kind": kind, "result": r})
    return ok, out


def judge(gold_dir: Path, cand: Path, rows: dict, syn: set[str]) -> dict:
    gold = selection(gold_dir / "selection.csv")
    text = (cand / "brief.md").read_text(encoding="utf-8")
    sel = score_selection(gold, selection(cand / "selection.csv"))
    facts = check(text, rows, syn)
    items = []
    ap = gold_dir / "assertions.jsonl"
    if ap.exists():
        items = [json.loads(x) for x in ap.read_text(encoding="utf-8").splitlines() if x.strip()]
    llm = {}
    lp = cand / "llm-judgments.csv"
    if lp.exists():
        with open(lp, encoding="utf-8", newline="") as f:
            llm = {r["id"]: r["verdict"].strip().upper() for r in csv.DictReader(f)}
    aok, ares = score_assertions(items, text, llm)
    return {"candidate": str(cand), "pass": sel["match"] and not facts and aok, "selection": sel, "fact_issues": facts, "assertions": ares}


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__, file=sys.stderr)
        return 2
    g = Path(sys.argv[1])
    try:
        with open(ROOT / "project/fact-pack/evidence-register.csv", encoding="utf-8", newline="") as f:
            rows = {r["evidence_id"]: r for r in csv.DictReader(f)}
        res = [judge(g, Path(c), rows, {"42", "27", "18", "11"}) for c in sys.argv[2:]]
        sels = [selection(Path(c) / "selection.csv") for c in sys.argv[2:]]
    except (OSError, KeyError, json.JSONDecodeError) as e:
        print(f"입력 오류: {e}", file=sys.stderr)
        return 2
    stable = all(s == sels[0] for s in sels)
    ok = all(r["pass"] for r in res) and stable
    print(json.dumps({"golden": g.name, "reproduced": ok, "runs": len(res), "selection_stable": stable, "results": res}, ensure_ascii=False, indent=1))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
