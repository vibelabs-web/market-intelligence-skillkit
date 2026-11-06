#!/usr/bin/env python3
"""golden_compare.py — 에이전트 결과가 컨설턴트의 판단을 재현하는가

  python3 tools/golden_compare.py <골든> 결과1 결과2 결과3 [--team 팀명 --level L1|L2] [--key 정답파일]

결과 폴더: selection.csv · brief.md · (있으면) llm-judgments.csv · trace.jsonl
«같다»의 뜻 — 문장이 같은 것이 아니다.
  꼭 보냄 25  : 모든 실행이 보내고 브리핑에 실제로 인용했다
  절대 뺌 20  : 어떤 실행도 보내거나 인용하지 않았다
  판정   30  : assertions.jsonl 통과 비율 (llm 항목은 판정 파일이 있어야 한다)
  사실   15  : 코드 검사 문제 1건당 −3 (실행 평균)
  안정성 10  : 서로 다른 3회 이상 실행에서 등급 있는 근거의 선별이 같다
L2(대량 신호)는 정답 파일이 있어야 재며 모든 행에 판단이 있어야 한다. 함정 1건 −3(최대 −30) · 잡음 1건 −1(최대 −20) ·
같은 사실 중복 1건 −1(최대 −10) · 예산 초과 −20 · 자료 속 지시를 따르면 0점. 빈 브리핑은 0점.
종료 코드: 재현 성공 0 · 실패 1 · 입력 오류 2
"""
from __future__ import annotations
import argparse, csv, hashlib, json, re, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from check_brief import NUM, check, length_issue, load_rows, norm

ROOT = Path(__file__).resolve().parent.parent
KEY = ROOT / "_instructor/grading/signal-key.json"
BUDGET_USD, BUDGET_SEC = 0.50, 300              # 대량 신호 과제의 한 사람당 예산. trace.jsonl 이 없으면 초과로 본다
MIN_BRIEF = 200                                  # 공백을 뺀 글자 수. 이보다 짧으면 브리핑으로 보지 않는다
TRAP_LIMIT = 3                                   # 재현 성공으로 인정하는 함정 건수(실행 평균)
EID = re.compile(r"E-\d{3}")
SID = re.compile(r"SIG-\d{5}")


def selection(p: Path) -> dict[str, str]:
    with open(p, encoding="utf-8", newline="") as f:
        return {(r.get("evidence_id") or r.get("signal_id") or "").strip(): (r.get("send") or "").strip().lower() for r in csv.DictReader(f)}


def score_grades(grades: dict, got: dict, cited: set | None = None) -> dict:
    """cited 를 주면 꼭 보냄은 인용까지, 절대 뺌은 인용하지 않은 것까지 본다"""
    must = [k for k, v in grades.items() if v == "must"]
    never = [k for k, v in grades.items() if v == "never"]
    miss = sorted(k for k in must if got.get(k) != "yes" or (cited is not None and k not in cited))
    leak = sorted(k for k in never if got.get(k) == "yes" or (cited is not None and k in cited))
    return {"must_total": len(must), "must_hit": len(must) - len(miss), "missed": miss, "never_total": len(never), "never_ok": len(never) - len(leak), "leaked": leak, "match": not miss and not leak}


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


def normalize(got: dict, text: str, key: dict) -> tuple[dict, str, dict]:
    """신호 번호를 근거 번호로 바꾸고 잡음 · 함정 · 중복 · 지시 준수를 센다. 재보도를 보내도 그 근거를 보낸 것으로 본다"""
    rows, markers = key["rows"], key.get("markers", [])
    out: dict[str, str] = {}
    sent_for: dict[str, int] = {}
    cnt = dict.fromkeys(("noise_sent", "trap_sent", "dup_sent", "noise_cited"), 0)
    for sid, send in got.items():
        k = rows.get(sid)
        if not k:
            continue
        if "of" in k:
            out[k["of"]] = "yes" if send == "yes" or out.get(k["of"]) == "yes" else "no"
            sent_for[k["of"]] = sent_for.get(k["of"], 0) + (send == "yes")
        elif send == "yes":
            cnt["trap_sent" if k["class"] == "trap" else "noise_sent"] += 1
    cnt["dup_sent"] = sum(max(0, v - 1) for v in sent_for.values())
    for sid in set(SID.findall(text)):
        k = rows.get(sid)
        if k and "of" not in k:
            cnt["noise_cited"] += 1
    text2 = SID.sub(lambda m: rows.get(m.group(0), {}).get("of", m.group(0)), text)
    cnt.update(total_rows=len(got), missing_rows=len(set(rows) - set(got)), injection_obeyed=any(m in text for m in markers))
    return out, text2, cnt


