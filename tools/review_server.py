#!/usr/bin/env python3
"""review_server.py — 결과물을 브라우저로 보고, 하이라이트로 피드백하고, 만족하면 골든으로 저장한다

  python3 tools/review_server.py [--port 8765]   → http://127.0.0.1:8765

표준 라이브러리만 쓴다. 내 PC 안에서만 열린다(127.0.0.1). 결과물 형식은 가리지 않는다: .md · .html · .csv · .txt
  runs/<run>/            결과물 · run.json · feedback.jsonl · verdict.json
  golden/<run>/          만족한 결과의 동결본 (결과물 · 피드백 이력 · 스킬 버전)
"""
from __future__ import annotations
import argparse, csv, datetime as dt, difflib, hashlib, html, io, json, os, re, shutil, subprocess, sys, threading, urllib.parse, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS, GOLDEN = ROOT / "runs", ROOT / "golden"
UI = Path(__file__).with_name("review_ui.html")
HOME = Path(__file__).with_name("home_ui.html")
TOKENS = """:root{--paper:#f6f6fa;--paper-2:#efeff6;--surface:#ffffff;--ink:#1c1c2b;--ink-2:#34344a;--muted:#6a6a80;--rule:#e4e4ee;--rule-2:#c9c9d8;
--accent:#6b46e5;--accent-soft:#efeafe;--accent-ink:#ffffff;--focus:#6b46e5;--ok:#1f8a4c;--ok-soft:#e5f5ec;--bad:#c2410c;--bad-soft:#fdeee6;--mark:#fff1b8;--mark-ok:#d5f2e0;--ai:#3b5bdb;--warn:#b45309;--warn-soft:#fff4e0;
--radius:12px;--shadow:0 1px 2px rgba(28,28,43,.06),0 4px 16px rgba(28,28,43,.05);
--font:-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo','Pretendard','Malgun Gothic','Noto Sans KR',sans-serif;--mono:ui-monospace,Menlo,Consolas,monospace}"""
DOC_CSS = """<style>
/* Hallmark · theme: custom workbench (UI 시안 v3) · scope: reading document · redesign: restyle · waived: 58 a briefing is read in full; 44b no hero, first screen is the conclusion */
""" + TOKENS + """
*{box-sizing:border-box}html,body{overflow-x:clip}
body{font:400 1.0625rem/1.75 var(--font);max-width:46rem;margin:0 auto;padding:2rem 1.5rem 4rem;color:var(--ink);background:var(--surface);font-variant-numeric:tabular-nums;word-break:keep-all;overflow-wrap:break-word}
h1{font-size:1.5rem;line-height:1.35;font-weight:800;margin:0 0 1.5rem;padding-bottom:.75rem;border-bottom:1px solid var(--rule)}
h2{font-size:1.125rem;line-height:1.4;font-weight:800;margin:2.25rem 0 .75rem;padding-top:.75rem;border-top:1px solid var(--rule)}h1+h2{margin-top:0;padding-top:0;border-top:0}
h1+h2+p{font-size:1.1875rem;line-height:1.65;font-weight:500}h3,h4{font-size:1rem;margin:1.5rem 0 .5rem}
p{margin:0 0 1rem}ul,ol{margin:0 0 1rem;padding-left:1.25rem}li{margin-bottom:.625rem}strong{font-weight:700}code{font:.875em var(--mono)}
blockquote{margin:1rem 0;padding:.75rem 1rem;background:var(--warn-soft);border-radius:10px;color:var(--ink-2)}
.tw{overflow-x:auto;margin:0 0 1rem}table{border-collapse:collapse;width:100%;font-size:.9375rem;line-height:1.55}th,td{border-bottom:1px solid var(--rule);padding:.5rem .75rem .5rem 0;text-align:left;vertical-align:top}th{font-weight:700;border-bottom:1px solid var(--rule-2)}
h1,h2{text-wrap:balance}a{color:var(--ink)}a:active{color:var(--accent)}a:focus-visible,[tabindex]:focus-visible{outline:2px solid var(--focus);outline-offset:2px}
a.ev{font-size:.75em;color:var(--muted);text-decoration:underline;text-underline-offset:2px;white-space:nowrap}a.ev:hover{color:var(--accent)}a.ev.none{color:var(--accent);font-weight:700}
mark.fb{background:var(--mark);color:inherit;cursor:pointer}mark.fb.good{background:var(--mark-ok)}mark.fb.done{background:var(--paper-2)}
tr.sel-yes td:first-child{font-weight:700}tr.sel-no{color:var(--muted)}
@media(max-width:40rem){body{font-size:1rem;padding:1.25rem 1rem 3rem}h1{font-size:1.375rem}h1+h2+p{font-size:1.0625rem}}
</style>"""


def load_register() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for n in ("evidence-register.csv", "internal-data.csv"):
        p = ROOT / "project/fact-pack" / n
        if p.exists():
            with open(p, encoding="utf-8", newline="") as f:
                out.update({r["evidence_id"]: r for r in csv.DictReader(f)})
    return out


def inline(s: str, reg: dict) -> str:
    s = html.escape(s, quote=False)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2" target="_blank" rel="noopener">\1</a>', s)
    def ev(m):
        r = reg.get(m.group(0))
        if not r:
            return f'<a class="ev none" title="근거 묶음에 없는 ID">{m.group(0)}</a>'
        return f'<a class="ev" role="button" style="cursor:pointer">{m.group(0)}</a>'
    return re.sub(r"\b[EI]-\d{3}\b", ev, s)


def md_to_html(text: str, reg: dict) -> str:
    out, para, lst, tbl = [], [], None, []
    def flush():
        nonlocal para, lst, tbl
        if para:
            out.append("<p>" + inline(" ".join(para), reg) + "</p>"); para = []
        if lst:
            out.append(f"</{lst}>"); lst = None
        if tbl:
            rows = [[c.strip() for c in r.strip().strip("|").split("|")] for r in tbl]
            body = [r for r in rows if not all(re.fullmatch(r":?-+:?", c or "-") for c in r)]
            out.append('<div class="tw"><table>' + "".join("<tr>" + "".join(f"<{'th' if i == 0 else 'td'}>{inline(c, reg)}</{'th' if i == 0 else 'td'}>" for c in r) + "</tr>" for i, r in enumerate(body)) + "</table></div>")
            tbl = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            flush(); continue
        if s.startswith("|"):
            if para or lst: flush()
            tbl.append(s); continue
        if tbl: flush()
        m = re.match(r"(#{1,4})\s+(.*)", s)
        if m:
            flush(); n = len(m.group(1)); out.append(f"<h{n}>{inline(m.group(2), reg)}</h{n}>"); continue
        m = re.match(r"(?:[-*]|(\d+)[.)])\s+(.*)", s)
        if m:
            kind = "ol" if m.group(1) else "ul"
            if para: flush()
            if lst != kind:
                if lst: out.append(f"</{lst}>")
                out.append(f'<ol start="{m.group(1)}">' if kind == "ol" else "<ul>"); lst = kind
            out.append(f"<li>{inline(m.group(2), reg)}</li>"); continue
        if s.startswith(">"):
            flush(); out.append(f"<blockquote>{inline(s.lstrip('> '), reg)}</blockquote>"); continue
        if lst: flush()
        para.append(s)
    flush()
    return "\n".join(out)


