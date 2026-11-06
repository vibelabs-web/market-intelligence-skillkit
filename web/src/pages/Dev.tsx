import { useEffect, useState } from "react";
import { api } from "../lib/api";

export default function Dev() {
  const [r, setR] = useState<any[] | null>(null);
  useEffect(() => { api("/api/dev/results").then(setR).catch(() => setR([])); }, []);
  const rows = (r ?? []).slice().sort((a, b) => (b.score ?? 0) - (a.score ?? 0));
  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-xl font-extrabold">개발자 평가</h1>
        <p className="mt-1 text-sm text-muted">개발자가 자기 코드(에이전트 · LLM API)로 골든을 재현한 결과입니다. <code>dev/results/*.json</code> 에 결과를 넣으면 여기에 순위로 보입니다. 채점 방법은 <code>dev/README.md</code> 를 보세요.</p>
      </header>
      {r && !rows.length && <p className="card text-sm text-muted">아직 제출된 결과가 없습니다.</p>}
      {rows.length > 0 && <section className="card overflow-x-auto"><table className="w-full text-sm">
        <thead><tr className="text-left text-muted"><th className="py-2 pr-3">순위</th><th className="pr-3">팀</th><th className="pr-3">골든</th><th className="pr-3">일치도</th><th>객관 오류</th></tr></thead>
        <tbody>{rows.map((x, i) => <tr key={i} className="border-t border-rule"><td className="py-2 pr-3">{i + 1}</td><td className="pr-3">{x.team ?? x.name}</td><td className="pr-3">{x.golden}</td>
          <td className="pr-3 font-bold">{x.score ?? "-"}</td><td>{x.errors ?? "-"}</td></tr>)}</tbody></table></section>}
    </div>
  );
}
