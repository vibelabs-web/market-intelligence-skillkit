#!/usr/bin/env python3
"""ext_check.py — 확장 과제 점검 (판정만 하고 고치지 않는다)

  python3 tools/ext_check.py api <팀>                  E1 수집: 모든 쪽을 받았나 · 429 를 지켰나 · 장애 뒤 다시 받았나
  python3 tools/ext_check.py db <sqlite 파일> <결과 폴더>  E2 저장: 브리핑이 인용한 신호를 DB 에서 원문까지 되짚을 수 있나
  python3 tools/ext_check.py outbox <발송 폴더>          E3 발송: 사람이 승인한 그대로만 나갔나
종료 코드: 통과 0 · 미달 1 · 입력 오류 2
"""
from __future__ import annotations
import hashlib, json, re, sqlite3, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SID = re.compile(r"SIG-\d{5}")


def check_api(lines: list[dict], total_pages: int | None = None) -> dict:
    ok_pages = {l["page"] for l in lines if l["status"] == 200}
    last_429 = None
    early = 0
    for l in sorted(lines, key=lambda x: x["t"]):
        if last_429 is not None and l["t"] - last_429 < 1.0:
            early += 1                         # Retry-After(1초)를 기다리지 않고 다시 보냈다
        if l["status"] == 429:
            last_429 = l["t"]
    failed = {l["page"] for l in lines if l["status"] in (503, 504)}
    dup = sum(1 for l in lines if l["status"] == 200) - len(ok_pages)
    out = {"requests": len(lines), "pages_ok": len(ok_pages), "pages_expected": total_pages, "rate_limited": sum(l["status"] == 429 for l in lines),
           "ignored_retry_after": early, "outage_pages": len(failed), "outage_recovered": len(failed & ok_pages), "duplicate_fetches": dup}
    out["pass"] = (total_pages is None or len(ok_pages) == total_pages) and failed <= ok_pages and early == 0
    return out


def check_db(db: Path, run: Path) -> dict:
    text = (run / "brief.md").read_text(encoding="utf-8")
    cited = sorted(set(SID.findall(text)))
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        ev = {r[0]: r for r in con.execute("SELECT signal_id, source_url, published_at FROM evidence")}
        cit = {r[0] for r in con.execute("SELECT signal_id FROM citations WHERE run = ?", (run.name,))}
    except sqlite3.Error as e:
        return {"pass": False, "error": f"표가 없거나 열 이름이 다릅니다: {e}"}
    finally:
        con.close()
    missing = [s for s in cited if s not in ev]
    no_source = [s for s in cited if s in ev and not (ev[s][1] or "").strip()]
    not_logged = [s for s in cited if s not in cit]
    return {"cited": len(cited), "missing_in_evidence": missing, "no_source_url": no_source, "not_in_citations": not_logged,
            "pass": bool(cited) and not missing and not no_source and not not_logged}


def check_outbox(box: Path) -> dict:
    """sent/<이름>.md 마다 approvals/<이름>.json({"approved_by","sha256","approved_at"})이 있고 내용 해시가 같아야 한다.
    log.jsonl 의 sent 기록 시각은 승인 시각보다 늦어야 한다"""
    sent = sorted((box / "sent").glob("*.md")) if (box / "sent").is_dir() else []
    log = {}
    if (box / "log.jsonl").exists():
        for l in (box / "log.jsonl").read_text(encoding="utf-8").splitlines():
            if l.strip():
                e = json.loads(l)
                if e.get("event") == "sent":
                    log[e.get("name")] = e.get("at", "")
    problems = []
    for f in sent:
        a = box / "approvals" / f"{f.stem}.json"
        if not a.exists():
            problems.append(f"{f.name}: 승인 기록 없이 나갔습니다")
            continue
        ap = json.loads(a.read_text(encoding="utf-8"))
        if not str(ap.get("approved_by", "")).strip():
            problems.append(f"{f.name}: 승인한 사람이 없습니다")
        if ap.get("sha256") != hashlib.sha256(f.read_bytes()).hexdigest():
            problems.append(f"{f.name}: 승인 뒤 내용이 바뀌었습니다")
        if f.stem not in log:
            problems.append(f"{f.name}: 발송 기록(log.jsonl)이 없습니다")
        elif str(log[f.stem]) < str(ap.get("approved_at", "")):
            problems.append(f"{f.name}: 승인 전에 보냈습니다")
    return {"sent": len(sent), "problems": problems, "pass": bool(sent) and not problems}


def main() -> int:
    a = sys.argv[1:]
    try:
        if len(a) == 2 and a[0] == "api":
            p = ROOT / f"dev/results/api-{a[1]}.jsonl"
            lines = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
            import csv
            with open(ROOT / "dev/data/signals.csv", encoding="utf-8", newline="") as f:
                n = sum(1 for _ in csv.DictReader(f))
            sizes = {l.get("page_size") for l in lines if l["status"] == 200}
            if len(sizes) != 1:
                print("입력 오류: 한 번의 수집은 같은 page_size 로 해야 합니다", file=sys.stderr)
                return 2
            size = sizes.pop()
            out = check_api(lines, (n + size - 1) // size)
        elif len(a) == 3 and a[0] == "db":
            out = check_db(Path(a[1]), Path(a[2]))
        elif len(a) == 2 and a[0] == "outbox":
            out = check_outbox(Path(a[1]))
        else:
            print(__doc__, file=sys.stderr)
            return 2
    except (OSError, json.JSONDecodeError) as e:
        print(f"입력 오류: {e}", file=sys.stderr)
        return 2
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0 if out["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