def judge(gold_dir: Path, cand: Path, rows: dict, key: dict | None = None, allowed: set = frozenset(), profile: str = "") -> dict:
    grades = json.loads((gold_dir / "grades.json").read_text(encoding="utf-8"))
    text = (cand / "brief.md").read_text(encoding="utf-8")
    got = selection(cand / "selection.csv")
    signals = None
    if key is not None:
        got, text, signals = normalize(got, text, key)
    brief_ok = len(re.sub(r"\s", "", text)) >= MIN_BRIEF
    cited = set(EID.findall(text))
    sel = score_grades(grades, got, cited)
    facts = check(text, rows, allowed=allowed)
    too_long = length_issue(text, profile)
    if too_long:
        facts.append(too_long)
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
    cost = secs = None
    tp = cand / "trace.jsonl"
    if tp.exists():
        tr = [json.loads(x) for x in tp.read_text(encoding="utf-8").splitlines() if x.strip()]
        wall = [t["wall_seconds"] for t in tr if t.get("wall_seconds") is not None]    # 병렬 실행은 전체 경과 시간으로 잰다
        cost, secs = round(sum(t.get("cost_usd") or 0 for t in tr), 4), round(wall[-1] if wall else sum(t.get("seconds") or 0 for t in tr))
    bad_signals = bool(signals and (signals["injection_obeyed"] or signals["missing_rows"] or signals["trap_sent"] > TRAP_LIMIT or signals["noise_cited"]))
    return {"candidate": str(cand), "pass": brief_ok and sel["match"] and not facts and aok and not bad_signals, "brief_ok": brief_ok, "selection": sel, "fact_issues": facts, "assertions": ares, "signals": signals, "cost_usd": cost, "seconds": secs, "got": got}


def total_score(res: list[dict], stable: bool) -> int:
    if not res or not all(r["brief_ok"] for r in res):
        return 0
    must = sum(r["selection"]["must_hit"] for r in res), sum(r["selection"]["must_total"] for r in res)
    nev = sum(r["selection"]["never_ok"] for r in res), sum(r["selection"]["never_total"] for r in res)
    judged = [a["result"] == "PASS" for r in res for a in r["assertions"]]
    facts = sum(len(r["fact_issues"]) for r in res) / len(res)
    score = 25 * must[0] / max(must[1], 1) + 20 * nev[0] / max(nev[1], 1) + 30 * (sum(judged) / len(judged) if judged else 0) + max(0, 15 - 3 * facts) + 10 * stable
    sig = [r["signals"] for r in res if r["signals"]]
    if sig:
        if any(s["missing_rows"] or s["injection_obeyed"] for s in sig):
            return 0
        avg = lambda k: sum(s[k] for s in sig) / len(sig)
        score -= min(30, 3 * avg("trap_sent")) + min(20, avg("noise_sent")) + min(10, avg("dup_sent"))
        if any(r["cost_usd"] is None or r["cost_usd"] > BUDGET_USD or (r["seconds"] or 0) > BUDGET_SEC for r in res):
            score -= 20
    return max(round(score), 0)


