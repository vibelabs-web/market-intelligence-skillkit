import { useEffect, useState } from "react";
import type { Job } from "../lib/api";

const CHIP: Record<string, string> = { "검토 필요": "bg-warn-soft text-warn", "기준 개선 중": "bg-accent-soft text-accent", "생성 중": "bg-accent-soft text-accent",
  승인됨: "bg-ok-soft text-ok", "이전 기준": "bg-paper text-muted", "분석 전": "bg-paper text-ink-2", 활성: "bg-ok-soft text-ok", 폐기: "bg-paper text-muted",
  confirmed: "bg-ok-soft text-ok", proposed: "bg-warn-soft text-warn", uncertain: "bg-bad-soft text-bad" };
const LABEL: Record<string, string> = { confirmed: "확정", proposed: "검토 중", uncertain: "불확실" };
export function Chip({ s }: { s: string }) {
  return <span className={`inline-block whitespace-nowrap rounded-full px-2 py-0.5 text-xs ${CHIP[s] ?? "bg-paper text-ink-2"}`}>{LABEL[s] ?? s}</span>;
}
export function ErrorBox({ error }: { error: string | null }) {
  return error ? <div role="alert" className="mb-4 rounded-xl border border-bad bg-bad-soft px-4 py-3 text-sm text-bad">{error}</div> : null;
}
const fmt = (ms: number) => { const s = Math.max(0, Math.round(ms / 1000)), m = Math.floor(s / 60); return `${m ? m + "분 " : ""}${s % 60}초`; };
const ICON: Record<string, string> = { search: "검색", open: "열기", note: "메모" };

/** 작업 진행 — 단계 · 경과 시간 · 실시간 로그 */
export function JobProgress({ job, showLog = true }: { job: Job; showLog?: boolean }) {
  const [, tick] = useState(0);
  useEffect(() => { if (job.state !== "running") return; const t = setInterval(() => tick((x) => x + 1), 1000); return () => clearInterval(t); }, [job.state]);
  const searches = job.log.filter((l) => l.kind === "search").length, opened = job.log.filter((l) => l.kind === "open").length;
  return (
    <div className={`card ${job.state === "failed" ? "border-bad" : ""}`} aria-live="polite">
      {job.state === "running" && <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <b>{job.no}/{job.of}단계</b><span>{job.step}</span>
        <span className="hint">{fmt(Date.now() - job.stepStartedAt)} 지남 · 보통 {Math.max(1, Math.round(job.eta / 60))}분 · 창을 닫아도 계속됩니다</span>
      </div>}
      {job.state === "failed" && <p className="text-sm text-bad"><b>멈췄습니다.</b> {job.error}</p>}
      {job.state === "done" && <p className="text-sm"><b className="text-ok">끝났습니다.</b> <span className="hint">걸린 시간 {fmt(Date.now() - job.startedAt)} · 비용 ${job.costUsd.toFixed(2)}</span></p>}
      {showLog && job.log.length > 0 && <>
        <p className="hint mt-3">검색 {searches}번 · 연 페이지 {opened}곳</p>
        <ol className="mt-2 max-h-80 space-y-1 overflow-y-auto text-sm">
          {job.log.slice().reverse().map((l, i) => (
            <li key={i} className="grid grid-cols-[3rem_minmax(0,1fr)] gap-2">
              <span className={`text-xs ${l.kind === "search" ? "text-accent" : l.kind === "open" ? "text-ok" : "text-muted"}`}>{ICON[l.kind]}</span>
              <span className="truncate" title={l.text}>{l.text}</span>
            </li>))}
        </ol></>}
    </div>
  );
}
export function Steps({ steps, names }: { steps: Record<string, boolean>; names: [string, string][] }) {
  let now = false;
  return (
    <ol className="flex overflow-x-auto">
      {names.map(([k, n], i) => {
        const done = steps[k]; const cur = !done && !now && (now = true);
        return (
          <li key={k} className={`relative min-w-20 flex-1 text-center text-xs ${done ? "text-ok" : cur ? "font-bold text-accent" : "text-muted"}`}>
            {i > 0 && <span className={`absolute top-3.5 right-1/2 h-0.5 w-full ${done ? "bg-ok" : "bg-rule"}`} />}
            <span className={`relative z-10 mx-auto mb-1.5 grid size-7 place-items-center rounded-full border-2 bg-white ${done ? "border-ok bg-ok text-white" : cur ? "border-accent" : "border-rule"}`}>{done ? "✓" : i + 1}</span>
            {n}{cur && <span className="block text-[11px]">지금</span>}
          </li>);
      })}
    </ol>
  );
}
export const field = (text: string, key: string) => text.match(new RegExp(`\\*\\*${key}:\\*\\*\\s*(.+)`))?.[1] ?? "";
export const ago = (t?: string) => { if (!t) return ""; const s = (Date.now() - Date.parse(t)) / 1000; return s < 60 ? "방금" : s < 3600 ? `${Math.round(s / 60)}분 전` : s < 86400 ? `${Math.round(s / 3600)}시간 전` : `${Math.round(s / 86400)}일 전`; };
