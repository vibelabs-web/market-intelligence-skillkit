/** 작업 대기열 — 한 번에 하나. 진행 상황과 실시간 로그(검색어 · 연 페이지)를 구독자에게 보낸다 */
import type { ClaudeEvent } from "../llm/claude.ts";

export interface Job {
  id: string; kind: string; projectId?: string; run?: string; state: "running" | "done" | "failed";
  step: string; no: number; of: number; startedAt: number; stepStartedAt: number; eta: number;
  log: (ClaudeEvent & { at: number })[]; costUsd: number; result?: Record<string, unknown>; error?: string;
}
type Listener = (j: Job) => void;
const jobs = new Map<string, Job>();
const listeners = new Map<string, Set<Listener>>();
let seq = 0;

export const current = () => [...jobs.values()].find((j) => j.state === "running") ?? null;
export const getJob = (id: string) => jobs.get(id) ?? null;
export const latest = (projectId?: string) => [...jobs.values()].filter((j) => !projectId || j.projectId === projectId).at(-1) ?? null;

export function subscribe(id: string, fn: Listener) {
  const set = listeners.get(id) ?? new Set();
  set.add(fn); listeners.set(id, set);
  return () => set.delete(fn);
}
const publish = (j: Job) => listeners.get(j.id)?.forEach((fn) => fn(j));

export interface Ctx {
  job: Job;
  step: (text: string, no: number, of: number, eta: number) => void;
  event: (e: ClaudeEvent) => void;
  cost: (usd: number) => void;
}

export function start(kind: string, meta: { projectId?: string; run?: string }, work: (ctx: Ctx) => Promise<Record<string, unknown>>): Job {
  if (current()) throw new Error("다른 작업이 진행 중입니다. 끝난 뒤에 다시 눌러 주세요");
  const t = Date.now();
  const job: Job = { id: `j${++seq}-${t}`, kind, ...meta, state: "running", step: "시작", no: 1, of: 1, startedAt: t, stepStartedAt: t, eta: 60, log: [], costUsd: 0 };
  jobs.set(job.id, job);
  const ctx: Ctx = {
    job,
    step: (text, no, of, eta) => { Object.assign(job, { step: text, no, of, eta, stepStartedAt: Date.now() }); publish(job); },
    event: (e) => { job.log.push({ ...e, at: Date.now() }); if (job.log.length > 300) job.log.shift(); publish(job); },
    cost: (usd) => { job.costUsd += usd; publish(job); },
  };
  work(ctx).then((result) => { Object.assign(job, { state: "done", result }); publish(job); })
    .catch((e: Error) => { Object.assign(job, { state: "failed", error: e.message }); publish(job); });
  return job;
}
