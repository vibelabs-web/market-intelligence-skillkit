import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../lib/api";
import { Chip, ErrorBox, ago } from "../components/ui";

const TABS: [string, string][] = [["concepts", "개념"], ["claims", "자료"], ["sources", "출처"], ["runs", "리서치 기록"], ["sql", "SQL"]];
const DOMAIN: Record<string, string> = { demand: "수요", regulation: "규제", competitor: "경쟁", supply: "공급", macro: "거시", other: "기타" };
const list = (s: string) => { try { return JSON.parse(s ?? "[]") as string[]; } catch { return []; } };

export default function Library() {
  const [q, setQ] = useSearchParams();
  const tab = q.get("tab") ?? "concepts", project = q.get("project") ?? "", cid = q.get("concept");
  const [stats, setStats] = useState<any>(null), [projects, setProjects] = useState<any[]>([]), [rows, setRows] = useState<any[] | null>(null);
  const [concept, setConcept] = useState<any>(null), [text, setText] = useState(q.get("q") ?? ""), [error, setError] = useState<string | null>(null);
  const [sql, setSql] = useState("SELECT domain, status, COUNT(*) AS n FROM claims GROUP BY domain, status ORDER BY n DESC"), [res, setRes] = useState<any>(null);
  const set = (k: string, v: string | null) => { const n = new URLSearchParams(q); v ? n.set(k, v) : n.delete(k); if (k !== "concept") n.delete("concept"); setQ(n); };
  useEffect(() => { api("/api/library/stats").then(setStats); api("/api/library/projects").then(setProjects); }, []);
  useEffect(() => {
    setRows(null); setError(null);
    const s = encodeURIComponent(q.get("q") ?? "");
    const url = tab === "concepts" ? `/api/library/concepts?q=${s}` : tab === "claims" ? `/api/library/claims?q=${s}&project=${project}` : tab === "sources" ? "/api/library/sources" : tab === "runs" ? `/api/library/runs?project=${project}` : null;
    if (url) api(url).then(setRows).catch((e) => setError(e.message));
  }, [tab, project, q.get("q")]);
  useEffect(() => { setConcept(null); if (cid) api(`/api/library/concepts/${cid}`).then(setConcept).catch((e) => setError(e.message)); }, [cid]);
  const pname = (id: string) => projects.find((p) => p.id === id)?.title ?? id;
  const runSql = async () => { setError(null); try { setRes(await api("/api/library/query", { sql })); } catch (e: any) { setError(e.message); setRes(null); } };

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-xl font-extrabold">지식 DB</h1>
        <p className="mt-1 text-sm text-muted">모든 프로젝트에서 리서치한 자료가 쌓이는 곳입니다. 자료는 개념별로 정리되고, 다음 리서치는 여기서 먼저 찾은 뒤 빈 곳만 새로 조사합니다.</p>
        {stats && <p className="hint mt-2">프로젝트 {stats.projects} · 개념 {stats.concepts} · 자료 {stats.claims} · 출처 {stats.sources} · 리서치 {stats.runs}회</p>}
      </header>
      <div className="flex flex-wrap items-center gap-3">
        <nav className="flex gap-1 overflow-x-auto" role="tablist">{TABS.map(([k, l]) => (
          <button key={k} role="tab" aria-selected={tab === k} onClick={() => set("tab", k)} className={`rounded-xl px-3 py-1.5 text-sm ${tab === k ? "bg-accent text-white" : "bg-white text-ink-2 hover:bg-paper"}`}>{l}</button>))}</nav>
        {(tab === "claims" || tab === "runs") && <select className="field w-auto max-w-72 py-1.5 text-sm" value={project} onChange={(e) => set("project", e.target.value || null)} aria-label="프로젝트">
          <option value="">전체 프로젝트</option>{projects.map((p) => <option key={p.id} value={p.id}>{p.title}</option>)}</select>}
        {(tab === "concepts" || tab === "claims") && <form className="flex flex-1 gap-2" onSubmit={(e) => { e.preventDefault(); set("q", text.trim() || null); }}>
          <input className="field py-1.5 text-sm" placeholder="검색어 (예: 관세, 효율 규제)" value={text} onChange={(e) => setText(e.target.value)} aria-label="검색" /><button className="btn">찾기</button></form>}
      </div>
      <ErrorBox error={error} />

      {tab === "concepts" && <div className="grid grid-cols-1 gap-5 lg:grid-cols-[18rem_minmax(0,1fr)]">
        <ul className="space-y-1">{rows?.map((c) => (
          <li key={c.id}><button onClick={() => set("concept", c.id)} className={`w-full rounded-xl px-3 py-2 text-left text-sm ${cid === c.id ? "bg-accent-soft font-bold text-accent" : "bg-white hover:bg-paper"}`}>
            {c.name}<span className="hint block">자료 {c.claims}건 · {ago(c.updated_at)} 갱신</span></button></li>))}
          {rows && !rows.length && <li className="text-sm text-muted">개념이 없습니다. 리서치를 하면 생깁니다.</li>}</ul>
        <div>{concept ? <article className="card space-y-4">
          <div><p className="hint">{concept.id}</p><h2 className="text-lg font-bold">{concept.name}</h2>
            <p className="mt-2 text-sm leading-6 whitespace-pre-wrap">{concept.summary}</p>
            {concept.projects.length > 0 && <p className="hint mt-2">쓴 프로젝트: {concept.projects.map((p: any, i: number) => <span key={p.id}>{i > 0 && " · "}<Link className="btn-link" to={`/projects/${p.id}`}>{p.title}</Link></span>)}</p>}</div>
          <ul className="divide-y divide-rule">{concept.claimRows.map((c: any) => <ClaimRow key={c.id} c={c} />)}</ul>
        </article> : <p className="card text-sm text-muted">왼쪽에서 개념을 고르면 요약과 그 개념에 묶인 자료가 보입니다.</p>}</div>
      </div>}

      {tab === "claims" && <section className="card"><p className="hint mb-2">{rows?.length ?? "…"}건{project && ` · ${pname(project)}`}</p>
        <ul className="divide-y divide-rule">{rows?.map((c) => <ClaimRow key={c.id} c={c} pname={pname} />)}</ul></section>}

      {tab === "sources" && <section className="card overflow-x-auto"><table className="w-full text-sm">
        <thead><tr className="text-left text-muted"><th className="py-2 pr-3">출처</th><th className="pr-3">발행처</th><th className="pr-3">발행일</th><th className="pr-3">자료</th><th>마지막 확인</th></tr></thead>
        <tbody>{rows?.map((s) => <tr key={s.id} className="border-t border-rule"><td className="py-2 pr-3"><a className="btn-link" href={s.url} target="_blank" rel="noreferrer">{s.title || s.url}</a></td>
          <td className="pr-3">{s.publisher}</td><td className="pr-3 whitespace-nowrap">{s.published_at}</td><td className="pr-3">{s.claims}</td><td className="whitespace-nowrap">{ago(s.last_checked)}</td></tr>)}</tbody></table></section>}

      {tab === "runs" && <ul className="space-y-3">{rows?.map((r) => (
        <li key={r.id} className="card text-sm">
          <div className="flex flex-wrap items-baseline justify-between gap-2"><Link className="font-bold hover:text-accent" to={`/projects/${r.project_id}`}>{pname(r.project_id)}</Link><span className="hint">{ago(r.finished_at)} · ${Number(r.cost_usd).toFixed(2)}</span></div>
          <p className="mt-1">새 자료 {r.new_claims} · 다시 쓴 자료 {r.reused_claims} · 개념 {r.concepts}</p>
          <details className="mt-2"><summary className="cursor-pointer text-muted">검색어 {list(r.searches).length} · 연 페이지 {list(r.opened).length} · 찾지 못한 것 {list(r.gaps).length}</summary>
            <div className="mt-2 grid gap-3 md:grid-cols-3">{[["검색어", r.searches], ["연 페이지", r.opened], ["찾지 못한 것", r.gaps]].map(([k, v]) => (
              <div key={k}><b className="hint">{k}</b><ul className="mt-1 space-y-0.5">{list(v).map((x, i) => <li key={i} className="truncate" title={x}>{x}</li>)}</ul></div>))}</div></details>
        </li>))}{rows && !rows.length && <li className="card text-sm text-muted">리서치 기록이 없습니다.</li>}</ul>}

      {tab === "sql" && <section className="card space-y-3">
        <p className="text-sm text-muted">읽기 전용입니다. SELECT 문 하나만 실행됩니다. 표: projects · sources · claims · concepts · claim_concepts · conflicts · project_claims · research_runs</p>
        <textarea className="field font-mono text-sm" rows={4} value={sql} onChange={(e) => setSql(e.target.value)} aria-label="SQL" />
        <button className="btn-primary" onClick={runSql}>실행</button>
        {res && <div className="overflow-x-auto"><p className="hint mb-1">{res.rows.length}행{res.truncated && " (앞부분만)"}</p><table className="w-full text-sm">
          <thead><tr>{res.columns.map((c: string) => <th key={c} className="py-1 pr-3 text-left text-muted">{c}</th>)}</tr></thead>
          <tbody>{res.rows.map((r: any, i: number) => <tr key={i} className="border-t border-rule">{r.map((v: any, j: number) => <td key={j} className="max-w-md truncate py-1 pr-3" title={String(v ?? "")}>{String(v ?? "")}</td>)}</tr>)}</tbody></table></div>}
      </section>}
    </div>
  );
}

function ClaimRow({ c, pname }: { c: any; pname?: (id: string) => string }) {
  return (
    <li className="py-3 text-sm">
      <div className="flex flex-wrap items-baseline gap-2"><span className="hint">{c.id}</span><b>{c.claim}</b><Chip s={c.status} /><span className="hint">{DOMAIN[c.domain] ?? c.domain} · {c.region} · {c.data_period}</span></div>
      {c.quote && <blockquote className="mt-1 border-l-2 border-rule pl-2 text-ink-2">{c.quote}</blockquote>}
      <p className="hint mt-1">{c.url && <a className="btn-link" href={c.url} target="_blank" rel="noreferrer">{c.source_title || c.publisher || c.url}</a>}{c.limitations && ` · 한계: ${c.limitations}`}
        {pname && c.project_ids && <> · 프로젝트: {String(c.project_ids).split(",").map((p: string, i: number) => <span key={p}>{i > 0 && ", "}<Link className="btn-link" to={`/projects/${p}`}>{pname(p)}</Link></span>)}</>}</p>
    </li>
  );
}
