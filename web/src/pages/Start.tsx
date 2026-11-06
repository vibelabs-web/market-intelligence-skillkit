import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { ErrorBox, ago } from "../components/ui";

export default function Start() {
  const [data, setData] = useState<any>(null), [error, setError] = useState<string | null>(null);
  useEffect(() => { api("/api/projects").then(setData).catch((e) => setError(e.message)); }, []);
  const projects: any[] = data?.projects ?? [];
  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-2xl font-extrabold">결정할 질문부터 정하세요</h1>
        <p className="mt-1 text-muted">질문을 정하면 그 방향으로 새로 리서치합니다. 조사한 자료는 지식 DB 에 쌓여 다음 프로젝트에서도 쓰입니다.</p>
      </header>
      <ErrorBox error={error} />
      <section className="card flex flex-col items-start gap-4 md:flex-row md:items-center md:justify-between">
        <ol className="grid gap-2 text-sm md:grid-cols-4 md:gap-6">
          {["결정 질문 · 받는 사람 정하기", "그 방향으로 새로 리서치", "받는 사람마다 브리핑", "피드백으로 판단 기준 다듬기"].map((s, i) => (
            <li key={s} className="flex items-center gap-2"><span className="grid size-6 shrink-0 place-items-center rounded-full bg-accent-soft text-xs font-bold text-accent">{i + 1}</span>{s}</li>))}
        </ol>
        <Link to="/projects/new" className="btn-primary shrink-0">새 프로젝트 시작</Link>
      </section>
      <section>
        <h2 className="mb-3 font-bold">지난 프로젝트</h2>
        {data && !projects.length && <p className="card text-sm text-muted">아직 프로젝트가 없습니다. 첫 프로젝트를 시작하면 여기에 쌓입니다.</p>}
        <ul className="grid gap-3 md:grid-cols-2">
          {projects.map((p) => (
            <li key={p.id}><Link to={`/projects/${p.id}`} className="card block hover:border-accent">
              <b className="block">{p.title}</b>
              <span className="mt-1 block text-sm text-ink-2">{p.question}</span>
              <span className="hint mt-2 block">자료 {p.claims}건 · 브리핑 {p.briefs}개 · {p.researched_at ? `리서치 ${ago(p.researched_at)}` : "리서치 전"}</span>
            </Link></li>))}
        </ul>
      </section>
    </div>
  );
}
