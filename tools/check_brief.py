#!/usr/bin/env python3
"""check_brief.py — 보고서를 코드로 검사한다 (G1 출처 · G2 상태 · G3 숫자 · G4 계산 · G5 가상 표시 · G6 분량)

  python3 tools/check_brief.py runs/r1/brief.md [--register project/fact-pack/evidence-register.csv] [--profile project/people/ceo.md]

판단이 필요한 것은 하지 않는다. 종료 코드: 문제 없음 0 · 문제 있음 1 · 입력 오류 2
"""
from __future__ import annotations
import argparse, csv, json, re, sys
from pathlib import Path

ID = re.compile(r"(?:[EI]-\d{3}|SIG-\d{5})")
NUM = re.compile(r"(?<![\w.-])\d[\d,]*(?:\.\d+)?")
FIRM = re.compile(r"시행\s*중|확정(?!되면|되고|돼도|될|되지|이\s*아)|발효|의무화(?:됐|되었)|in force|mandatory", re.I)
HEDGE = re.compile(r"초안|검토|추진|예정|미확정|불확실|proposed|draft|가능성|확인\s*필요")
SPAN = re.compile(r"\(([^()]*[=×÷≈+−][^()]*)\)|((?:[^().;]|(?<=\d)\.(?=\d))*[=×÷≈](?:[^().;]|(?<=\d)\.(?=\d))*)")   # 식을 보인 숫자만 근거 대조에서 뺀다
TERM = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(천만|억|만|천|%)?")
UNIT = {"천만": 1e7, "억": 1e8, "만": 1e4, "천": 1e3, "%": 0.01, "": 1, None: 1}
SYN = re.compile(r"\(?\s*(?:synthetic|내부\s*집계|내부\s*자료)\s*\)?", re.I)


def norm(n: str) -> str:
    n = n.replace(",", "").rstrip(".")
    return n.rstrip("0").rstrip(".") if "." in n else n


def formula_spans(s: str) -> list[str]:
    return [a or b for a, b in SPAN.findall(s)]


def bad_formula(span: str) -> str | None:
    """«A × B = C» 처럼 값만으로 된 식의 답이 맞는지 본다. 날짜 · 단위가 섞인 식은 건너뛴다"""
    if "월" in span or "일" in span or "주" in span:
        return None
    m = re.search(r"(.+?)\s*[=≈]\s*(.+)", span)
    if not m:
        return None
    left, right = m.groups()
    terms, ops = TERM.findall(left), re.findall(r"[×÷+]", left)
    ans = TERM.search(right)
    if not ans or not ops or len(terms) != len(ops) + 1:
        return None
    val = lambda t: float(t[0].replace(",", "")) * UNIT[t[1]]
    got = val(terms[0])
    for op, t in zip(ops, terms[1:]):
        v = val(t)
        if op == "÷" and not v:
            return None
        got = got * v if op == "×" else got / v if op == "÷" else got + v
    want = val((ans.group(1), ans.group(2)))
    return None if want and abs(got - want) / abs(want) <= 0.02 else f"계산이 맞지 않음: {span.strip()} (계산하면 약 {got:,.4g})"


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
            if out and fresh and re.fullmatch(r"(?:\[?(?:E-\d{3}|SIG-\d{5})\]?[\s,.·]*)+", s):   # 문장 뒤에 따로 놓인 근거 표시
                out[-1] += " " + s
            else:
                out.append(s)
            fresh = True
        fresh = False
    return out


def bare_numbers(s: str) -> list[str]:
    s = ID.sub(" ", s)
    s = re.sub(r"(?<![\d,.])20\d\d(?:[-./]\d{1,2}){0,2}(?!\d)", " ", s)   # 연도 · 날짜
    s = re.sub(r"(?<![\d,.])\d{1,2}/\d{1,2}(?![\d/])", " ", s)                  # 12/1 같은 날짜
    s = re.sub(r"\d{1,2}월(?:\s*\d{1,2}일)?|\d{1,2}일|\d{1,2}분기", " ", s)     # 한글 날짜 — 숫자로 검사하지 않는다
    s = re.sub(r"\d{1,3}\s*(?:개월|주|분)\s*(?:안|내|동안|뒤|전)", " ", s)        # 기간 표현
    s = re.sub(r"(?:최근|지난)\s*\d{1,3}\s*(?:개월|주|년)", " ", s)
    s = re.sub(r"\b1\s*(?:건|대|인|톤|품목)당|(?<![\d,.])1건(?!\s*당)", " ", s)
    s = re.sub(r"\d{1,2}\s*(?:개(?!국|월)|가지|단계|품목|차례)", " ", s)              # 글의 구성을 세는 수
    return [norm(m) for m in NUM.findall(s)]


