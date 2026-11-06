import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, followJob, type Job } from "../lib/api";
import { Chip, ErrorBox, JobProgress, Steps, field, ago } from "../components/ui";

export const STEP_NAMES: [string, string][] = [["brief", "브리핑"], ["feedback", "문제 지적"], ["improve", "기준 수정"], ["rerun", "다시 만들기"], ["golden", "골든 저장"]];

export default function Project() {
  const { id } = useParams(), nav = useNavigate();
  const [d, setD] = useState<any>(null), [error, setError] = useState<string | null>(null), [job, setJob] = useState<Job | null>(null);
  const [pick, setPick] = useState<string>(""), [edit, setEdit] = useState<string | null>(null);
  const load = () => api(`/api/projects/${id}`).then((x) => { setD(x); setPick((p) => p || x.people[0]?.id || ""); if (x.job?.state === "running") setJob(x.job); }).catch((e) => setError(e.message));
  useEffect(() => { load(); }, [id]);
  useEffect(() => { if (job?.state !== "running") return; return followJob(job.id, (j) => { setJob(j); if (j.state === "done" && j.kind === "brief" && j.result?.run) nav(`/briefs/${j.result.run}`); else if (j.state !== "running") load(); }); }, [job?.id]);
  if (!d) return <><ErrorBox error={error} /><p className="text-muted">불러오는 중…</p></>;
  const p = d.project, person = d.people.find((x: any) => x.id === pick), mine = d.runs.filter((r: any) => r.person === pick);
  const busy = job?.state === "running";
  const make = async () => { setError(null); try { const r = await api(`/api/projects/${id}/briefs`, { person: pick }); setJob(r.job); } catch (e: any) { setError(e.message); } };
  const save = async () => { try { await api(`/api/projects/${id}/people/${pick}`, { text: edit }, "PUT"); setEdit(null); load(); } catch (e: any) { setError(e.message); } };
  const researched = d.research.length > 0;
  const latest = mine[0];
  const gaps = ((d.notes as string).split("## 찾지 못한 것")[1] ?? "").split("\n## ")[0].split("\n").map((l) => l.replace(/^-\s*/, "").trim()).filter((l) => l && l !== "없음");
  return (
    <div className="space-y-6">
      <header>
        <p className="hint">프로젝트 · {ago(p.created_at)} 시작</p>
        <h1 className="text-xl font-extrabold">{p.question}</h1>
        {p.context && <p className="mt-1 text-sm text-ink-2">{p.context}</p>}
      </header>
      <ErrorBox error={error} />
      {job && (busy || job.state === "failed") && <JobProgress job={job} showLog={job.kind === "research"} />}

      <section className="card">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="font-bold">리서치</h2>
          <div className="flex gap-3 text-sm"><Link className="btn-link" to={`/library?project=${id}`}>조사한 자료 {d.claims}건 보기</Link><Link className="btn-link" to={`/projects/${id}/research`}>리서치 기록</Link></div>
        </div>
        {researched ? <p className="mt-1 text-sm text-ink-2">자료 {d.claims}건 (다른 프로젝트에서 다시 쓴 자료 {d.reused}건) · 리서치 {d.research.length}회 · 마지막 {ago(d.research[0].finished_at)}</p>
          : <p className="mt-1 text-sm text-warn">아직 리서치가 끝나지 않았습니다. <Link className="btn-link" to={`/projects/${id}/research`}>진행 보기</Link></p>}
      </section>

      {researched && <section className="card space-y-4">
        <h2 className="font-bold">누구에게 보낼 브리핑인가요?</h2>
        <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="받는 사람">
          {d.people.map((x: any) => (
            <button key={x.id} role="radio" aria-checked={pick === x.id} onClick={() => { setPick(x.id); setEdit(null); }}
              className={`rounded-xl border px-3 py-2 text-left text-sm ${pick === x.id ? "border-accent bg-accent-soft" : "border-rule bg-white hover:border-accent"}`}>
              <b className="block">{x.title}</b><span className="hint">{field(x.text, "결정할 일").slice(0, 40) || "결정할 일 미확인"}</span>
            </button>))}
        </div>
        {person && <div className="rounded-xl bg-paper p-4">
          {edit === null ? <>
            <dl className="grid gap-x-6 gap-y-2 text-sm md:grid-cols-2">
              {["결정할 일", "결정 시점", "권한", "놀라고 싶지 않은 것", "더 알아야 할 주체", "안 받아도 되는 것", "형식"].map((k) => (
                <div key={k}><dt className="hint">{k}</dt><dd className={/^미확인/.test(field(person.text, k)) || !field(person.text, k) ? "text-warn" : ""}>{field(person.text, k) || "미확인"}</dd></div>))}
            </dl>
            <p className="hint mt-3">«미확인»은 리서치로 알 수 없는 것입니다. 아는 내용이면 고쳐 주세요. 브리핑이 이 설정을 따릅니다.</p>
            <button className="btn mt-2" disabled={busy} onClick={() => setEdit(person.text)}>받는 사람 설정 고치기</button>
          </> : <>
            <textarea className="field font-mono text-sm" rows={14} value={edit} onChange={(e) => setEdit(e.target.value)} aria-label="받는 사람 설정" />
            <div className="mt-2 flex gap-2"><button className="btn-primary" onClick={save}>저장</button><button className="btn" onClick={() => setEdit(null)}>취소</button></div>
          </>}
        </div>}
        {person && <div className="flex flex-wrap items-center gap-3 border-t border-rule pt-4">
          {latest ? <>
            <Link to={`/briefs/${latest.run}`} className="btn-primary">{latest.label} 이어서 검토</Link>
            <button className="btn" disabled={busy} onClick={make}>새 브리핑 만들기</button>
          </> : <button className="btn-primary" disabled={busy} onClick={make}>{person.title}에게 보낼 브리핑 만들기</button>}
          <span className="hint">2~4분 걸립니다. 다 되면 검토 화면으로 넘어갑니다.</span>
        </div>}
      </section>}

      {d.runs.length > 0 && <section className="card">
        <h2 className="mb-3 font-bold">만든 브리핑</h2>
        <ul className="divide-y divide-rule">
          {d.runs.map((r: any) => (
            <li key={r.run} className="grid gap-3 py-3 md:grid-cols-[minmax(0,1fr)_22rem] md:items-center">
              <div><Link to={`/briefs/${r.run}`} className="font-bold hover:text-accent">{r.label}</Link> <Chip s={r.status} /></div>
              <Steps steps={r.steps} names={STEP_NAMES} />
            </li>))}
        </ul>
      </section>}

      <div className="grid gap-6 md:grid-cols-2">
        <section className="card">
          <h2 className="mb-2 font-bold">우리 회사 숫자</h2>
          {d.internal.length ? <ul className="space-y-1 text-sm">{d.internal.map((r: any) => <li key={r.evidence_id}><span className="hint mr-2">{r.evidence_id}</span>{r.claim}</li>)}</ul>
            : <p className="text-sm text-muted">적은 숫자가 없습니다. 브리핑은 «이 값이 있어야 결정할 수 있다»고 알려 줍니다.</p>}
        </section>
        <section className="card">
          <h2 className="mb-2 font-bold">리서치에서 찾지 못한 것</h2>
          {gaps.length ? <ul className="list-disc space-y-1 pl-5 text-sm text-ink-2">{gaps.map((g: string) => <li key={g}>{g}</li>)}</ul> : <p className="text-sm text-muted">없습니다.</p>}
        </section>
      </div>
    </div>
  );
}