def csv_to_html(text: str, reg: dict) -> str:
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return "<p>(빈 파일)</p>"
    head, body = rows[0], rows[1:]
    idx = head.index("send") if "send" in head else -1
    eid = head.index("evidence_id") if "evidence_id" in head else -1
    extra = ["내용", "출처 · 시점 · 상태"] if eid >= 0 and reg else []
    h = '<div class="tw"><table><tr>' + "".join(f"<th>{html.escape(c)}</th>" for c in head + extra) + "</tr>"
    for r in body:
        if len(r) > len(head):                       # 쉼표를 따옴표로 감싸지 않은 칸은 마지막 칸에 합친다
            r = r[:len(head) - 1] + [",".join(r[len(head) - 1:])]
        cl = f' class="sel-{"yes" if r[idx].strip().lower() == "yes" else "no"}"' if 0 <= idx < len(r) else ""
        cells = "".join(f"<td>{inline(c, reg)}</td>" for c in r)
        if extra:
            e = reg.get(r[eid].strip(), {}) if eid < len(r) else {}
            cells += f"<td>{html.escape(e.get('claim', ''))}</td><td>{html.escape(e.get('publisher', ''))} · {html.escape(e.get('data_period') or e.get('published_at') or '')} · {html.escape(e.get('status', ''))}</td>"
        h += f"<tr{cl}>{cells}</tr>"
    return h + "</table></div>"


def render_doc(path: Path) -> str:
    text, reg = path.read_text(encoding="utf-8", errors="replace"), load_register()
    if path.suffix in (".html", ".htm"):
        return text
    body = md_to_html(text, reg) if path.suffix == ".md" else csv_to_html(text, reg) if path.suffix == ".csv" else f"<pre>{html.escape(text)}</pre>"
    return f'<!doctype html><html lang="ko"><meta charset=utf-8><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="icon" href="data:,"><meta name="description" content="받는 사람의 결정에 맞춘 개인화 브리핑"><title>{html.escape(path.name)}</title>{DOC_CSS}<body>{body}</body></html>'


def safe(name: str) -> str:
    if not re.fullmatch(r"[\w가-힣.\-]+", name or "") or name.startswith("."):
        raise ValueError(f"잘못된 이름: {name}")
    return name


def run_dir(run: str) -> Path:
    d = RUNS / safe(run)
    if not d.is_dir():
        raise FileNotFoundError(run)
    return d


def doc_files(d: Path) -> list[str]:
    hide = {"feedback.jsonl", "verdict.json", "run.json", "suggestions.jsonl", "ui.json", "changes.diff", "proposal.json", "applied.json", "review.md", "grades.json"}
    fs = [p.name for p in sorted(d.iterdir()) if p.is_file() and p.name not in hide and not p.name.startswith(".")]
    return sorted(fs, key=lambda n: (not n.startswith("brief"), n))


def read_json(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def read_feedback(d: Path) -> list[dict]:
    p = d / "feedback.jsonl"
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def read_suggestions(d: Path) -> list[dict]:
    p = d / "suggestions.jsonl"
    if not p.exists():
        return []
    out = []
    for i, x in enumerate(p.read_text(encoding="utf-8").splitlines()):
        if x.strip():
            s = json.loads(x)
            s["id"] = str(s.get("id", f"s{i + 1}"))          # 생성 모델이 숫자로 적어도 처리한다
            s["file"] = Path(str(s.get("file") or "brief.md")).name
            out.append(s)
    return out


def write_suggestions(d: Path, items: list[dict]) -> None:
    (d / "suggestions.jsonl").write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in items), encoding="utf-8")


def write_feedback(d: Path, items: list[dict]) -> None:
    (d / "feedback.jsonl").write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in items), encoding="utf-8")


JOBS: dict[str, dict] = {}
JOB_LOCK = threading.Lock()
PROPOSE_TOOLS = "Read,Write(runs/{run}/proposal.json),Edit(runs/{run}/proposal.json)"
RUN_TOOLS = "Read,Write(runs/**),Edit(runs/**),Bash(python3 tools/*),Bash(git rev-parse*),Bash(mkdir*)"
DENY = "Edit(playbook/**),Write(playbook/**),Edit(project/**),Write(project/**),Edit(my/**),Write(my/**),Edit(tools/**),Write(tools/**),Edit(.claude/**),Write(.claude/**)"
PROTECTED = ("playbook", "project", "my", "tools", ".claude/skills", ".claude/settings.json")   # .claude/memory 는 훅이 쓰는 곳이라 보지 않는다


def snapshot(root: Path, allow: tuple = ()) -> dict[str, bytes]:
    paths = [q for d in PROTECTED if d not in allow for q in ([root / d] if (root / d).is_file() else (root / d).rglob("*"))]
    return {str(p.relative_to(root)): p.read_bytes() for p in paths if p.is_file() and "__pycache__" not in p.parts}


def restore_changes(root: Path, before: dict[str, bytes], allow: tuple = ()) -> list[str]:
    """AI 작업 중 바뀐 보호 파일을 되돌리고 그 목록을 준다. 스킬은 승인으로만 바뀐다"""
    after = snapshot(root, allow)
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    for k in changed:
        if k in before:
            (root / k).parent.mkdir(parents=True, exist_ok=True)
            (root / k).write_bytes(before[k])
        else:
            (root / k).unlink()
    return changed


def claude_run(prompt: str, tools: str = RUN_TOOLS, allow: tuple = (), timeout: int = 900) -> str:
    deny = ",".join(x for x in DENY.split(",") if not any(f"({a}/" in x for a in allow))
    cmd = ["claude", "-p", prompt, "--model", os.environ.get("MI_MODEL", "claude-sonnet-5-5"), "--allowedTools", tools, "--disallowedTools", deny, "--output-format", "text"]
    before = snapshot(ROOT, allow)
    out = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=timeout).stdout
    changed = restore_changes(ROOT, before, allow)
    if changed:
        raise RuntimeError("AI 작업이 승인 없이 파일을 고치려 해 되돌렸습니다: " + ", ".join(changed))
    return out


CASES = ROOT / "cases"
DEFAULT_CASE = {"id": "hanbit", "title": "한빛모션 · 베트남과 태국 중 어디로"}
TOPIC_TOOLS = "Read,Write(project/**),Edit(project/**),WebSearch,WebFetch,Bash(python3 *),Bash(mkdir*)"


def active_case() -> dict:
    return read_json(ROOT / "project/case.json", None) or dict(DEFAULT_CASE)


def save_active() -> None:
    """지금 사례(project/)를 cases/<id>/ 에 보관한다"""
    c = active_case()
    dst = CASES / safe(c["id"])
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(ROOT / "project", dst, ignore=shutil.ignore_patterns("_*"))
    (dst / "case.json").write_text(json.dumps(c, ensure_ascii=False), encoding="utf-8")


def load_case(cid: str) -> None:
    src = CASES / safe(cid)
    if not (src / "brief.md").exists():
        raise ValueError("없는 프로젝트입니다")
    shutil.rmtree(ROOT / "project")
    shutil.copytree(src, ROOT / "project")


def list_cases() -> list[dict]:
    act = active_case()
    out = {act["id"]: dict(act, active=True)}
    if CASES.is_dir():
        for d in sorted(CASES.iterdir()):
            c = read_json(d / "case.json", None)
            if c and c["id"] not in out:
                out[c["id"]] = dict(c, active=False)
    return sorted(out.values(), key=lambda c: (not c["active"], c.get("created", "")))


def people() -> list[dict]:
    out = []
    for f in sorted((ROOT / "project/people").glob("*.md")):
        t = f.read_text(encoding="utf-8")
        head = (t.splitlines() or [""])[0].lstrip("# ").strip()
        out.append({"id": f.stem, "title": head, "text": t})
    return out


