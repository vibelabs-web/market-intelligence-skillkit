import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { Chip, ErrorBox, when } from "../components/ui";

const STATUS: Record<string, string> = { active: "활성", superseded: "이전 기준", retired: "폐기" };

export default function Goldens() {
  const [g, setG] = useState<any[] | null>(null), [error, setError] = useState<string | null>(null);
  const load = () => api("/api/goldens").then((d) => setG(d.goldens)).catch((e) => setError(e.message));
  useEffect(() => { load(); }, []);
  const status = async (dir: string, s: string) => { try { await api(`/api/goldens/${dir}/status`, { status: s }); load(); } catch (e: any) { setError(e.message); } };
  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-xl font-extrabold">골든 라이브러리</h1>
        <p className="mt-1 text-sm text-muted">컨설턴트가 승인한 브리핑입니다. 개발자는 같은 자료로 이 결과를 재현하고, «꼭 보낼 · 절대 뺄» 근거로 채점받습니다.</p>
      </header>
      <ErrorBox error={error} />
      {g && !g.length && <p className="card text-sm text-muted">아직 골든이 없습니다. 브리핑 검토의 «승인» 탭에서 만듭니다.</p>}
      <ul className="grid gap-3 md:grid-cols-2">{g?.map((x) => (
        <li key={x.dir} className={`card space-y-2 text-sm ${x.status !== "active" ? "opacity-70" : ""}`}>
          <div className="flex flex-wrap items-center gap-2"><b>{x.persona_label || x.scope?.persona} · v{x.golden_version}</b><Chip s={STATUS[x.status] ?? x.status} /></div>
          <p className="text-ink-2">{x.approval_reason}</p>
          <p className="hint">{x.approved_by || "컨설턴트"} · {when(x.approved_at)} · {x.dir}</p>
          <div className="flex flex-wrap gap-2"><Link className="btn" to={`/briefs/${x.run}`}>브리핑 보기</Link>
            {x.status === "active" ? <button className="btn" onClick={() => status(x.dir, "retired")}>폐기</button> : <button className="btn" onClick={() => status(x.dir, "active")}>다시 활성</button>}</div>
        </li>))}</ul>
    </div>
  );
}
