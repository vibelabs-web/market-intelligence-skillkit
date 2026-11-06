#!/usr/bin/env python3
"""check_brief.py — 보고서를 코드로 검사한다 (G1 출처 · G2 상태 · G3 숫자 · G5 가상 표시)

  python3 tools/check_brief.py runs/r1/brief-CEO.md [--register project/fact-pack/evidence-register.csv]

판단이 필요한 것은 하지 않는다. 종료 코드: 문제 없음 0 · 문제 있음 1 · 입력 오류 2
"""
from __future__ import annotations
import argparse, csv, json, re, sys
from pathlib import Path

ID = re.compile(r"E-\d{3}")
NUM = re.compile(r"(?<![\w.-])\d[\d,]*(?:\.\d+)?")
FIRM = re.compile(r"시행\s*중|확정|발효|의무화(?:됐|되었)|in force|mandatory", re.I)
HEDGE = re.compile(r"초안|검토|추진|예정|미확정|불확실|proposed|draft|가능성|확인\s*필요")
SYN = re.compile(r"\(?\s*(?:synthetic|내부\s*집계|내부\s*자료)\s*\)?", re.I)


def norm(n: str) -> str:
    return n.replace(",", "").rstrip(".")


def sentences(text: str) -> list[str]:
    out: list[str] = []
    fresh = False
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or re.fullmatch(r"[|:\-\s]+", line):
            continue
        line = re.sub(r"^(?:[-*]|\d+[.)])\s+", "", line)              # 목록 표시
        for s in re.split(r"(?<=[.!?])\s+", line):
            s = s.strip()
            if not s:
                continue
            if out and fresh and re.fullmatch(r"(?:\[?E-\d{3}\]?[\s,.·]*)+", s):   # 문장 뒤에 따로 놓인 근거 표시
                out[-1] += " " + s
            else:
                out.append(s)
            fresh = True
        fresh = False
    return out


def bare_numbers(s: str) -> list[str]:
    s = ID.sub(" ", s)
    s = re.sub(r"(?<![\d,.])20\d\d(?:[-./]\d{1,2}){0,2}(?!\d)", " ", s)   # 연도 · 날짜
    s = re.sub(r"\d{1,2}월(?:\s*\d{1,2}일)?|\d{1,2}일|\d{1,2}분기", " ", s)     # 한글 날짜 — 숫자로 검사하지 않는다
    s = re.sub(r"\d{1,3}\s*(?:개월|주|분)\s*(?:안|내|동안|뒤|전)", " ", s)        # 기간 표현
    return [norm(m) for m in NUM.findall(s)]


def check(text: str, rows: dict[str, dict], synthetic_values: set[str] = frozenset()) -> list[dict]:
    issues = []
    def add(gate, sent, why):
        issues.append({"gate": gate, "sentence": sent[:160], "why": why})
    for s in sentences(text):
        ids = ID.findall(s)
        nums = bare_numbers(s)
        is_syn = bool(SYN.search(s))
        for i in ids:
            if i not in rows:
                add("G1", s, f"근거 묶음에 없는 ID {i}")
        known = [rows[i] for i in ids if i in rows]
        if nums and not ids and not is_syn:
            add("G1", s, f"숫자 {nums} 에 근거 ID · synthetic 표시가 없음")
        if known:
            hay = " ".join(f"{r.get('quote','')} {r.get('claim','')}" for r in known).replace(",", "")
            for n in nums:
                if n not in hay and not is_syn:
                    add("G3", s, f"숫자 {n} 이 인용한 근거에 없음")
            if any(r.get("status") in ("proposed", "uncertain") for r in known) and FIRM.search(s) and not HEDGE.search(s):
                add("G2", s, "검토 · 불확실 근거를 확정처럼 씀")
        if not is_syn and any(v in nums for v in synthetic_values):
            add("G5", s, "가상 내부 수치에 synthetic 표시가 없음")
    return issues


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("brief")
    ap.add_argument("--register", default="project/fact-pack/evidence-register.csv")
    ap.add_argument("--synthetic", default="", help="쉼표로 구분한 가상 수치 (예: 42,27,18)")
    a = ap.parse_args()
    try:
        text = Path(a.brief).read_text(encoding="utf-8")
        with open(a.register, encoding="utf-8", newline="") as f:
            rows = {r["evidence_id"]: r for r in csv.DictReader(f)}
    except OSError as e:
        print(f"입력 오류: {e}", file=sys.stderr)
        return 2
    issues = check(text, rows, {norm(x) for x in a.synthetic.split(",") if x})
    sel = Path(a.brief).with_name("selection.csv")
    if sel.exists():
        with open(sel, encoding="utf-8", newline="") as f:
            no = {r["evidence_id"].strip() for r in csv.DictReader(f) if r["send"].strip().lower() != "yes"}
        for i in sorted(no & set(ID.findall(text))):
            issues.append({"gate": "선별", "sentence": i, "why": "selection.csv 에서 뺀 근거를 브리핑이 인용함"})
    print(json.dumps({"file": a.brief, "issues": issues}, ensure_ascii=False, indent=1))
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
