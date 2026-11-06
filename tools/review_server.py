#!/usr/bin/env python3
"""review_server.py — 결과물을 브라우저로 보고, 하이라이트로 피드백하고, 만족하면 골든으로 저장한다

  python3 tools/review_server.py [--port 8765]   → http://127.0.0.1:8765

표준 라이브러리만 쓴다. 내 PC 안에서만 열린다(127.0.0.1). 결과물 형식은 가리지 않는다: .md · .html · .csv · .txt
  runs/<run>/            결과물 · run.json · feedback.jsonl · verdict.json
  golden/<run>/          만족한 결과의 동결본 (결과물 · 피드백 이력 · 스킬 버전)
"""
from __future__ import annotations
import argparse, csv, datetime as dt, difflib, hashlib, html, io, json, os, re, shutil, subprocess, threading, urllib.parse, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS, GOLDEN = ROOT / "runs", ROOT / "golden"
UI = Path(__file__).with_name("review_ui.html")
DOC_CSS = """<style>
body{font:16px/1.7 -apple-system,'Apple SD Gothic Neo','Malgun Gothic',sans-serif;max-width:820px;margin:24px auto;padding:0 20px;color:#1c1c20;background:#fff}
h1{font-size:25px}h2{font-size:20px;margin-top:28px}table{border-collapse:collapse;width:100%;font-size:14px}th,td{border:1px solid #ddd;padding:6px 9px;text-align:left;vertical-align:top}th{background:#f4f4f6}
blockquote{border-left:3px solid #bbb;margin:0;padding-left:14px;color:#555}a.ev{font-size:12px;color:#3556c9;text-decoration:none;background:#eef1fb;border-radius:4px;padding:0 4px}
mark.fb{background:#ffe58a;cursor:pointer}mark.fb.good{background:#bdeec8}mark.fb.done{background:#e6e6e6}tr.sel-yes td:first-child{border-left:4px solid #2a8f4a}tr.sel-no{color:#777}
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
            return f'<a class="ev" style="background:#fde3e3;color:#b00" title="근거 묶음에 없는 ID">{m.group(0)}</a>'
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
            out.append("<table>" + "".join("<tr>" + "".join(f"<{'th' if i == 0 else 'td'}>{inline(c, reg)}</{'th' if i == 0 else 'td'}>" for c in r) + "</tr>" for i, r in enumerate(body)) + "</table>")
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
    h = "<table><tr>" + "".join(f"<th>{html.escape(c)}</th>" for c in head + extra) + "</tr>"
    for r in body:
        if len(r) > len(head):                       # 쉼표를 따옴표로 감싸지 않은 칸은 마지막 칸에 합친다
            r = r[:len(head) - 1] + [",".join(r[len(head) - 1:])]
        cl = f' class="sel-{"yes" if r[idx].strip().lower() == "yes" else "no"}"' if 0 <= idx < len(r) else ""
        cells = "".join(f"<td>{inline(c, reg)}</td>" for c in r)
        if extra:
            e = reg.get(r[eid].strip(), {}) if eid < len(r) else {}
            cells += f"<td>{html.escape(e.get('claim', ''))}</td><td>{html.escape(e.get('publisher', ''))} · {html.escape(e.get('data_period') or e.get('published_at') or '')} · {html.escape(e.get('status', ''))}</td>"
        h += f"<tr{cl}>{cells}</tr>"
    return h + "</table>"


def render_doc(path: Path) -> str:
    text, reg = path.read_text(encoding="utf-8", errors="replace"), load_register()
    if path.suffix in (".html", ".htm"):
        return text
    body = md_to_html(text, reg) if path.suffix == ".md" else csv_to_html(text, reg) if path.suffix == ".csv" else f"<pre>{html.escape(text)}</pre>"
    return f"<!doctype html><meta charset=utf-8>{DOC_CSS}<body>{body}</body>"


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
    hide = {"feedback.jsonl", "verdict.json", "run.json", "suggestions.jsonl", "ui.json", "changes.diff", "proposal.json", "applied.json", "review.md"}
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
TOOLS = ("Read,Edit(playbook/**),Write(playbook/**),Edit(project/people/**),Write(project/people/**),Edit(project/rubric.md),Edit(my/**),Edit(shave-log.md),Write(shave-log.md),"
         "Write(runs/**),Edit(runs/**),Bash(python3 tools/*),Bash(git status*),Bash(git add*),Bash(git commit*),Bash(git rev-parse*),Bash(git log*),Bash(git diff*),Bash(mkdir*)")


def claude_run(prompt: str) -> str:
    cmd = ["claude", "-p", prompt, "--model", os.environ.get("MI_MODEL", "claude-sonnet-5-5"), "--permission-mode", "acceptEdits", "--allowedTools", TOOLS, "--output-format", "text"]
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=600).stdout


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


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-c", "user.name=mi-skillkit", "-c", "user.email=mi@local", *args], cwd=ROOT, capture_output=True, text=True)


def next_run(run: str) -> str:
    m = re.fullmatch(r"(.*?)-?(\d+)?", run)
    base, n = (m.group(1) or run), int(m.group(2) or 1)
    while True:
        n += 1
        name = f"{base}-{n:02d}"
        if not (RUNS / name).exists():
            return name


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
        after, before = c.get("after") or "", c.get("before") or ""
        lost = removed_sentences(before, after)
        if lost:
            c["removes"] = True                      # 기존 문장이 사라지면 표시한다 — 모델이 add 라고 적어도
            c["removed"] = lost
    return p


def propose_job(run: str) -> None:
    job = JOBS[run]
    try:
        job.update(step="피드백을 자료와 대조해 수정안을 만드는 중", no=1, of=1, eta=60)
        (RUNS / run / "proposal.json").unlink(missing_ok=True)
        out = claude_run(f"/mi-feedback {run}")
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
        git("add", "--", *files)
        git("commit", "-qm", f"{run} 피드백 승인 반영: " + " · ".join(c["id"] for c in ok))
        commit = git("rev-parse", "--short", "HEAD").stdout.strip()
        with open(ROOT / "shave-log.md", "a", encoding="utf-8") as f:
            for c in ok:
                f.write(f"| {run} | {c['file']} | {str(c.get('reason', '')).replace('|', '/')} | {','.join(map(str, c.get('from_feedback', [])))} | 승인 ({c.get('decided_by', '')}) |\n")
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
        meta.update(person=person, parent=run, skill_commit=commit)
        (RUNS / made[-1] / "run.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        job.update(step="판정 에이전트가 새 판을 읽는 중", no=2, of=2, eta=70, started=dt.datetime.now().timestamp())
        claude_run(f"/mi-review {made[-1]}")
        diff = git("diff", head, commit, "--", *files).stdout
        (RUNS / made[-1] / "changes.diff").write_text(diff, encoding="utf-8")
        (RUNS / made[-1] / "applied.json").write_text(json.dumps({"from_run": run, "head_before": head, "commit": commit, "files": files}, ensure_ascii=False), encoding="utf-8")
        job.update(state="done", kind="apply", new_run=made[-1])
    except Exception as e:                           # 어떤 실패든 화면에 알린다
        job.update(state="failed", error=str(e)[:300])


def lineage(run: str) -> list[str]:
    seen, cur = [], run
    while cur and cur not in seen and (RUNS / cur).is_dir():
        seen.append(cur)
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
    style = "<style>body{font:15px/1.65 -apple-system,'Apple SD Gothic Neo','Malgun Gothic',sans-serif;max-width:900px;margin:20px auto;padding:0 16px}.del{background:#fde7e7;color:#8a1f1f}.add{background:#e2f6e7;color:#14602e}.same{color:#555}</style>"
    return f"<!doctype html><meta charset=utf-8>{style}" + ("".join(out) or "<p>차이가 없습니다.</p>")


def freeze_golden(run: str, name: str | None) -> dict:
    d = run_dir(run)
    v = read_json(d / "verdict.json", {})
    if not v.get("ok"):
        raise ValueError("«납품해도 됨» 판정이 있어야 골든으로 저장합니다")
    g = GOLDEN / safe(name or run)
    if g.exists():
        raise ValueError(f"이미 있는 골든입니다: {g.name}")
    g.mkdir(parents=True)
    for f in doc_files(d):
        shutil.copy2(d / f, g / f)
    history = []
    for r in reversed(lineage(run)):
        history += [dict(x, run=r) for x in read_feedback(RUNS / r)]
    (g / "feedback-history.jsonl").write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in history), encoding="utf-8")
    labels = []
    for r in reversed(lineage(run)):
        labels += [dict(x, run=r) for x in read_suggestions(RUNS / r) if x.get("state")]
    (g / "judge-labels.jsonl").write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in labels), encoding="utf-8")
    meta = read_json(d / "run.json", {})
    def sha(rel):
        p = ROOT / rel if rel else None
        return hashlib.sha256(p.read_bytes()).hexdigest()[:12] if p and p.is_file() else None
    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    except OSError:
        commit = ""
    person = meta.get("person")
    manifest = {"golden": g.name, "run": run, "lineage": lineage(run), "person": person, "verdict": v, "skill_commit": meta.get("skill_commit") or commit,
                "at": dt.datetime.now().isoformat(timespec="seconds"),
                "inputs": {"profile": f"project/people/{person}.md" if person else None, "profile_sha": sha(f"project/people/{person}.md") if person else None,
                           "evidence": "project/fact-pack/evidence-register.csv", "evidence_sha": sha("project/fact-pack/evidence-register.csv")}}
    (g / "golden.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    return manifest


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
            if u.path == "/":
                self.send(UI.read_text(encoding="utf-8"))
            elif u.path == "/api/runs":
                out = []
                if RUNS.is_dir():
                    for d in sorted((x for x in RUNS.iterdir() if x.is_dir()), key=lambda x: x.stat().st_mtime, reverse=True):
                        m = read_json(d / "run.json", {})
                        fb = read_feedback(d)
                        out.append({"run": d.name, "person": m.get("person"), "parent": m.get("parent"), "files": doc_files(d), "feedback": len(fb),
                                    "verdict": read_json(d / "verdict.json", None), "golden": (GOLDEN / d.name).exists()})
                self.js({"runs": out})
            elif u.path == "/api/run":
                d = run_dir(q["run"])
                ch = d / "changes.diff"
                self.js({"run": q["run"], "meta": read_json(d / "run.json", {}), "files": doc_files(d), "feedback": read_feedback(d), "suggestions": read_suggestions(d),
                         "ui": read_json(d / "ui.json", {}), "proposal": load_proposal(d), "applied": read_json(d / "applied.json", None), "changes": ch.read_text(encoding="utf-8") if ch.exists() else "", "job": JOBS.get(q["run"]),
                         "verdict": read_json(d / "verdict.json", None), "lineage": lineage(q["run"])})
            elif u.path == "/api/evidence":
                self.js(load_register().get(q["id"]) or {"error": "근거 묶음에 없는 번호입니다"})
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
                item = {k: data.get(k) for k in ("file", "quote", "comment", "kind", "reviewer", "occurrence")}
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
                if git("checkout", a["head_before"], "--", *a["files"]).returncode != 0:
                    raise ValueError("되돌리지 못했습니다")
                git("add", "--", *a["files"])
                git("commit", "-qm", f"{data['run']} 의 스킬 변경 되돌리기")
                a["reverted"] = True
                (d / "applied.json").write_text(json.dumps(a, ensure_ascii=False), encoding="utf-8")
                self.js(a)
            elif self.path == "/api/verdict":
                d = run_dir(data["run"])
                v = {"ok": bool(data.get("ok")), "reason": data.get("reason", ""), "reviewer": data.get("reviewer", ""), "at": dt.datetime.now().isoformat(timespec="seconds")}
                (d / "verdict.json").write_text(json.dumps(v, ensure_ascii=False, indent=1), encoding="utf-8")
                self.js(v)
            elif self.path == "/api/golden":
                self.js(freeze_golden(data["run"], data.get("name")))
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
    RUNS.mkdir(exist_ok=True); GOLDEN.mkdir(exist_ok=True)
    print(f"검토 화면: http://127.0.0.1:{a.port}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", a.port), H).serve_forever()


if __name__ == "__main__":
    main()