def check(text: str, rows: dict[str, dict], synthetic_values: set[str] = frozenset(), allowed: set[str] = frozenset()) -> list[dict]:
    """allowed: 받는 사람의 프로필에 있어 근거 번호 없이 써도 되는 숫자"""
    issues = []
    def add(gate, sent, why):
        issues.append({"gate": gate, "sentence": sent[:160], "why": why})
    pairs = [(s, line) for line in text.replace("**", "").splitlines() for s in sentences(line)]
    for s, line in pairs:
        ids = ID.findall(s) or ID.findall(line)       # 문단 끝에 몰아 적은 근거 번호도 그 문단의 근거로 본다
        spans = formula_spans(s)
        shown = {norm(n) for x in spans for n in bare_numbers(x)}
        for r, x, y in re.findall(r"(\d[\d,.]*)[^\d()]{0,8}\(\s*(\d[\d,.]*)\D*?−\s*(\d[\d,.]*)\D*\)", s):   # «10주 공백(16주 − 6주)»: 맞는 뺄셈만
            if float(x.replace(",", "")) - float(y.replace(",", "")) == float(r.replace(",", "").rstrip(".")):
                shown.add(norm(r))
        shown |= {n.split(".")[0] for n in shown}     # «약 26억 (26.2억 × …)» 처럼 식의 값을 줄여 쓴 경우
        nums = [n for n in bare_numbers(s) if n not in shown and n not in allowed]
        is_syn = bool(SYN.search(s)) and not ids      # 근거 번호가 있으면 «내부 자료»라는 말로 대조를 피하지 못한다
        for x in spans:
            why = bad_formula(x)
            if why:
                add("G4", s, why)
        for i in ids:
            if i not in rows:
                add("G1", s, f"근거 묶음에 없는 ID {i}")
        known = [rows[i] for i in ids if i in rows]
        if nums and not ids and not is_syn:
            add("G1", s, f"숫자 {nums} 에 근거 ID · synthetic 표시가 없음")
        if known:
            hay = {norm(n) for n in NUM.findall(" ".join(f"{r.get('quote','')} {r.get('claim','')}" for r in known))}
            for n in nums:
                if n not in hay and not is_syn:
                    add("G3", s, f"숫자 {n} 이 인용한 근거에 없음")
            if any(r.get("status") in ("proposed", "uncertain") for r in known) and FIRM.search(s) and not HEDGE.search(s):
                add("G2", s, "검토 · 불확실 근거를 확정처럼 씀")
        if not is_syn and any(v in nums for v in synthetic_values):
            add("G5", s, "가상 내부 수치에 synthetic 표시가 없음")
    return issues


def length_issue(text: str, profile: str) -> dict | None:
    """프로필의 «형식» 줄에 분량이나 읽는 시간이 있으면 재서 20% 넘게 길 때 알린다 (1분 ≈ 350자, 공백 포함, 근거 번호 · 마크다운 표시 제외)"""
    line = next((l for l in profile.splitlines() if "형식" in l), "")
    chars = re.search(r"(\d[\d,]*)\s*자", line)
    mins = re.search(r"(\d+)\s*분", line)
    if not chars and not mins:
        return None
    limit = int(chars.group(1).replace(",", "")) if chars else int(mins.group(1)) * 350
    n = len(re.sub(r"\s+", " ", re.sub(r"[#*|`>\[\]]", "", ID.sub("", text))).strip())
    if n <= limit * 1.2:
        return None
    return {"gate": "G6", "sentence": f"{n}자", "why": f"프로필 기준 {limit}자보다 많이 깁니다 ({n}자)"}


def load_rows(register: str = "project/fact-pack/evidence-register.csv") -> dict[str, dict]:
    """시장 근거 + 같은 폴더의 내부 자료 대장"""
    rows: dict[str, dict] = {}
    p = Path(register)
    for f in (p, p.with_name("internal-data.csv")):
        if f.exists():
            with open(f, encoding="utf-8", newline="") as fp:
                rows.update({r["evidence_id"]: r for r in csv.DictReader(fp)})
    if not rows:
        raise OSError(f"근거 묶음이 없습니다: {register}")
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("brief")
    ap.add_argument("--register", default="project/fact-pack/evidence-register.csv")
    ap.add_argument("--synthetic", default="", help="쉼표로 구분한 가상 수치 (예: 42,27,18)")
    ap.add_argument("--profile", help="받는 사람 프로필 — 여기 있는 숫자는 근거 번호 없이 쓸 수 있다")
    a = ap.parse_args()
    try:
        text = Path(a.brief).read_text(encoding="utf-8")
        rows = load_rows(a.register)
    except OSError as e:
        print(f"입력 오류: {e}", file=sys.stderr)
        return 2
    allowed = {norm(n) for n in NUM.findall(Path(a.profile).read_text(encoding="utf-8"))} if a.profile else frozenset()
    issues = check(text, rows, {norm(x) for x in a.synthetic.split(",") if x}, allowed)
    if a.profile:
        too_long = length_issue(text, Path(a.profile).read_text(encoding="utf-8"))
        if too_long:
            issues.append(too_long)
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
