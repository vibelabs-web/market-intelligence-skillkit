/** 서버 API 호출 · 작업 진행 구독 */
export async function api<T = any>(url: string, body?: unknown, method?: string): Promise<T> {
  const r = await fetch(url, body !== undefined || method ? { method: method ?? "POST", headers: { "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body) } : undefined);
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.error ?? "요청이 실패했습니다");
  return d as T;
}
export interface JobLog { kind: "search" | "open" | "note"; text: string; at: number }
export interface Job { id: string; kind: string; projectId?: string; run?: string; state: "running" | "done" | "failed"; step: string; no: number; of: number;
  startedAt: number; stepStartedAt: number; eta: number; log: JobLog[]; costUsd: number; result?: any; error?: string }
/** 작업이 끝날 때까지 진행 상황을 받는다 */
export function followJob(id: string, onUpdate: (j: Job) => void) {
  const es = new EventSource(`/api/jobs/${id}/events`);
  es.onmessage = (e) => { const j = JSON.parse(e.data) as Job; onUpdate(j); if (j.state !== "running") es.close(); };
  es.onerror = () => { es.close(); setTimeout(async () => { const { job } = await api<{ job: Job }>(`/api/jobs/${id}`); if (job) { onUpdate(job); if (job.state === "running") followJob(id, onUpdate); } }, 2000); };
  return () => es.close();
}
export const reviewer = { get: () => { try { return localStorage.getItem("reviewer") ?? ""; } catch { return ""; } }, set: (v: string) => { try { localStorage.setItem("reviewer", v); } catch { /* 저장 못 해도 동작한다 */ } } };
