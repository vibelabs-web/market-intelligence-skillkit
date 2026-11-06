#!/usr/bin/env python3
"""defect_score.py — 평가 에이전트가 결함 문장을 얼마나 잡고 정상 문장을 얼마나 잘못 짚는가

  python3 tools/defect_score.py 판정1.jsonl 판정2.jsonl 판정3.jsonl --key <강사 정답 해시> [--team 팀 --cost 달러 --seconds 초]
강사 채점 전용이다. 정답 해시는 저장소에 없고 강사가 따로 보관한다.

판정 파일: 줄마다 {"case":"procurement-A","sid":"S01","verdict":"DEFECT 또는 OK","type":"(선택)","reason":"..."}
점수 F1 = 결함 재현율과 정밀도의 조화평균. 답이 없는 문장은 틀린 것으로 본다. 정답지가 있으면(_instructor) 유형별로도 보여 준다.
"""
from __future__ import annotations
import argparse, hashlib, json, os, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent


def load(p: str) -> dict:
    out = {}
    for l in Path(p).read_text(encoding="utf-8").splitlines():
        if l.strip():
            d = json.loads(l)
            out[f"{d['case']}/{d['sid']}"] = str(d.get("verdict", "")).upper()
    return out


def score(pred: dict, key: dict, salt: str) -> dict:
    tp = fp = fn = tn = 0
    for k, h in key.items():
        case, sid = k.split("/")
        truth = "DEFECT" if hashlib.sha256(f"{salt}{case}{sid}DEFECT".encode()).hexdigest() == h else "OK"
        p = pred.get(k)
        if truth == "DEFECT":
            tp += p == "DEFECT"; fn += p != "DEFECT"
        else:
            fp += p != "OK"; tn += p == "OK"
    rec = tp / (tp + fn) if tp + fn else 0
    pre = tp / (tp + fp) if tp + fp else 0
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "recall": round(rec, 3), "precision": round(pre, 3), "f1": round(2 * rec * pre / (rec + pre), 3) if rec + pre else 0}


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("preds", nargs="+"); ap.add_argument("--team"); ap.add_argument("--key", default=os.environ.get("MI_DEFECT_KEY", str(ROOT / "_instructor/defects/answers.hash.json"))); ap.add_argument("--cost", type=float); ap.add_argument("--seconds", type=float)
    a = ap.parse_args()
    try:
        K = json.loads(Path(a.key).read_text(encoding="utf-8"))
        preds = [load(p) for p in a.preds]
    except (OSError, ValueError, KeyError) as e:
        print(f"입력 오류: {e}", file=sys.stderr); return 2
    runs = [score(p, K["items"], K["salt"]) for p in preds]
    keys = list(K["items"])
    stable = sum(len({p.get(k) for p in preds}) == 1 for k in keys) / len(keys)
    f1 = sum(r["f1"] for r in runs) / len(runs)
    out = {"runs": runs, "f1_mean": round(f1, 3), "stability": round(stable, 3)}
    ans = ROOT / "_instructor/defects/answers.json"
    if ans.exists():
        A = json.loads(ans.read_text(encoding="utf-8")); miss: dict[str, list] = {}
        for case, v in A.items():
            for it in v["items"]:
                if it["label"] == "DEFECT":
                    m = miss.setdefault(it["type"], [0, 0]); m[1] += len(preds)
                    m[0] += sum(p.get(f"{case}/{it['sid']}") == "DEFECT" for p in preds)
        out["by_type"] = {t: f"{a_}/{b_}" for t, (a_, b_) in sorted(miss.items())}
    print(json.dumps(out, ensure_ascii=False, indent=1))
    if a.team:
        d = ROOT / "dev/results"; d.mkdir(parents=True, exist_ok=True)
        (d / f"{a.team}-defects.json").write_text(json.dumps({"team": a.team, "golden": "결함 시험", "level": "주과제", "score": round(f1 * 100), "must": f"재현율 {sum(r['recall'] for r in runs) / len(runs):.2f}", "never": f"정밀도 {sum(r['precision'] for r in runs) / len(runs):.2f}", "fact_issues": "-", "stable": f"{stable:.2f}", "cost_usd": a.cost, "seconds": a.seconds, "at": time.strftime("%H:%M:%S")}, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
