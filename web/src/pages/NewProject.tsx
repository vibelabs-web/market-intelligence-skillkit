import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { ErrorBox } from "../components/ui";

const STEPS = [
  { key: "question", title: "어떤 결정을 돕는 브리핑인가요?", hint: "한 문장으로. 보류도 선택지가 될 수 있게 쓰면 좋습니다.", ph: "예: 국내 산업용 전동기 제조사는 베트남과 태국 중 어디부터 수출을 늘려야 하는가", required: true, rows: 2,
    extra: { key: "context", label: "고객 상황 (선택)", ph: "예: 국내 중견 제조사, 내년 3월 이사회에서 결정. 동남아 매출은 아직 적다." } },
  { key: "people", title: "브리핑을 받을 사람은 누구인가요?", hint: "역할만 적습니다. 이름은 쓰지 않습니다. 결정 시점 · 권한을 알면 함께 적어 주세요.", ph: "예: 대표(12월 이사회, 50억까지 승인) · 구매 책임자 · 해외영업 책임자", required: true, rows: 3 },
  { key: "scope", title: "무엇을 비교 · 조사할까요?", hint: "리서치가 이 범위를 고루 봅니다. 비워 두면 질문에서 정합니다.", ph: "예: 두 나라의 수요 · 효율 규제와 인증 · 관세 · 경쟁사 · 원자재", rows: 3 },
  { key: "numbers", title: "우리 회사 숫자가 있나요? (선택)", hint: "한 줄에 하나. 적은 숫자만 판단에 씁니다. AI 는 회사 숫자를 지어내지 않습니다. 없으면 브리핑이 «이 값이 있어야 결정할 수 있다»고 알려 줍니다.", ph: "예:\n연매출 600억 원\n최근 12개월 베트남 문의 40건, 수주 2건\n구리 연간 구매량 400톤", rows: 5 },
] as const;

export default function NewProject() {
  const nav = useNavigate();
  const [i, setI] = useState(0), [busy, setBusy] = useState(false), [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState<Record<string, string>>({ question: "", context: "", people: "", scope: "", numbers: "" });
  const s = STEPS[i], last = i === STEPS.length - 1;
  const canNext = !("required" in s && s.required) || form[s.key].trim().length >= (s.key === "question" ? 6 : 2);
  const submit = async () => {
    setBusy(true); setError(null);
    try { const r = await api("/api/projects", form); nav(`/projects/${r.project.id}/research?job=${r.job.id}`); }
    catch (e: any) { setError(e.message); setBusy(false); }
  };
  return (
    <div className="mx-auto max-w-2xl">
      <ol className="mb-6 flex gap-2" aria-label="단계">
        {STEPS.map((x, n) => <li key={x.key} className={`h-1.5 flex-1 rounded-full ${n <= i ? "bg-accent" : "bg-rule"}`} />)}
      </ol>
      <p className="hint mb-1">새 프로젝트 · {i + 1}/{STEPS.length}</p>
      <h1 className="text-xl font-extrabold">{s.title}</h1>
      <p className="mt-1 mb-4 text-sm text-muted">{s.hint}</p>
      <ErrorBox error={error} />
      <form onSubmit={(e) => { e.preventDefault(); if (!canNext) return; last ? submit() : setI(i + 1); }} className="card space-y-4">
        <textarea autoFocus className="field" rows={s.rows} placeholder={s.ph} value={form[s.key]} onChange={(e) => setForm({ ...form, [s.key]: e.target.value })} aria-label={s.title} />
        {"extra" in s && s.extra && <div><label className="label" htmlFor="extra">{s.extra.label}</label>
          <textarea id="extra" className="field" rows={2} placeholder={s.extra.ph} value={form[s.extra.key]} onChange={(e) => setForm({ ...form, [s.extra!.key]: e.target.value })} /></div>}
        <div className="flex items-center justify-between gap-3">
          <button type="button" className="btn" disabled={i === 0 || busy} onClick={() => setI(i - 1)}>이전</button>
          <div className="flex items-center gap-3">
            {last && <span className="hint hidden md:inline">리서치는 10~30분 걸립니다</span>}
            <button className="btn-primary" disabled={!canNext || busy}>{last ? (busy ? "시작하는 중…" : "리서치 시작") : "다음"}</button>
          </div>
        </div>
      </form>
    </div>
  );
}
