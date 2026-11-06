import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { ErrorBox } from "../components/ui";

export default function Criteria() {
  const [d, setD] = useState<any>(null), [edit, setEdit] = useState<string | null>(null), [error, setError] = useState<string | null>(null);
  const load = () => api("/api/criteria").then(setD).catch((e) => setError(e.message));
  useEffect(() => { load(); }, []);
  const save = async () => { try { setD(await api("/api/criteria", { text: edit }, "PUT")); setEdit(null); } catch (e: any) { setError(e.message); } };
  if (!d) return <><ErrorBox error={error} /><p className="text-muted">불러오는 중…</p></>;
  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-xl font-extrabold">내 판단 기준 <span className="text-accent">v{d.version}</span></h1>
        <p className="mt-1 text-sm text-muted">모든 브리핑이 이 순서로 판단합니다. 브리핑에 남긴 지적을 승인하면 여기가 바뀌고, 바뀐 기록이 아래에 남습니다.</p>
      </header>
      <ErrorBox error={error} />
      <section className="card">
        <h2 className="mb-2 font-bold">판단 순서</h2>
        <ol className="list-decimal space-y-1 pl-5 text-sm">{d.order.map((o: string) => <li key={o}>{o}</li>)}</ol>
        {edit === null ? <button className="btn mt-4" onClick={() => setEdit(d.lens)}>직접 고치기</button> : <div className="mt-4 space-y-2">
          <textarea className="field font-mono text-sm" rows={18} value={edit} onChange={(e) => setEdit(e.target.value)} aria-label="내 판단 기준" />
          <div className="flex gap-2"><button className="btn-primary" onClick={save}>저장 (기록에 남음)</button><button className="btn" onClick={() => setEdit(null)}>취소</button></div></div>}
      </section>
      <section className="card">
        <h2 className="mb-3 font-bold">바뀐 기록</h2>
        {!d.history.length && <p className="text-sm text-muted">아직 바뀐 적이 없습니다. 브리핑 검토에서 지적 → 수정안 승인을 하면 쌓입니다.</p>}
        <ol className="space-y-3">{d.history.slice().reverse().map((h: any, i: number) => (
          <li key={i} className={`rounded-xl border border-rule p-3 text-sm ${h.reverted ? "opacity-60" : ""}`}>
            <div className="flex flex-wrap items-baseline justify-between gap-2"><b>{h.reverted ? "되돌림" : `v${h.version}`} · {h.changes.map((c: any) => c.target).join(", ")}</b>
              <span className="hint">{String(h.at).slice(0, 16).replace("T", " ")} · {h.approver}</span></div>
            <ul className="mt-1 text-ink-2">{h.changes.map((c: any, j: number) => <li key={j}>· {c.reason}</li>)}</ul>
            {h.feedback.length > 0 && <p className="hint mt-1">계기가 된 지적: {h.feedback.join(" / ")}</p>}
            {h.new_run && <p className="mt-1"><Link className="btn-link" to={`/briefs/${h.from_run}`}>{h.from_label}</Link> → <Link className="btn-link" to={`/briefs/${h.new_run}`}>{h.new_label}</Link></p>}
          </li>))}</ol>
      </section>
    </div>
  );
}