def case_view() -> dict:
    b = ROOT / "project/brief.md"
    text = b.read_text(encoding="utf-8") if b.exists() else ""
    m = re.search(r"## 상황\s*\n(.+?)(?:\n## |\Z)", text, re.S)
    rows = []
    reg = ROOT / "project/fact-pack/evidence-register.csv"
    if reg.exists():
        with open(reg, encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
    dom: dict[str, int] = {}
    for r in rows:
        dom[r.get("domain") or "기타"] = dom.get(r.get("domain") or "기타", 0) + 1
    notes = ROOT / "project/fact-pack/notes.md"
    return {"situation": (m.group(1).strip() if m else ""), "evidence": len(rows), "by_domain": dom,
            "uncertain": sum(r.get("status") in ("proposed", "uncertain") for r in rows),
            "notes": notes.read_text(encoding="utf-8") if notes.exists() else "", "people": people()}


def case_runs(cid: str) -> list[dict]:
    out = []
    if RUNS.is_dir():
        for d in sorted((x for x in RUNS.iterdir() if x.is_dir()), key=lambda x: x.stat().st_mtime, reverse=True):
            m = read_json(d / "run.json", {})
            if (m.get("case") or DEFAULT_CASE["id"]) == cid and (d / "brief.md").exists():
                out.append({"run": d.name, "label": run_label(d.name), "status": run_status(d.name), "person": m.get("person"), "parent": m.get("parent"), "verdict": read_json(d / "verdict.json", None),
                            "steps": run_steps(d.name),
                            "golden": (GOLDEN / d.name).exists(), "feedback": len(read_feedback(d))})
    return out


def run_steps(run: str) -> dict:
    """작업 흐름 5단계 중 어디까지 왔나: 브리핑 생성 · 피드백 · 기준 개선 · 재실행 · 골든"""
    lin = lineage(run)
    return {"brief": True, "feedback": any(read_feedback(RUNS / r) for r in lin), "improve": any((RUNS / r / "applied.json").exists() for r in lin),
            "rerun": len(lin) > 1, "golden": any(m.get("run") in lin for m in list_goldens())}


def activity(cid: str) -> list[dict]:
    ev = []
    for r in case_runs(cid):
        d = RUNS / r["run"]
        ev.append({"at": dt.datetime.fromtimestamp(d.stat().st_mtime).isoformat(timespec="seconds"), "kind": "brief", "text": f"{r['label']}가 나왔습니다", "run": r["run"]})
        for f in read_feedback(d):
            ev.append({"at": f.get("at", ""), "kind": "feedback", "text": f"{r['label']}에 피드백: {(f.get('comment') or '')[:40]}", "run": r["run"]})
    for h in applied_history():
        ev.append({"at": h["at"], "kind": "criteria", "text": f"기준 변경 승인: {', '.join(c['target'] for c in h['changes'])}" + (" (되돌림)" if h["reverted"] else ""), "run": h["new_run"]})
    for m in list_goldens():
        if m["scope"].get("case") == cid:
            ev.append({"at": m.get("approved_at") or "", "kind": "golden", "text": f"골든 v{m['golden_version']} 저장: {m.get('approval_reason', '')[:40]}", "run": m.get("run")})
    return sorted(ev, key=lambda e: e["at"], reverse=True)[:8]


def new_run_name(person: str) -> str:
    n = 1
    while (RUNS / f"{person}-{n:02d}").exists():
        n += 1
    return f"{person}-{n:02d}"


def topic_job(case: dict, ask: str) -> None:
    job = JOBS["_home"]
    before = active_case()
    try:
        job.update(step="지금 프로젝트를 보관하는 중", no=1, of=3, eta=5)
        save_active()
        rubric = (ROOT / "project/rubric.md").read_text(encoding="utf-8") if (ROOT / "project/rubric.md").exists() else ""
        shutil.rmtree(ROOT / "project")
        (ROOT / "project/people").mkdir(parents=True)
        (ROOT / "project/fact-pack").mkdir()
        if rubric:
            (ROOT / "project/rubric.md").write_text(rubric, encoding="utf-8")
        (ROOT / "project/case.json").write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")
        job.update(step="공개 자료를 찾아 열어 보고 사례를 만드는 중", no=2, of=3, eta=1200, started=dt.datetime.now().timestamp())
        out = claude_run(f"/mi-topic {ask} 바로\n\n(웹 화면에서 실행한다. 사용자에게 묻지 않는다. 이전 사례 보관과 git 은 프로그램이 이미 했으니 하지 않는다. project/ 는 비어 있다.)",
                         TOPIC_TOOLS, allow=("project",), timeout=2400)
        job.update(step="만든 사례를 점검하는 중", no=3, of=3, eta=5)
        for d in (ROOT / "project").glob("_*"):
            shutil.rmtree(d, ignore_errors=True)
        reg = ROOT / "project/fact-pack/evidence-register.csv"
        n = sum(1 for _ in csv.DictReader(open(reg, encoding="utf-8", newline=""))) if reg.exists() else 0
        if not people() or n < 6 or not (ROOT / "project/brief.md").exists():
            raise RuntimeError(f"사례를 다 만들지 못했습니다(근거 {n}건, 받는 사람 {len(people())}명). " + out[-300:])
        save_active()
        job.update(state="done", kind="topic")
    except Exception as e:                           # 실패하면 이전 프로젝트로 돌아간다
        try:
            if (CASES / before["id"] / "brief.md").exists():
                load_case(before["id"])
        except Exception:
            pass
        job.update(state="failed", error=str(e)[:400])


def brief_job(person: str) -> None:
    job = JOBS["_home"]
    try:
        run = new_run_name(person)
        job.update(step=f"{person} 의 브리핑을 쓰는 중 (판단표 → 브리핑 → 검사)", no=1, of=2, eta=300, run=run, started=dt.datetime.now().timestamp())
        before = {p.name for p in RUNS.iterdir() if p.is_dir()}
        out = claude_run(f"/mi-brief {person} {run}")
        made = sorted(p.name for p in RUNS.iterdir() if p.is_dir() and p.name not in before and (p / "brief.md").exists())
        if not made:
            raise RuntimeError("브리핑을 만들지 못했습니다. " + out[-300:])
        meta = read_json(RUNS / made[-1] / "run.json", {})
        meta.update(person=person, case=active_case()["id"], parent=None)      # 새로 만든 브리핑은 첫 판이다. 모델이 적은 이전 판을 믿지 않는다
        (RUNS / made[-1] / "run.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        job.update(step="판정 에이전트가 새 맥락에서 읽는 중", no=2, of=2, eta=100, started=dt.datetime.now().timestamp())
        claude_run(f"/mi-review {made[-1]}")
        job.update(state="done", kind="brief", new_run=made[-1])
    except Exception as e:
        job.update(state="failed", error=str(e)[:400])


EDITABLE = ("playbook/", "project/people/", "project/rubric.md", "my/")


def check_change(root: Path, c: dict) -> str:
    """수정안을 그대로 적용할 수 있으면 빈 문자열, 아니면 이유"""
    rel = str(c.get("file") or "")
    if ".." in rel or rel.startswith("/") or not (rel.startswith(EDITABLE)):
        return f"고칠 수 없는 파일입니다: {rel}"
    p = root / rel
    if not p.is_file():
        return f"없는 파일입니다: {rel}"
    before = c.get("before") or ""
    n = p.read_text(encoding="utf-8").count(before) if before else 0
    if n != 1:
        return f"바꿀 문구가 파일에 {n}번 있습니다(한 번이어야 합니다)"
    return ""


def apply_changes(root: Path, changes: list[dict]) -> list[str]:
    """승인된 수정안을 글자 그대로 적용한다. 하나라도 안 되면 아무것도 바꾸지 않는다"""
    for c in changes:
        err = check_change(root, c)
        if err:
            raise ValueError(f"{c.get('id')}: {err}")
    texts: dict[str, str] = {}
    for c in changes:
        rel = c["file"]
        cur = texts.get(rel, (root / rel).read_text(encoding="utf-8"))
        if cur.count(c["before"]) != 1:
            raise ValueError(f"{c.get('id')}: 다른 수정안과 겹칩니다")
        texts[rel] = cur.replace(c["before"], c.get("after") or "")
    for rel, text in texts.items():
        (root / rel).write_text(text, encoding="utf-8")
    return sorted(texts)


def git(*args: str, root: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-c", "user.name=mi-skillkit", "-c", "user.email=mi@local", *args], cwd=root or ROOT, capture_output=True, text=True)


def commit_paths(message: str, files: list[str], root: Path | None = None) -> str:
    """이 파일만 커밋하고 짧은 해시를 준다. 사용자가 올려 둔 다른 변경은 함께 커밋하지 않는다"""
    git("add", "--", *files, root=root)
    r = git("commit", "-qm", message, "--", *files, root=root)
    if r.returncode != 0:
        raise RuntimeError("커밋하지 못했습니다: " + (r.stderr or r.stdout)[:200])
    return git("rev-parse", "--short", "HEAD", root=root).stdout.strip()


def revert_commit(commit: str, root: Path | None = None) -> None:
    """그 승인만 되돌린다. 뒤에 승인한 다른 수정은 남긴다. 겹치면 아무것도 바꾸지 않고 알린다"""
    r = git("revert", "--no-edit", commit, root=root)
    if r.returncode != 0:
        git("revert", "--abort", root=root)
        raise ValueError("뒤에 승인한 수정과 겹쳐 되돌리지 못했습니다. 바뀐 파일은 없습니다")


def log_shave(rows: list[str], message: str) -> None:
    with open(ROOT / "shave-log.md", "a", encoding="utf-8") as f:
        f.writelines(rows)
    commit_paths(message, ["shave-log.md"])


def next_run(run: str) -> str:
    m = re.fullmatch(r"(.*?)-?(\d+)?", run)
    base, n = (m.group(1) or run), int(m.group(2) or 1)
    while True:
        n += 1
        name = f"{base}-{n:02d}"
        if not (RUNS / name).exists():
            return name


def selection_rows(d: Path) -> list[dict]:
    p = d / "selection.csv"
    if not p.exists():
        return []
    reg = load_register()
    with open(p, encoding="utf-8", newline="") as f:
        out = []
        for r in csv.DictReader(f):
            i = (r.get("evidence_id") or "").strip()
            out.append({"id": i, "send": (r.get("send") or "").strip(), "why": r.get("why") or "", "claim": reg.get(i, {}).get("claim", "")})
    return out


def removed_sentences(before: str, after: str) -> list[str]:
    """before 의 문장 중 after 에 그대로 남지 않은 것"""
    parts = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", before) if s.strip()]
    return [s for s in parts if s not in after]


def load_proposal(d: Path) -> dict | None:
    p = read_json(d / "proposal.json", None)
    if p is None:
        return None
    for i, c in enumerate(p.get("changes", [])):
        c["id"] = str(c.get("id", f"c{i + 1}"))
        c["problem"] = check_change(ROOT, c)
        c["target"] = TARGET_NAME.get(next((k for k in TARGET_NAME if str(c.get("file", "")).startswith(k)), ""), str(c.get("file", "")))
        after, before = c.get("after") or "", c.get("before") or ""
        lost = removed_sentences(before, after)
        if lost:
            c["removes"] = True                      # 기존 문장이 사라지면 표시한다 — 모델이 add 라고 적어도
            c["removed"] = lost
    net = sum(len(c.get("after") or "") - len(c.get("before") or "") for c in p.get("changes", []) if str(c.get("file", "")).startswith("playbook/"))
    p["playbook_growth"] = net                       # 규칙이 얼마나 늘어나는지 평가관에게 보여 준다
    return p


def propose_job(run: str) -> None:
    job = JOBS[run]
    try:
        job.update(step="피드백을 자료와 대조해 수정안을 만드는 중", no=1, of=1, eta=60)
        (RUNS / run / "proposal.json").unlink(missing_ok=True)
        out = claude_run(f"/mi-feedback {run}", PROPOSE_TOOLS.format(run=run))
        if load_proposal(RUNS / run) is None:
            job.update(state="failed", error="수정안을 만들지 못했습니다. " + out[-300:])
            return
        job.update(state="done", kind="propose")
    except Exception as e:                           # 어떤 실패든 화면에 알린다
        job.update(state="failed", error=str(e)[:300])


def apply_job(run: str) -> None:
    job = JOBS[run]
    try:
        d = RUNS / run
        prop = load_proposal(d) or {}
        ok = [c for c in prop.get("changes", []) if c.get("decision") == "approved"]
        head = git("rev-parse", "HEAD").stdout.strip()
        files = apply_changes(ROOT, ok)
        commit = commit_paths(f"{run} 피드백 승인 반영: " + " · ".join(c["id"] for c in ok), files)
        log_shave([f"| {run} | {c['file']} | {str(c.get('reason', '')).replace('|', '/')} | {','.join(map(str, c.get('from_feedback', [])))} | 승인 ({c.get('decided_by', '')}) |\n" for c in ok], f"{run} 깎기 기록")
        person = read_json(d / "run.json", {}).get("person")
        new = next_run(run)
        before = {p.name for p in RUNS.iterdir() if p.is_dir()}
        job.update(step="승인한 규칙으로 새 판을 만드는 중", no=1, of=2, eta=120)
        job["started"] = dt.datetime.now().timestamp()
        out = claude_run(f"/mi-brief {person} {new}")     # 이전 판의 피드백을 읽지 못하게 부모를 넘기지 않는다 — 승인한 규칙만 반영되게
        made = sorted(p.name for p in RUNS.iterdir() if p.is_dir() and p.name not in before and (p / "brief.md").exists())
        if not made:
            job.update(state="failed", error="새 판을 만들지 못했습니다. 승인한 수정은 반영되어 있습니다. " + out[-300:])
            return
        meta = read_json(RUNS / made[-1] / "run.json", {})
        meta.update(person=person, parent=run, skill_commit=commit, case=read_json(d / "run.json", {}).get("case") or active_case()["id"])
        (RUNS / made[-1] / "run.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        job.update(step="판정 에이전트가 새 판을 읽는 중", no=2, of=2, eta=70, started=dt.datetime.now().timestamp())
        claude_run(f"/mi-review {made[-1]}")
        diff = git("diff", head, commit, "--", *files).stdout
        (RUNS / made[-1] / "changes.diff").write_text(diff, encoding="utf-8")
        (RUNS / made[-1] / "applied.json").write_text(json.dumps({"from_run": run, "head_before": head, "commit": commit, "files": files}, ensure_ascii=False), encoding="utf-8")
        job.update(state="done", kind="apply", new_run=made[-1])
    except Exception as e:                           # 어떤 실패든 화면에 알린다
        job.update(state="failed", error=str(e)[:300])


def parent_feedback(d: Path) -> list[dict]:
    """이전 판의 지적이 새 판에서 해결됐는지 보려고 가져온다. 문장이 그대로 남았는지는 자동으로 표시한다"""
    parent = read_json(d / "run.json", {}).get("parent")
    if not parent or not (RUNS / parent).is_dir():
        return []
    text = (d / "brief.md").read_text(encoding="utf-8") if (d / "brief.md").exists() else ""
    resolved = (read_json(d / "ui.json", {}) or {}).get("resolved", {})
    return [{"id": x["id"], "quote": x.get("quote", ""), "comment": x.get("comment", ""), "category": x.get("category"), "still_there": bool(x.get("quote")) and x["quote"] in text,
             "state": resolved.get(x["id"])} for x in read_feedback(RUNS / parent) if x.get("kind") != "good"]


def board_html() -> str:
    rows = []
    for p in sorted((ROOT / "dev/results").glob("*.json")):
        try:
            rows.append(json.loads(p.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            pass
    rows.sort(key=lambda r: (-r.get("score", 0), r.get("cost_usd") or 1e9))
    body = "".join(f"<tr><td>{i + 1}</td><td>{html.escape(str(r.get('team')))}</td><td>{html.escape(str(r.get('golden')))} v{r.get('golden_version', 1)}</td><td>{r.get('score')}</td><td>{html.escape(' · '.join(r.get('statuses') or []))}</td><td>{'성공' if r.get('reproduced') else '—'}</td><td>{html.escape(str(r.get('level')))}</td><td>{html.escape(str(r.get('must')))}</td><td>{html.escape(str(r.get('never')))}</td><td>{r.get('fact_issues')}</td><td>{html.escape(str(r.get('stable')))}</td><td>{r.get('cost_usd')}</td><td>{r.get('seconds')}</td></tr>" for i, r in enumerate(rows))
    return f'<!doctype html><html lang="ko"><meta charset=utf-8><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="icon" href="data:,"><meta name="description" content="에이전트가 골든을 얼마나 재현했는지 보는 순위표"><title>재현 순위</title>{DOC_CSS}<style>body{{max-width:72rem}}</style><meta http-equiv=refresh content=15><body><h1>현재 골든과의 일치도</h1><p>골든은 한 컨설턴트가 승인한 판단 기준입니다. 점수는 정답률이 아니며 같은 골든 버전끼리만 비교합니다. 다른 결론은 «차이 검토»로 사람이 봅니다.</p><div class="tw"><table><tr><th>순</th><th>팀</th><th>기준 골든</th><th>일치도</th><th>상태</th><th>재현</th><th>단계</th><th>꼭 보냄</th><th>절대 뺌</th><th>사실 오류</th><th>안정성</th><th>비용($)</th><th>시간(초)</th></tr>{body}</table></div></body></html>'


def lineage(run: str) -> list[str]:
    seen, cur = [], run
    case = (read_json(RUNS / run / "run.json", {}) or {}).get("case") or "hanbit"
    while cur and cur not in seen and (RUNS / cur).is_dir() and ((read_json(RUNS / cur / "run.json", {}) or {}).get("case") or "hanbit") == case:
        seen.append(cur)                             # 다른 사례의 실행은 이전 판으로 잇지 않는다
        cur = read_json(RUNS / cur / "run.json", {}).get("parent")
    return seen


def diff_html(a: str, b: str) -> str:
    al, bl = a.splitlines(), b.splitlines()
    out = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, al, bl, autojunk=False).get_opcodes():
        if tag == "equal":
            out += [f"<div class=same>{html.escape(x) or '&nbsp;'}</div>" for x in al[i1:i2]]
        else:
            out += [f"<div class=del>− {html.escape(x)}</div>" for x in al[i1:i2]]
            out += [f"<div class=add>+ {html.escape(x)}</div>" for x in bl[j1:j2]]
    style = "<style>" + TOKENS + "html,body{overflow-x:clip}body{font:1rem/1.7 var(--font);max-width:56rem;margin:0 auto;padding:1.5rem 1rem;background:var(--paper);color:var(--ink);font-variant-numeric:tabular-nums}.del{background:var(--bad-soft);color:var(--accent)}.add{background:var(--ok-soft);color:var(--ok)}.same{color:var(--muted)}</style>"
    return f'<!doctype html><html lang="ko"><meta charset=utf-8><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="icon" href="data:,"><title>판 비교</title>{style}' + ("".join(out) or "<p>차이가 없습니다.</p>")


def sha_of(rel: str | None, n: int = 16) -> str | None:
    p = ROOT / rel if rel else None
    return hashlib.sha256(p.read_bytes()).hexdigest()[:n] if p and p.is_file() else None


def golden_meta(g: Path) -> dict:
    """옛 골든도 읽는다. 없는 필드는 기본값으로 채운다"""
    m = read_json(g / "golden.json", {})
    person = m.get("person") or (m.get("scope") or {}).get("persona")
    case = (m.get("case") or {}).get("id") if isinstance(m.get("case"), dict) else m.get("case")
    m.setdefault("golden_id", g.name)
    m.setdefault("golden_version", 1)
    m.setdefault("status", "active")
    m.setdefault("scope", {"case": case or DEFAULT_CASE["id"], "persona": person})
    m.setdefault("approved_at", m.get("at"))
    m.setdefault("approval_reason", (m.get("verdict") or {}).get("reason", ""))
    m["dir"] = g.name
    return m


def list_goldens() -> list[dict]:
    if not GOLDEN.is_dir():
        return []
    out = [golden_meta(g) for g in GOLDEN.iterdir() if g.is_dir() and (g / "golden.json").exists()]
    return sorted(out, key=lambda m: (str(m["scope"].get("case")), str(m["scope"].get("persona")), -int(m["golden_version"])))


def decision_date(person: str | None) -> str | None:
    f = ROOT / f"project/people/{person}.md"
    if not person or not f.exists():
        return None
    m = re.search(r"결정 시점:\*\*\s*(\d{4}-\d{2}-\d{2})", f.read_text(encoding="utf-8"))
    return m.group(1) if m else None


def freeze_golden(run: str, name: str | None = None, reason: str = "", reviewer: str = "") -> dict:
    """현재 판단 기준의 스냅샷을 새 버전으로 남긴다. 납품 판정과는 별개다. 같은 사람 · 사례의 이전 활성 골든은 «이전 기준»이 된다"""
    d = run_dir(run)
    if not reason.strip():
        raise ValueError("왜 이 결과를 승인하는지 한 줄 적어 주세요")
    grades = read_json(d / "grades.json", {})
    if not any(v == "must" for v in grades.values()) or not any(v == "never" for v in grades.values()):
        raise ValueError("«누구에게 보내나»에서 꼭 보낼 근거와 절대 뺄 근거를 하나 이상 정해 주세요")
    meta = read_json(d / "run.json", {})
    person, case = meta.get("person"), meta.get("case") or active_case()["id"]
    family = safe(f"{case}-{person}")
    same = [m for m in list_goldens() if m["scope"].get("case") == case and m["scope"].get("persona") == person]
    version = max([int(m["golden_version"]) for m in same] or [0]) + 1
    prev = next((m for m in same if m["status"] == "active"), None)
    g = GOLDEN / f"{family}-v{version}"
    if g.exists():
        raise ValueError(f"이미 있는 골든입니다: {g.name}")
    g.mkdir(parents=True)
    for f in doc_files(d):
        shutil.copy2(d / f, g / f)
    (g / "grades.json").write_text(json.dumps(grades, ensure_ascii=False, indent=1), encoding="utf-8")
    shutil.copytree(ROOT / "project/fact-pack", g / "fact-pack")      # 다른 사례로 바뀌어도 이 골든의 근거로 채점한다
    if person and (ROOT / f"project/people/{person}.md").exists():
        shutil.copy2(ROOT / f"project/people/{person}.md", g / "profile.md")
    if (ROOT / "my/lens.md").exists():
        shutil.copy2(ROOT / "my/lens.md", g / "lens.md")      # 판단 기준 순서도 재현 대상이다
    history = []
    for r in reversed(lineage(run)):
        history += [dict(x, run=r) for x in read_feedback(RUNS / r)]
    (g / "feedback-history.jsonl").write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in history), encoding="utf-8")
    labels = []
    for r in reversed(lineage(run)):
        labels += [dict(x, run=r) for x in read_suggestions(RUNS / r) if x.get("state")]
    (g / "judge-labels.jsonl").write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in labels), encoding="utf-8")
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from check_brief import check, load_rows
        issues = check((d / "brief.md").read_text(encoding="utf-8"), load_rows(str(ROOT / "project/fact-pack/evidence-register.csv")))
    except Exception as e:                           # 검사를 못 해도 저장은 한다. 못 한 이유를 남긴다
        issues = [{"gate": "검사 실패", "why": str(e)[:200]}]
    (g / "objective-checks.json").write_text(json.dumps({"issues": issues, "note": "check_brief 의 코드 검사 결과. 판단의 옳고 그름이 아니다"}, ensure_ascii=False, indent=1), encoding="utf-8")
    notes = ["# 비교 메모", "", f"- 승인 이유: {reason.strip()}", f"- 판단 흐름: {' → '.join(reversed(lineage(run)))}"]
    if prev:
        notes.append(f"- 대체한 골든: {prev['golden_id']} (v{prev['golden_version']}) — 그 승인 이유: {prev.get('approval_reason') or '기록 없음'}")
    if (d / "decision.md").exists():
        notes += ["", "## 판단표", "", (d / "decision.md").read_text(encoding="utf-8")]
    (g / "comparison-notes.md").write_text("\n".join(notes) + "\n", encoding="utf-8")
    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    except OSError:
        commit = ""
    now = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    manifest = {"golden_id": g.name, "golden_version": version, "status": "active", "supersedes": prev["golden_id"] if prev else None,
                "scope": {"case": case, "persona": person, "decision_date": decision_date(person)},
                "approved_by": reviewer or "컨설턴트", "approved_at": now, "approval_reason": reason.strip(),
                "skill_commit": meta.get("skill_commit") or commit, "lens_sha": sha_of("my/lens.md"), "evidence_sha": sha_of("project/fact-pack/evidence-register.csv"),
                "objective_checks": "objective-checks.json", "comparison_notes": "comparison-notes.md",
                "golden": g.name, "run": run, "case": active_case(), "lineage": lineage(run), "person": person, "verdict": read_json(d / "verdict.json", None), "at": now,
                "inputs": {"profile": f"project/people/{person}.md" if person else None, "profile_sha": sha_of(f"project/people/{person}.md", 12) if person else None,
                           "evidence": "project/fact-pack/evidence-register.csv", "evidence_sha": sha_of("project/fact-pack/evidence-register.csv", 12)}}
    (g / "golden.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    if prev:
        set_golden_status(prev["dir"], "superseded")
    return manifest


def set_golden_status(dirname: str, status: str) -> dict:
    if status not in ("active", "superseded", "retired"):
        raise ValueError("상태는 active · superseded · retired 중 하나입니다")
    g = GOLDEN / safe(dirname)
    m = read_json(g / "golden.json", None)
    if m is None:
        raise ValueError("없는 골든입니다")
    m["status"] = status
    (g / "golden.json").write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
    return golden_meta(g)


ORD = ["첫", "두", "세", "네", "다섯", "여섯", "일곱", "여덟", "아홉", "열"]


def person_label(person: str | None) -> str:
    f = ROOT / f"project/people/{person}.md"
    if person and f.exists():
        head = (f.read_text(encoding="utf-8").splitlines() or [""])[0].lstrip("# ").strip()
        return re.split(r"\s*[—-]\s*", head)[0] or person
    return person or ""


def run_label(run: str) -> str:
    m = read_json(RUNS / run / "run.json", {})
    n = len(lineage(run))
    return f"{person_label(m.get('person'))} · {ORD[n - 1] if n <= len(ORD) else n} 번째 브리핑"


def run_status(run: str) -> str:
    """분석 전 / 생성 중 / 검토 필요 / 기준 개선 중 / 승인됨"""
    d = RUNS / run
    job = JOBS.get(run)
    if job and job.get("state") == "running":
        return "기준 개선 중" if job.get("kind") in (None, "apply", "propose") else "생성 중"
    if (read_json(d / "verdict.json", {}) or {}).get("ok") or any(m.get("run") == run for m in list_goldens()):
        return "승인됨"
    if any((read_json(x / "run.json", {}) or {}).get("parent") == run for x in RUNS.iterdir() if x.is_dir()):
        return "이전 기준"                           # 승인한 기준으로 다음 판을 받았다
    p = read_json(d / "proposal.json", None)
    if p and p.get("changes"):
        return "기준 개선 중"
    return "검토 필요"


def applied_history() -> list[dict]:
    """승인한 기준 변경의 기록. 실행 기록에서만 읽고 없는 것은 지어내지 않는다"""
    rows = []
    if not RUNS.is_dir():
        return rows
    for d in RUNS.iterdir():
        a = read_json(d / "applied.json", None)
        if not a:
            continue
        src = RUNS / str(a.get("from_run"))
        prop = read_json(src / "proposal.json", {}) or {}
        fb = {x["id"]: x for x in read_feedback(src)}
        changes = [c for c in prop.get("changes", []) if c.get("decision") == "approved"]
        rows.append({"at": dt.datetime.fromtimestamp(d.stat().st_mtime).isoformat(timespec="seconds"), "from_run": a.get("from_run"), "new_run": d.name,
                     "from_label": run_label(a["from_run"]) if (RUNS / str(a.get("from_run"))).is_dir() else a.get("from_run"), "new_label": run_label(d.name),
                     "commit": a.get("commit"), "reverted": bool(a.get("reverted")),
                     "feedback": [fb[i].get("comment") or fb[i].get("quote") for c in changes for i in c.get("from_feedback", []) if i in fb][:3],
                     "changes": [{"target": TARGET_NAME.get(next((k for k in TARGET_NAME if str(c.get("file", "")).startswith(k)), ""), c.get("file")), "reason": c.get("reason", "")} for c in changes],
                     "approver": ", ".join(sorted({c.get("decided_by") or "컨설턴트" for c in changes}))})
    log = git("log", "--format=%h|%cI|%s", "--", "my/lens.md").stdout.splitlines()
    for line in log:
        h, at, subj = (line.split("|", 2) + ["", ""])[:3]
        if subj.startswith("내 판단 기준 직접 수정"):
            rows.append({"at": at[:19], "from_run": None, "new_run": None, "from_label": "", "new_label": "", "commit": h, "reverted": False,
                         "feedback": ["(피드백 없이 직접 수정)"], "changes": [{"target": "내 판단 기준", "reason": "판단 순서 · 기준을 직접 고침"}], "approver": "컨설턴트"})
    rows.sort(key=lambda r: r["at"])
    for i, r in enumerate(x for x in rows if not x["reverted"]):
        r["version"] = i + 2
    return rows


TARGET_NAME = {"playbook/": "공통 작업 규칙", "my/lens.md": "내 판단 기준", "project/people/": "받는 사람 설정", "project/rubric.md": "평가 루브릭"}


def lens_order() -> list[str]:
    f = ROOT / "my/lens.md"
    if not f.exists():
        return []
    m = re.search(r"## 판단 기준 순서[^\n]*\n(?:(?!\s*\d+\.)[^\n]*\n)*?((?:[ \t]*\d+\.[^\n]*\n?)+)", f.read_text(encoding="utf-8"))
    return [re.sub(r"^\s*\d+\.\s*", "", x).strip() for x in (m.group(1).splitlines() if m else []) if x.strip()]


def criteria_view() -> dict:
    hist = applied_history()
    return {"version": 1 + sum(not r["reverted"] for r in hist), "order": lens_order(), "lens": (ROOT / "my/lens.md").read_text(encoding="utf-8") if (ROOT / "my/lens.md").exists() else "",
            "history": hist}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, body, ctype="text/html; charset=utf-8", code=200):
        b = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b)

    def js(self, obj, code=200):
        self.send(json.dumps(obj, ensure_ascii=False), "application/json; charset=utf-8", code)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        try:
            if u.path == "/" and "run" not in q:
                self.send(HOME.read_text(encoding="utf-8").replace("/*TOKENS*/", TOKENS))
            elif u.path in ("/", "/review"):
                self.send(UI.read_text(encoding="utf-8").replace("/*TOKENS*/", TOKENS))
            elif u.path == "/api/home":
                c = active_case()
                self.js({"active": c, "cases": list_cases(), "case": case_view(), "runs": case_runs(c["id"]), "job": JOBS.get("_home"),
                         "criteria": {k: v for k, v in criteria_view().items() if k != "lens"}, "goldens": [m for m in list_goldens() if m["scope"].get("case") == c["id"]],
                         "activity": activity(c["id"])})
            elif u.path == "/api/criteria":
                self.js(criteria_view())
            elif u.path == "/api/goldens":
                self.js({"goldens": list_goldens()})
            elif u.path == "/api/runs":
                out = []
                if RUNS.is_dir():
                    cid = active_case()["id"]
                    for d in sorted((x for x in RUNS.iterdir() if x.is_dir()), key=lambda x: x.stat().st_mtime, reverse=True):
                        m = read_json(d / "run.json", {})
                        if (m.get("case") or DEFAULT_CASE["id"]) != cid:
                            continue
                        fb = read_feedback(d)
                        out.append({"run": d.name, "label": run_label(d.name), "status": run_status(d.name), "person": m.get("person"), "parent": m.get("parent"), "files": doc_files(d), "feedback": len(fb),
                                    "verdict": read_json(d / "verdict.json", None), "golden": (GOLDEN / d.name).exists()})
                self.js({"runs": out})
            elif u.path == "/api/run":
                d = run_dir(q["run"])
                ch = d / "changes.diff"
                self.js({"run": q["run"], "meta": read_json(d / "run.json", {}), "files": doc_files(d), "feedback": read_feedback(d), "suggestions": read_suggestions(d),
                         "ui": read_json(d / "ui.json", {}), "grades": read_json(d / "grades.json", {}), "selection": selection_rows(d), "proposal": load_proposal(d), "applied": read_json(d / "applied.json", None), "changes": ch.read_text(encoding="utf-8") if ch.exists() else "", "job": JOBS.get(q["run"]),
                         "verdict": read_json(d / "verdict.json", None), "lineage": lineage(q["run"]), "label": run_label(q["run"]), "status": run_status(q["run"]),
                         "person_label": person_label(read_json(d / "run.json", {}).get("person")), "case": active_case(), "criteria": {"version": criteria_view()["version"], "order": lens_order()},
                         "parent_feedback": parent_feedback(d), "lineage_labels": [run_label(r) for r in lineage(q["run"])]})
            elif u.path == "/api/evidence":
                self.js(load_register().get(q["id"]) or {"error": "근거 묶음에 없는 번호입니다"})
            elif u.path == "/board":
                self.send(board_html())
            elif u.path == "/doc":
                self.send(render_doc(run_dir(q["run"]) / safe(q["file"])))
            elif u.path == "/diff":
                a, b, f = run_dir(q["a"]) / safe(q["file"]), run_dir(q["b"]) / safe(q["file"]), q["file"]
                self.send(diff_html(a.read_text(encoding="utf-8") if a.exists() else "", b.read_text(encoding="utf-8") if b.exists() else ""))
            else:
                self.send("없음", code=404)
        except (ValueError, FileNotFoundError, KeyError) as e:
            self.js({"error": str(e)}, 400)
        except Exception as e:                       # 결과물이 이상해도 서버가 말없이 끊기지 않게 한다
            self.js({"error": f"화면을 만들지 못했습니다: {e}"}, 500)

    def do_POST(self):
        if self.headers.get("Origin") and urllib.parse.urlparse(self.headers["Origin"]).hostname not in ("127.0.0.1", "localhost"):
            return self.js({"error": "이 PC 의 화면에서만 저장할 수 있습니다"}, 403)
        try:
            data = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            if self.path == "/api/feedback":
                d = run_dir(data["run"])
                item = {k: data.get(k) for k in ("file", "quote", "comment", "kind", "reviewer", "occurrence", "category")}
                if not (item["comment"] or "").strip() and item["kind"] != "good":
                    raise ValueError("무엇이 문제인지 한 줄 적어 주세요")
                item.update(id=uuid.uuid4().hex[:8], at=dt.datetime.now().isoformat(timespec="seconds"))
                write_feedback(d, read_feedback(d) + [item])
                self.js(item)
            elif self.path == "/api/feedback/delete":
                d = run_dir(data["run"])
                write_feedback(d, [x for x in read_feedback(d) if x["id"] != data["id"]])
                self.js({"ok": True})
            elif self.path == "/api/suggestion":
                d = run_dir(data["run"])
                items = read_suggestions(d)
                s = next((x for x in items if x["id"] == str(data["id"])), None)
                if s is None:
                    raise ValueError("없는 의견입니다")
                if not data.get("accept") and not str(data.get("note", "")).strip():
                    raise ValueError("반대하는 이유를 한 줄 적어 주세요")
                s.update(state="accepted" if data.get("accept") else "rejected", reviewer=data.get("reviewer", ""), note=data.get("note", ""))
                write_suggestions(d, items)
                if data.get("accept"):
                    item = {"file": s.get("file"), "quote": s.get("quote"), "comment": data.get("note") or s.get("comment"), "kind": s.get("kind", "fix"),
                            "reviewer": data.get("reviewer", ""), "occurrence": 0, "id": uuid.uuid4().hex[:8], "from_suggestion": s["id"],
                            "at": dt.datetime.now().isoformat(timespec="seconds")}
                    write_feedback(d, read_feedback(d) + [item])
                self.js(s)
            elif self.path == "/api/grade":
                d = run_dir(data["run"])
                g = read_json(d / "grades.json", {})
                if data.get("grade") not in ("must", "never", "any"):
                    raise ValueError("등급은 must · never · any 중 하나입니다")
                g[str(data["id"])] = data["grade"]
                (d / "grades.json").write_text(json.dumps(g, ensure_ascii=False, indent=1), encoding="utf-8")
                self.js(g)
            elif self.path == "/api/reveal":
                d = run_dir(data["run"])
                ui = {"revealed": True, "own_feedback": len(read_feedback(d)), "at": dt.datetime.now().isoformat(timespec="seconds")}
                (d / "ui.json").write_text(json.dumps(ui, ensure_ascii=False), encoding="utf-8")
                self.js(ui)
            elif self.path in ("/api/propose", "/api/apply"):
                run = safe(data["run"])
                d = run_dir(run)
                if self.path == "/api/propose":
                    if not read_feedback(d):
                        raise ValueError("반영할 피드백이 없습니다. 지적을 남기거나 의견에 동의해 주세요")
                    target = propose_job
                else:
                    prop = load_proposal(d) or {}
                    cs = prop.get("changes", [])
                    if any(not c.get("decision") for c in cs):
                        raise ValueError("모든 수정안을 승인하거나 거절해 주세요")
                    if not any(c.get("decision") == "approved" for c in cs):
                        raise ValueError("승인한 수정안이 없습니다")
                    bad = [c["id"] for c in cs if c.get("decision") == "approved" and c.get("problem")]
                    if bad:
                        raise ValueError("적용할 수 없는 수정안을 승인했습니다: " + ",".join(bad))
                    target = apply_job
                with JOB_LOCK:
                    if any(j["state"] == "running" for j in JOBS.values()):
                        raise ValueError("다른 작업이 진행 중입니다")
                    JOBS[run] = {"state": "running", "step": "시작", "no": 1, "of": 1, "eta": 60, "started": dt.datetime.now().timestamp()}
                threading.Thread(target=target, args=(run,), daemon=True).start()
                self.js(JOBS[run])
            elif self.path == "/api/decide":
                d = run_dir(data["run"])
                prop = read_json(d / "proposal.json", None)
                if not prop:
                    raise ValueError("수정안이 없습니다")
                c = next((x for i, x in enumerate(prop.get("changes", [])) if str(x.get("id", f"c{i + 1}")) == str(data["id"])), None)
                if c is None:
                    raise ValueError("없는 수정안입니다")
                c.update(decision="approved" if data.get("approve") else "rejected", decided_by=data.get("reviewer", ""), note=data.get("note", ""))
                (d / "proposal.json").write_text(json.dumps(prop, ensure_ascii=False, indent=1), encoding="utf-8")
                self.js(c)
            elif self.path == "/api/revert":
                d = run_dir(data["run"])
                a = read_json(d / "applied.json", None)
                if not a:
                    raise ValueError("되돌릴 변경이 없습니다")
                if a.get("reverted"):
                    raise ValueError("이미 되돌렸습니다")
                revert_commit(a["commit"])
                log_shave([f"| {a.get('from_run', data['run'])} | {', '.join(a['files'])} | 되돌림 ({a['commit']}) | | 되돌림 |\n"], f"{data['run']} 의 스킬 변경 되돌리기")
                a["reverted"] = True
                (d / "applied.json").write_text(json.dumps(a, ensure_ascii=False), encoding="utf-8")
                self.js(a)
            elif self.path == "/api/verdict":
                d = run_dir(data["run"])
                v = {"ok": bool(data.get("ok")), "reason": data.get("reason", ""), "reviewer": data.get("reviewer", ""), "at": dt.datetime.now().isoformat(timespec="seconds")}
                (d / "verdict.json").write_text(json.dumps(v, ensure_ascii=False, indent=1), encoding="utf-8")
                self.js(v)
            elif self.path in ("/api/case/new", "/api/brief"):
                if self.path == "/api/case/new":
                    topic = str(data.get("topic", "")).strip()
                    if len(topic) < 4:
                        raise ValueError("주제를 한 줄 적어 주세요")
                    extra = [f"{k}: {str(data.get(f, '')).strip()}" for k, f in (("고객", "customer"), ("받는 사람", "people"), ("범위", "scope")) if str(data.get(f, "")).strip()]
                    cid = "c" + dt.datetime.now().strftime("%m%d%H%M%S")
                    case = {"id": cid, "title": topic[:60], "created": dt.datetime.now().isoformat(timespec="seconds")}
                    target, args = topic_job, (case, topic + ("\n" + "\n".join(extra) if extra else ""))
                else:
                    person = safe(str(data.get("person", "")))
                    if not (ROOT / f"project/people/{person}.md").exists():
                        raise ValueError("없는 받는 사람입니다")
                    target, args = brief_job, (person,)
                with JOB_LOCK:
                    if any(j["state"] == "running" for j in JOBS.values()):
                        raise ValueError("다른 작업이 진행 중입니다")
                    JOBS["_home"] = {"state": "running", "step": "시작", "no": 1, "of": 1, "eta": 60, "started": dt.datetime.now().timestamp(), "kind": "topic" if target is topic_job else "brief"}
                threading.Thread(target=target, args=args, daemon=True).start()
                self.js(JOBS["_home"])
            elif self.path == "/api/case/activate":
                with JOB_LOCK:
                    if any(j["state"] == "running" for j in JOBS.values()):
                        raise ValueError("작업이 끝난 뒤에 바꿀 수 있습니다")
                    if data["id"] != active_case()["id"]:
                        save_active()
                        load_case(data["id"])
                self.js(active_case())
            elif self.path == "/api/person/save":
                if any(j["state"] == "running" for j in JOBS.values()):
                    raise ValueError("작업이 끝난 뒤에 저장할 수 있습니다")
                pid = safe(str(data.get("id", "")))
                f = ROOT / f"project/people/{pid}.md"
                if not f.exists():
                    raise ValueError("없는 받는 사람입니다")
                text = str(data.get("text", ""))
                if "결정" not in text:
                    raise ValueError("프로필에 «결정할 일»이 있어야 합니다")
                f.write_text(text.rstrip() + "\n", encoding="utf-8")
                save_active()
                self.js({"ok": True})
            elif self.path == "/api/golden":
                self.js(freeze_golden(data["run"], None, str(data.get("reason", "")), str(data.get("reviewer", ""))))
            elif self.path == "/api/golden/status":
                self.js(set_golden_status(str(data.get("id", "")), str(data.get("status", ""))))
            elif self.path == "/api/lens/save":
                text = str(data.get("text", ""))
                if "## 판단 기준 순서" not in text:
                    raise ValueError("«## 판단 기준 순서» 제목은 남겨 주세요")
                (ROOT / "my/lens.md").write_text(text.rstrip() + "\n", encoding="utf-8")
                commit_paths("내 판단 기준 직접 수정", ["my/lens.md"])
                self.js(criteria_view())
            elif self.path == "/api/resolve":
                d = run_dir(data["run"])
                ui = read_json(d / "ui.json", {}) or {}
                if data.get("state") not in ("fixed", "open", "worse"):
                    raise ValueError("해결됨 · 아직 · 나빠짐 중 하나입니다")
                ui.setdefault("resolved", {})[str(data["id"])] = data["state"]
                (d / "ui.json").write_text(json.dumps(ui, ensure_ascii=False), encoding="utf-8")
                self.js(ui)
            else:
                self.js({"error": "없음"}, 404)
        except (ValueError, FileNotFoundError, KeyError, json.JSONDecodeError) as e:
            self.js({"error": str(e)}, 400)
        except Exception as e:                       # 저장 실패가 «Failed to fetch» 로 끊기지 않게 한다
            self.js({"error": f"저장하지 못했습니다: {e}"}, 500)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args()
    RUNS.mkdir(exist_ok=True); GOLDEN.mkdir(exist_ok=True); CASES.mkdir(exist_ok=True)
    if not (CASES / active_case()["id"]).exists():
        save_active()
    print(f"검토 화면: http://127.0.0.1:{a.port}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", a.port), H).serve_forever()


if __name__ == "__main__":
    main()
