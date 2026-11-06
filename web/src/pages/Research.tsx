import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { api, followJob, type Job } from "../lib/api";
import { ErrorBox, JobProgress } from "../components/ui";

export default function Research() {
  const { id } = useParams(), [q] = useSearchParams();
  const [p, setP] = useState<any>(null), [job, setJob] = useState<Job | null>(null), [error, setError] = useState<string | null>(null);
  const load = () => api(`/api/projects/${id}`).then((d) => { setP(d); if (!q.get("job") && d.job) setJob(d.job); }).catch((e) => setError(e.message));
  useEffect(() => { load(); }, [id]);
  useEffect(() => { const jid = q.get("job") ?? p?.job?.id; if (!jid) return; return followJob(jid, (j) => { setJob(j); if (j.state !== "running") load(); }); }, [q.get("job"), p?.job?.id]);
  const again = async () => { try { const r = await api(`/api/projects/${id}/research`, {}); setJob(r.job); followJob(r.job.id, (j) => { setJob(j); if (j.state !== "running") load(); }); } catch (e: any) { setError(e.message); } };
  const r = job?.result;
  return (
    <div className="space-y-6">
      <header>
        <p className="hint">리서치</p>
        <h1 className="text-xl font-extrabold">{p?.project.question ?? "…"}</h1>
        <p className="mt-1 text-sm text-muted">지식 DB 에서 이미 아는 자료를 먼저 찾고, 빈 곳만 웹에서 새로 조사합니다. 찾는 검색어와 연 페이지가 아래에 그대로 보입니다.</p>
      </header>
      <ErrorBox error={error} />
      {job && <JobProgress job={job} />}
      {job?.state === "done" && job.kind === "research" && r && (
        <section className="card">
          <h2 className="mb-3 font-bold">리서치 결과</h2>
          <dl className="grid grid-cols-2 gap-3 md:grid-cols-4">
            {[["새로 찾은 자료", r.new], ["다시 쓴 자료", r.reused], ["개념", r.concepts], ["찾지 못한 것", r.gaps]].map(([k, v]) => (
              <div key={k as string} className="rounded-xl bg-paper p-3"><dt className="hint">{k}</dt><dd className="text-2xl font-extrabold">{v}</dd></div>))}
          </dl>
          <div className="mt-4 flex flex-wrap gap-3">
            <Link to={`/projects/${id}`} className="btn-primary">받는 사람 고르고 브리핑 만들기</Link>
            <Link to={`/library?project=${id}`} className="btn">조사한 자료 보기</Link>
          </div>
        </section>)}
      {!job && p && <section className="card space-y-3">
        <p className="text-sm">이 프로젝트의 리서치 기록 {p.research.length}회 · 자료 {p.claims}건 (다시 쓴 자료 {p.reused}건)</p>
        <div className="flex flex-wrap gap-3"><Link to={`/projects/${id}`} className="btn-primary">프로젝트로</Link><button className="btn" onClick={again}>같은 방향으로 다시 리서치</button></div>
      </section>}
    </div>
  );
}
