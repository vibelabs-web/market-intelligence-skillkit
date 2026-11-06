import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, followJob, reviewer, type Job } from "../lib/api";
import { renderMarkdown, lineDiff } from "../lib/markdown";
import { Chip, ErrorBox, JobProgress, Steps } from "../components/ui";
import { STEP_NAMES } from "./Project";

const KIND: Record<string, string> = { fix: "고쳐야 함", remove: "빼야 함", missing: "더 있어야 함", good: "유지" };
const CATS = ["사실", "해석", "개인화", "형식"];
const GRADE: [string, string][] = [["must", "꼭 보냄"], ["never", "절대 뺌"], ["any", "상관없음"]];
const esc = (s: string) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]!);

export default function Review() {
  const { run } = useParams(), nav = useNavigate();
  const [d, setD] = useState<any>(null), [error, setError] = useState<string | null>(null), [job, setJob] = useState<Job | null>(null);
  const [tab, setTab] = useState("brief"), [sel, setSel] = useState<{ quote: string; x: number; y: number } | null>(null);
  const [cat, setCat] = useState<string | null>(null), [comment, setComment] = useState(""), [ev, setEv] = useState<any>(null);
  const [who, setWho] = useState(reviewer.get()), [reason, setReason] = useState(""), [notes, setNotes] = useState<Record<string, string>>({});
  const docRef = useRef<HTMLDivElement>(null);
  const load = () => api(`/api/runs/${run}`).then((x) => { setD(x); if (x.job?.state === "running") setJob(x.job); }).catch((e) => setError(e.message));
  useEffect(() => { setD(null); setTab("brief"); load(); }, [run]);
  useEffect(() => {
    if (job?.state !== "running") return;
    return followJob(job.id, (j) => { setJob(j); if (j.state === "done" && j.result?.new_run) nav(`/briefs/${j.result.new_run}`); else if (j.state !== "running") load(); });
  }, [job?.id]);
  const known = useMemo(() => new Set<string>((d?.selection ?? []).map((r: any) => r.evidence_id)), [d]);
  const html = useMemo(() => {
    if (!d) return "";
    let h = renderMarkdown(d.brief, new Set([...known, ...(d.brief.match(/\b[EI]-\d{3}\b/g) ?? [])]));
    for (const f of d.feedback) if (f.quote && h.includes(esc(f.quote))) h = h.replace(esc(f.quote), `<mark class="fb${f.kind === "good" ? " fb-good" : ""}" title="${esc(KIND[f.kind] + " · " + f.comment)}">${esc(f.quote)}</mark>`);
    return h;
  }, [d, known]);
  if (!d) return <><ErrorBox error={error} /><p className="text-muted">불러오는 중…</p></>;

  const busy = job?.state === "running";
  const call = async (url: string, body: unknown = {}, after?: (r: any) => void) => {
    setError(null);
    try { const r = await api(url, { reviewer: who, ...(body as object) }); if (r?.job) setJob(r.job); after ? after(r) : load(); } catch (e: any) { setError(e.message); }
  };
  const mouseUp = () => {
    const s = window.getSelection(); const q = s?.toString().replace(/\s+/g, " ").trim() ?? "";
    if (q.length < 4 || !s?.rangeCount) return;
    const r = s.getRangeAt(0).getBoundingClientRect();
    setSel({ quote: q, x: Math.min(r.left, window.innerWidth - 340), y: r.bottom + 8 }); setCat(null); setComment("");
  };
  const docClick = async (e: React.MouseEvent) => {
    const a = (e.target as HTMLElement).closest(".ev") as HTMLElement | null;
    if (!a) return;
    try { setEv(await api(`/api/projects/${d.meta.project}/evidence/${a.dataset.ev}`)); } catch (er: any) { setEv({ evidence_id: a.dataset.ev, claim: er.message }); }
  };
  const addFb = (kind: string) => call(`/api/runs/${run}/feedback`, { quote: sel!.quote, comment, kind, category: cat }, () => { setSel(null); window.getSelection()?.removeAllRanges(); load(); });

  const fb: any[] = d.feedback, prop = d.proposal, changes: any[] = prop?.changes ?? [];
  const undecided = changes.filter((c) => !c.decision).length, approved = changes.filter((c) => c.decision === "approved").length;
  const pending = d.parentFeedback.filter((x: any) => !x.state).length;
  const superseded = d.status === "이전 기준";
  const grades = d.grades, hasMust = Object.values(grades).includes("must"), hasNever = Object.values(grades).includes("never");
  const steps = { brief: true, feedback: fb.length > 0 || d.lineage.length > 1, improve: !!d.applied, rerun: d.lineage.length > 1, golden: !!d.golden };

  let now: { text: string; act?: React.ReactNode };
  if (busy) now = { text: "AI 가 작업하는 중입니다. 끝나면 이 화면이 바뀝니다." };
  else if (d.golden) now = { text: `골든 v${d.golden.golden_version} 으로 저장했습니다. 개발자가 이 결과를 재현합니다.`, act: <Link className="btn" to="/goldens">골든 라이브러리</Link> };
  else if (superseded) now = { text: "이 판은 고친 기준으로 다시 만든 새 판으로 대체됐습니다.", act: <Link className="btn" to={`/projects/${d.meta.project}`}>새 판 보러 가기</Link> };
  else if (pending) now = { text: `지난 판에서 지적한 문제 ${pending}개가 해결됐는지 먼저 표시하세요.` };
  else if (undecided) now = { text: `판단 기준 수정안 ${undecided}개를 하나씩 승인하거나 거절하세요.` };
  else if (approved && !superseded) now = { text: "승인한 수정안으로 판단 기준을 고치고 브리핑을 다시 만듭니다.", act: <button className="btn-primary" onClick={() => call(`/api/runs/${run}/apply`)}>승인한 수정안으로 다시 만들기</button> };
  else if (fb.some((x) => x.kind !== "good") && !prop) now = { text: `지적 ${fb.length}개를 모았습니다. 이 지적을 판단 기준 수정안으로 바꿉니다.`, act: <button className="btn-primary" onClick={() => call(`/api/runs/${run}/propose`)}>지적으로 기준 수정안 만들기</button> };
  else if (prop && !changes.length) now = { text: "AI 가 고칠 기준을 찾지 못했습니다. 지적을 더 구체적으로 적거나, 문제가 없으면 승인하세요.", act: <button className="btn" onClick={() => setTab("approve")}>승인으로</button> };
  else now = { text: "브리핑을 받는 사람의 눈으로 읽고, 문제 있는 문장을 마우스로 끌어 지적하세요. 문제가 없으면 골든으로 승인합니다.", act: <button className="btn" onClick={() => setTab("approve")}>문제 없음 · 승인으로</button> };

  const tabs: [string, string][] = [["brief", "브리핑"], ["decision", "판단표"], ["send", "누구에게 보내나"], ...(d.parentBrief ? [["diff", "이전 판과 비교"]] as [string, string][] : []), ["approve", "승인"]];
  return (
    <div className="space-y-5">
      <header className="space-y-2">
        <p className="hint"><Link className="btn-link" to={`/projects/${d.meta.project}`}>{d.project.title}</Link> · 내 판단 기준 v{d.criteria.version}</p>
        <div className="flex flex-wrap items-center gap-2"><h1 className="text-xl font-extrabold">{d.label}</h1><Chip s={d.status} /></div>
        {d.lineage.length > 1 && <p className="text-sm text-muted">이어진 판: {d.lineage.slice().reverse().map((l: any, i: number) => <span key={l.run}>{i > 0 && " → "}{l.run === run ? <b>{l.label}</b> : <Link className="btn-link" to={`/briefs/${l.run}`}>{l.label}</Link>}</span>)}</p>}
        <Steps steps={steps} names={STEP_NAMES} />
      </header>
      <ErrorBox error={error} />
      <section className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border-2 border-accent bg-accent-soft/40 px-4 py-3" aria-label="지금 할 일">
        <p className="text-sm"><b className="mr-2 text-accent">지금 할 일</b>{now.text}</p>{now.act}
      </section>
      {job && (busy || job.state === "failed") && <JobProgress job={job} showLog={false} />}

      {d.parentFeedback.length > 0 && <section className="card">
        <h2 className="font-bold">지난 판에서 지적한 문제가 해결됐나요?</h2>
        <p className="hint mb-3">얼마나 달라졌는지보다, 지적한 문제가 풀렸는지와 다른 곳이 나빠지지 않았는지를 봅니다.</p>
        <ul className="space-y-2">{d.parentFeedback.map((x: any) => (
          <li key={x.id} className="rounded-xl bg-paper p-3 text-sm">
            {x.quote && <q className="block text-ink-2">{x.quote}</q>}<span>{x.comment}</span>{x.category && <span className="hint"> [{x.category}]</span>}
            <span className="hint block">{x.stillThere ? "이 문장이 새 판에도 그대로 있습니다" : "이 문장은 새 판에서 바뀌었습니다"}</span>
            <div className="mt-2 flex gap-2">{[["fixed", "해결됨"], ["open", "아직"], ["worse", "나빠짐"]].map(([k, l]) => (
              <button key={k} className={`btn px-2 py-1 text-xs ${x.state === k ? (k === "fixed" ? "border-ok bg-ok-soft" : k === "worse" ? "border-bad bg-bad-soft" : "border-warn bg-warn-soft") : ""}`} onClick={() => call(`/api/runs/${run}/resolve`, { id: x.id, state: k })}>{l}</button>))}</div>
          </li>))}</ul>
      </section>}

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="min-w-0">
          <nav className="mb-3 flex gap-1 overflow-x-auto border-b border-rule" role="tablist">
            {tabs.map(([k, l]) => <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)} className={`-mb-px border-b-2 px-3 py-2 text-sm whitespace-nowrap ${tab === k ? "border-accent font-bold text-accent" : "border-transparent text-ink-2"}`}>{l}</button>)}
          </nav>
          {tab === "brief" && <article className="card doc" ref={docRef} onMouseUp={mouseUp} onClick={docClick} dangerouslySetInnerHTML={{ __html: html }} />}
          {tab === "decision" && <article className="card doc" onClick={docClick} dangerouslySetInnerHTML={{ __html: renderMarkdown(d.decision || "판단표가 없습니다.", known) }} />}
          {tab === "send" && <section className="card">
            <p className="mb-3 text-sm text-ink-2">이 사람에게 <b>꼭 보낼</b> 근거와 <b>절대 빼야 할</b> 근거를 정하세요. 골든의 정답이 되고, 개발자 결과를 이 기준으로 채점합니다.</p>
            <ul className="divide-y divide-rule">{d.selection.map((r: any) => (
              <li key={r.evidence_id} className="grid gap-2 py-3 md:grid-cols-[minmax(0,1fr)_auto] md:items-center">
                <div className="text-sm"><b className="mr-2 text-accent">{r.evidence_id}</b>{r.claim || "(근거 표에 없음)"} {r.status && <Chip s={r.status} />}
                  <span className="hint block">AI 선택: {r.send === "yes" ? "보냄" : "뺌"} · {r.why}</span></div>
                <div className="flex gap-1">{GRADE.map(([g, l]) => <button key={g} onClick={() => call(`/api/runs/${run}/grade`, { id: r.evidence_id, grade: g })}
                  className={`btn px-2 py-1 text-xs ${grades[r.evidence_id] === g ? (g === "must" ? "border-ok bg-ok-soft" : g === "never" ? "border-bad bg-bad-soft" : "border-accent bg-accent-soft") : ""}`}>{l}</button>)}</div>
              </li>))}</ul>
          </section>}
          {tab === "diff" && <section className="card">
            <p className="hint mb-3">빨간 줄은 지난 판에서 빠진 문장, 초록 줄은 새로 들어온 문장입니다.</p>
            <pre className="overflow-x-auto text-sm leading-6 whitespace-pre-wrap">{lineDiff(d.parentBrief, d.brief).filter((x) => x.s.trim()).map((x, i) => (
              <div key={i} className={x.t === "add" ? "bg-ok-soft" : x.t === "del" ? "bg-bad-soft text-muted line-through" : ""}>{x.t === "add" ? "+ " : x.t === "del" ? "− " : "  "}{x.s}</div>))}</pre>
          </section>}
          {tab === "approve" && <section className="card space-y-4">
            {d.golden ? <p className="text-sm">이미 골든 v{d.golden.golden_version} 으로 저장했습니다. 승인 이유: {d.golden.approval_reason}</p> : <>
              <h2 className="font-bold">이 판을 골든으로 승인</h2>
              <ol className="space-y-1 text-sm">
                <li className={d.check.issues.length ? "text-bad" : "text-ok"}>{d.check.issues.length ? `✗ 자동 점검에서 객관 오류 ${d.check.issues.length}개가 남았습니다` : "✓ 자동 점검 통과 (숫자 · 근거 번호 · 출처)"}</li>
                <li className={hasMust && hasNever ? "text-ok" : "text-warn"}>{hasMust && hasNever ? "✓ 꼭 보낼 근거 · 절대 뺄 근거를 정했습니다" : <>· <button className="btn-link" onClick={() => setTab("send")}>«누구에게 보내나»</button>에서 꼭 보낼 근거와 절대 뺄 근거를 하나 이상 정하세요</>}</li>
              </ol>
              <label className="label" htmlFor="reason">왜 이 결과를 승인하나요?</label>
              <textarea id="reason" className="field" rows={3} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="예: 대표가 이사회 전에 알아야 할 관세 변수와 빠진 내부 숫자를 정확히 짚었다" />
              <button className="btn-primary" disabled={!reason.trim() || !hasMust || !hasNever || busy}
                onClick={() => call(`/api/runs/${run}/verdict`, { ok: true, reason }, () => call(`/api/runs/${run}/golden`, { reason }))}>골든으로 저장</button>
            </>}
          </section>}
        </div>

        <aside className="space-y-4">
          <section className="card">
            <label className="label" htmlFor="who">검토자</label>
            <input id="who" className="field" value={who} placeholder="이름 또는 이니셜" onChange={(e) => { setWho(e.target.value); reviewer.set(e.target.value); }} />
          </section>
          <section className="card">
            <h2 className="mb-2 font-bold">내 지적 {fb.length}개</h2>
            {!fb.length && <p className="text-sm text-muted">브리핑에서 문장을 끌어 선택하면 지적을 남길 수 있습니다.</p>}
            <ul className="space-y-2">{fb.map((x) => (
              <li key={x.id} className={`relative rounded-xl p-3 text-sm ${x.kind === "good" ? "bg-ok-soft" : "bg-warn-soft"}`}>
                <b>{KIND[x.kind] ?? x.kind}</b>{x.category && <span className="hint"> [{x.category}]</span>}
                {x.quote && <q className="block text-ink-2">{x.quote}</q>}{x.comment}
                {!superseded && <button className="absolute top-2 right-2 text-muted hover:text-bad" aria-label="지우기" onClick={async () => { await api(`/api/runs/${run}/feedback/${x.id}`, undefined, "DELETE"); load(); }}>×</button>}
              </li>))}</ul>
          </section>

          <section className="card">
            <h2 className="mb-1 font-bold">자동 점검 (객관 오류)</h2>
            {d.check.issues.length ? <ul className="space-y-2 text-sm">{d.check.issues.map((x: any, i: number) => <li key={i} className="rounded-xl bg-bad-soft p-2"><b className="text-bad">{x.why}</b><span className="block text-ink-2">{x.sentence}</span></li>)}</ul>
              : <p className="text-sm text-ok">숫자 · 근거 번호 · 출처 문제가 없습니다.</p>}
          </section>

          <section className="card">
            <h2 className="mb-1 font-bold">AI 검토 의견 (차이 검토)</h2>
            {!d.ui.revealed && !fb.length ? <>
              <p className="text-sm text-muted">내 눈으로 먼저 읽고 지적한 뒤에 보면 AI 의견에 끌려가지 않습니다.</p>
              <button className="btn mt-2" onClick={() => call(`/api/runs/${run}/reveal`)}>그래도 지금 보기</button>
            </> : !d.suggestions.length ? <p className="text-sm text-muted">의견이 없습니다.</p> :
              <ul className="space-y-2">{d.suggestions.map((s: any) => (
                <li key={s.id} className="rounded-xl bg-paper p-3 text-sm">
                  <span className={`mr-1 text-xs font-bold ${s.severity === "치명" ? "text-bad" : "text-warn"}`}>{s.severity}</span><b>{KIND[s.kind]}</b>
                  {s.quote && <q className="block text-ink-2">{s.quote}</q>}{s.comment}
                  {s.state ? <p className="hint mt-1">{s.state === "accepted" ? "동의함 → 내 지적에 넣음" : `반대함: ${s.note}`}</p> : <div className="mt-2 space-y-2">
                    <input className="field text-xs" placeholder="반대하면 이유를 적어 주세요" value={notes[s.id] ?? ""} onChange={(e) => setNotes({ ...notes, [s.id]: e.target.value })} />
                    <div className="flex gap-2"><button className="btn px-2 py-1 text-xs" onClick={() => call(`/api/runs/${run}/suggestions/${s.id}`, { accept: true, note: notes[s.id] ?? "" })}>동의</button>
                      <button className="btn px-2 py-1 text-xs" onClick={() => call(`/api/runs/${run}/suggestions/${s.id}`, { accept: false, note: notes[s.id] ?? "" })}>반대</button></div>
                  </div>}
                </li>))}</ul>}
          </section>
        </aside>
      </div>

      {prop && changes.length > 0 && <section className="card space-y-4">
        <h2 className="font-bold">판단 기준 수정안</h2>
        <p className="text-sm text-muted">지적을 다음 브리핑부터 반영되도록 기준 문서를 고치는 안입니다. 승인한 것만 반영되고, 나중에 되돌릴 수 있습니다.{prop.playbook_growth > 600 && <span className="text-warn"> 공통 작업 규칙이 {prop.playbook_growth}자 늘어납니다. 꼭 필요한지 보세요.</span>}</p>
        {changes.map((c) => (
          <div key={c.id} className="rounded-xl border border-rule p-4">
            <div className="flex flex-wrap items-baseline justify-between gap-2"><b>{c.target}</b>{c.decision && <Chip s={c.decision === "approved" ? "승인됨" : "이전 기준"} />}</div>
            <p className="mt-1 text-sm">{c.reason}</p>
            {c.problem && <p className="mt-1 text-sm text-bad">{c.problem}</p>}
            {c.removes && <p className="mt-1 text-sm text-warn">기존 문장을 지웁니다: {c.removed.join(" / ")}</p>}
            <pre className="mt-2 overflow-x-auto rounded-lg bg-paper p-2 text-xs leading-5 whitespace-pre-wrap">{lineDiff(c.before ?? "", c.after ?? "").filter((x) => x.s.trim()).map((x, i) => (
              <div key={i} className={x.t === "add" ? "bg-ok-soft" : x.t === "del" ? "bg-bad-soft line-through" : "text-muted"}>{x.s}</div>))}</pre>
            {!c.decision && <div className="mt-3 flex gap-2"><button className="btn-primary" disabled={!!c.problem} onClick={() => call(`/api/runs/${run}/decide`, { id: c.id, approve: true })}>승인</button>
              <button className="btn" onClick={() => call(`/api/runs/${run}/decide`, { id: c.id, approve: false })}>거절</button></div>}
          </div>))}
        {(prop.needs_data ?? []).length > 0 && <div className="rounded-xl bg-warn-soft p-3 text-sm"><b>기준이 아니라 자료가 필요한 지적</b>
          <ul className="mt-1 list-disc pl-5">{prop.needs_data.map((n: any, i: number) => <li key={i}>{n.what} — {n.why}</li>)}</ul></div>}
        {(prop.warnings ?? []).length > 0 && <ul className="text-sm text-muted">{prop.warnings.map((w: any, i: number) => <li key={i}>· {w.message}</li>)}</ul>}
      </section>}

      {d.applied && <section className="card flex flex-wrap items-center justify-between gap-3 text-sm">
        <span>이 판은 지난 판의 지적으로 {d.applied.files?.length ?? 0}개 기준 문서를 고쳐 만들었습니다.{d.applied.reverted && " (되돌림)"}</span>
        {!d.applied.reverted && <button className="btn" onClick={() => call(`/api/runs/${run}/revert`)}>기준 수정 되돌리기</button>}
      </section>}

      {sel && <div className="fixed z-50 w-80 rounded-2xl border border-rule bg-white p-3 shadow-xl" style={{ left: Math.max(8, sel.x), top: Math.min(sel.y, window.innerHeight - 260) }} role="dialog" aria-label="지적 남기기">
        <q className="line-clamp-2 block text-sm text-ink-2">{sel.quote}</q>
        <div className="my-2 flex flex-wrap gap-1"><span className="hint mr-1">분류</span>{CATS.map((c) => <button key={c} onClick={() => setCat(cat === c ? null : c)} className={`btn px-2 py-0.5 text-xs ${cat === c ? "border-accent bg-accent-soft" : ""}`}>{c}</button>)}</div>
        <textarea autoFocus className="field text-sm" rows={2} placeholder="무엇이 문제이고, 왜 그렇게 보나요?" value={comment} onChange={(e) => setComment(e.target.value)} />
        <div className="mt-2 flex flex-wrap gap-1">{Object.entries(KIND).map(([k, l]) => <button key={k} className={`btn px-2 py-1 text-xs ${k === "good" ? "" : "border-warn"}`} onClick={() => addFb(k)}>{l}</button>)}
          <button className="btn-link ml-auto text-xs" onClick={() => setSel(null)}>닫기</button></div>
      </div>}
      {ev && <div className="fixed right-4 bottom-4 z-50 w-96 max-w-[calc(100vw-2rem)] rounded-2xl border border-rule bg-white p-4 shadow-xl" role="dialog" aria-label="근거">
        <div className="flex items-baseline justify-between"><b className="text-accent">{ev.evidence_id}</b><button className="text-muted" aria-label="닫기" onClick={() => setEv(null)}>×</button></div>
        <p className="mt-1 text-sm">{ev.claim}</p>
        {ev.quote && <blockquote className="mt-2 border-l-2 border-rule pl-2 text-sm text-ink-2">{ev.quote}</blockquote>}
        <p className="hint mt-2">{[ev.publisher, ev.published_at, ev.status && ({ confirmed: "확정", proposed: "검토 중", uncertain: "불확실" } as any)[ev.status], ev.synthetic === "false" && "우리 회사 숫자"].filter(Boolean).join(" · ")}</p>
        {ev.limitations && <p className="mt-1 text-xs text-warn">한계: {ev.limitations}</p>}
        {ev.source_url && <a className="btn-link mt-2 block truncate text-sm" href={ev.source_url} target="_blank" rel="noreferrer">{ev.source_url}</a>}
      </div>}
    </div>
  );
}