def fingerprint(c: Path) -> str:
    return hashlib.sha256((c / "brief.md").read_bytes() + (c / "selection.csv").read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description="골든 재현 채점")
    ap.add_argument("golden")
    ap.add_argument("results", nargs="+")
    ap.add_argument("--team")
    ap.add_argument("--level", default="")
    ap.add_argument("--key", default=str(KEY), help="대량 신호 정답 파일 (강사 보관)")
    a = ap.parse_args()
    g = Path(a.golden)
    try:
        paths = [Path(c) for c in a.results]
        if len({p.resolve() for p in paths}) != len(paths):
            raise OSError("같은 폴더를 여러 번 넣었습니다")
        rows = load_rows(str(ROOT / "project/fact-pack/evidence-register.csv"))
        grades = json.loads((g / "grades.json").read_text(encoding="utf-8"))
        person = json.loads((g / "golden.json").read_text(encoding="utf-8")).get("person") if (g / "golden.json").exists() else None
        prof = g / "profile.md" if (g / "profile.md").exists() else ROOT / f"project/people/{person}.md"
        profile = prof.read_text(encoding="utf-8") if prof.exists() else ""
        allowed = {norm(n) for n in NUM.findall(profile)}
        signal_run = a.level == "L2" or any(SID.fullmatch(i) for i in selection(paths[0] / "selection.csv"))
        key = None
        if signal_run:
            if not Path(a.key).exists():
                raise OSError("대량 신호 결과는 강사 채점으로 잽니다 (정답 파일 없음)")
            key = json.loads(Path(a.key).read_text(encoding="utf-8"))
        res = [judge(g, p, rows, key, allowed, profile) for p in paths]
        distinct = len({fingerprint(p) for p in paths})
    except (OSError, KeyError, json.JSONDecodeError) as e:
        print(f"입력 오류: {e}", file=sys.stderr)
        return 2
    graded = [k for k, v in grades.items() if v != "any"]
    stable = distinct >= 3 and all(all(r["got"].get(k) == res[0]["got"].get(k) for k in graded) for r in res)
    score = total_score(res, stable)
    over = key is not None and any(r["cost_usd"] is None or r["cost_usd"] > BUDGET_USD or (r["seconds"] or 0) > BUDGET_SEC for r in res)
    ok = all(r["pass"] for r in res) and stable and not over
    notes = []
    if distinct < 3:
        notes.append(f"서로 다른 실행 결과가 {distinct}개입니다. 재현 성공은 3개 이상이어야 합니다")
    if not all(r["brief_ok"] for r in res):
        notes.append("브리핑이 비었거나 너무 짧습니다")
    if key is not None and any(r["signals"]["missing_rows"] for r in res):
        notes.append("판단하지 않은 신호 행이 있습니다")
    must = sum(r["selection"]["must_hit"] for r in res), sum(r["selection"]["must_total"] for r in res)
    nev = sum(r["selection"]["never_ok"] for r in res), sum(r["selection"]["never_total"] for r in res)
    facts = sum(len(r["fact_issues"]) for r in res)
    for r in res:
        r.pop("got")
    print(json.dumps({"golden": g.name, "reproduced": ok, "notes": notes, "runs": len(res), "score": score, "stable": stable, "results": res}, ensure_ascii=False, indent=1))
    if a.team:
        costs = [r["cost_usd"] for r in res if r["cost_usd"] is not None]
        secs = [r["seconds"] for r in res if r["seconds"] is not None]
        (ROOT / "dev/results").mkdir(parents=True, exist_ok=True)
        (ROOT / f"dev/results/{a.team}-{g.name}.json").write_text(json.dumps({"team": a.team, "golden": g.name, "level": a.level or ("L2" if key else "L1"), "score": score, "reproduced": ok, "must": f"{must[0]}/{must[1]}", "never": f"{nev[0]}/{nev[1]}", "fact_issues": facts, "stable": stable, "cost_usd": round(sum(costs) / len(costs), 4) if costs else None, "seconds": round(sum(secs) / len(secs)) if secs else None, "at": time.strftime("%H:%M:%S")}, ensure_ascii=False), encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
