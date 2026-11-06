/** Market Intelligence 워크벤치 서버 — http://127.0.0.1:8765 */
import Fastify from "fastify";
import fastifyStatic from "@fastify/static";
import path from "node:path";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { PATHS, PORT, ROOT, MODEL } from "./config.ts";
import { Knowledge, readOnlyQuery } from "./db/knowledge.ts";
import { start, current, getJob, latest, subscribe } from "./jobs/queue.ts";
import { research } from "./jobs/research.ts";
import * as R from "./jobs/runs.ts";
import { criteria } from "./criteria.ts";
import { commitPaths } from "./git.ts";
import { newProjectId, projectFiles, readJson, writeJson, writeText, readText, writeBrief, writeInternal, people, safeId, type Project } from "./store.ts";
import { parseCsv } from "./checks/briefCheck.ts";

const kb = new Knowledge(PATHS.db);
const app = Fastify({ bodyLimit: 2_000_000 });
const bad = (msg: string) => Object.assign(new Error(msg), { statusCode: 400 });
app.setErrorHandler((e: any, _req, reply) => { reply.code(e.statusCode && e.statusCode < 500 ? e.statusCode : 400).send({ error: e.message }); });
const id = (s: unknown) => { try { return safeId(String(s)); } catch (e: any) { throw bad(e.message); } };
const runOf = (s: unknown) => { const r = id(s); if (!existsSync(R.runDir(r))) throw bad("없는 브리핑입니다"); return r; };
const proj = (pid: string): Project => { const p = readJson<Project | null>(projectFiles(id(pid)).meta, null); if (!p) throw bad("없는 프로젝트입니다"); return p; };

// ── 프로젝트 · 리서치 ──
app.get("/api/projects", async () => ({ projects: kb.projects().map((p) => ({ ...p, briefs: R.projectRuns(p.id).length })), job: current(), model: MODEL }));
app.post("/api/projects", async (req: any) => {
  const b = req.body ?? {};
  const question = String(b.question ?? "").trim();
  if (question.length < 6) throw bad("결정할 질문을 한 문장으로 적어 주세요");
  if (!String(b.people ?? "").trim()) throw bad("브리핑을 받을 사람(역할)을 적어 주세요");
  const p: Project = { id: newProjectId(), title: String(b.title ?? "").trim() || question.slice(0, 50), question, context: String(b.context ?? ""), people: String(b.people),
    scope: String(b.scope ?? ""), numbers: String(b.numbers ?? ""), created_at: new Date().toISOString() };
  kb.saveProject(p); writeJson(projectFiles(p.id).meta, p); writeBrief(p); writeInternal(p.id, p.numbers);
  const job = start("research", { projectId: p.id }, (ctx) => research(ctx, kb, p));
  return { project: p, job };
});
app.post("/api/projects/:id/research", async (req: any) => { const p = proj(req.params.id); return { job: start("research", { projectId: p.id }, (ctx) => research(ctx, kb, p)) }; });
app.get("/api/projects/:id", async (req: any) => {
  const p = proj(req.params.id), f = projectFiles(p.id);
  return { project: p, people: people(p.id), runs: R.projectRuns(p.id), research: kb.runs(p.id), claims: kb.projectClaims(p.id).length,
    reused: kb.projectClaims(p.id).filter((c) => c.reused).length, notes: readText(f.notes), internal: parseCsv(readText(f.internal)), job: latest(p.id), criteria: criteria() };
});
app.put("/api/projects/:id/people/:pid", async (req: any) => {
  if (current()) throw bad("작업이 끝난 뒤에 저장할 수 있습니다");
  const f = path.join(projectFiles(proj(req.params.id).id).people, `${id(req.params.pid)}.md`);
  if (!existsSync(f)) throw bad("없는 받는 사람입니다");
  const text = String(req.body?.text ?? "");
  if (!text.includes("결정")) throw bad("«결정할 일»이 있어야 합니다");
  writeText(f, text.trimEnd() + "\n");
  return { ok: true };
});
app.post("/api/projects/:id/briefs", async (req: any) => {
  const p = proj(req.params.id), person = id(req.body?.person);
  if (!people(p.id).some((x) => x.id === person)) throw bad("없는 받는 사람입니다");
  return { job: start("brief", { projectId: p.id }, (ctx) => R.makeBrief(ctx, p.id, person)) };
});
app.get("/api/projects/:id/evidence/:eid", async (req: any) => {
  const f = projectFiles(proj(req.params.id).id);
  const row = [...parseCsv(readText(f.register)), ...parseCsv(readText(f.internal))].find((r) => r.evidence_id === req.params.eid);
  if (!row) throw bad("근거 표에 없는 번호입니다");
  return row;
});

// ── 브리핑 검토 ──
app.get("/api/runs/:run", async (req: any) => {
  const run = runOf(req.params.run), d = R.runDir(run), m = R.runMeta(run), f = projectFiles(m.project);
  const reg = Object.fromEntries([...parseCsv(readText(f.register)), ...parseCsv(readText(f.internal))].map((r) => [r.evidence_id, r]));
  const parent = m.parent;
  const brief = readText(path.join(d, "brief.md"));
  const pfb = parent ? readJson<any[]>(path.join(R.runDir(parent), "feedback.json"), []).filter((x) => x.kind !== "good") : [];
  const resolved = readJson<any>(path.join(d, "ui.json"), {}).resolved ?? {};
  return { run, label: R.runLabel(run), status: R.runStatus(run), meta: m, project: proj(m.project), person: R.personLabel(m.project, m.person),
    profile: readText(path.join(f.people, `${m.person}.md`)), brief, decision: readText(path.join(d, "decision.md")), review: readText(path.join(d, "review.md")),
    selection: parseCsv(readText(path.join(d, "selection.csv"))).map((r) => ({ ...r, claim: reg[r.evidence_id]?.claim ?? "", status: reg[r.evidence_id]?.status ?? "" })),
    check: readJson(path.join(d, "check.json"), { issues: [] }), suggestions: readJson(path.join(d, "suggestions.json"), []), feedback: readJson(path.join(d, "feedback.json"), []),
    proposal: R.loadProposal(run), applied: readJson(path.join(d, "applied.json"), null), verdict: readJson(path.join(d, "verdict.json"), null),
    grades: readJson(path.join(d, "grades.json"), {}), ui: readJson(path.join(d, "ui.json"), {}), lineage: R.lineage(run).map((r) => ({ run: r, label: R.runLabel(r) })),
    parentBrief: parent ? readText(path.join(R.runDir(parent), "brief.md")) : null,
    parentFeedback: pfb.map((x) => ({ ...x, stillThere: !!x.quote && brief.includes(x.quote), state: resolved[x.id] ?? null })),
    golden: R.listGoldens().find((g) => g.run === run) ?? null, criteria: { version: criteria().version, order: criteria().order }, job: latest(m.project) };
});
const runFile = (run: string, n: string) => path.join(R.runDir(run), n);
app.post("/api/runs/:run/feedback", async (req: any) => {
  const run = runOf(req.params.run), b = req.body ?? {};
  if (!String(b.comment ?? "").trim() && b.kind !== "good") throw bad("무엇이 문제인지 한 줄 적어 주세요");
  const item = { id: Math.random().toString(16).slice(2, 10), quote: String(b.quote ?? ""), comment: String(b.comment ?? ""), kind: String(b.kind ?? "fix"),
    category: b.category ?? null, occurrence: Number(b.occurrence ?? 0), reviewer: String(b.reviewer ?? ""), at: new Date().toISOString() };
  const list = readJson<any[]>(runFile(run, "feedback.json"), []); list.push(item); writeJson(runFile(run, "feedback.json"), list);
  return item;
});
app.delete("/api/runs/:run/feedback/:fid", async (req: any) => {
  const run = runOf(req.params.run);
  writeJson(runFile(run, "feedback.json"), readJson<any[]>(runFile(run, "feedback.json"), []).filter((x) => x.id !== req.params.fid));
  return { ok: true };
});
app.post("/api/runs/:run/reveal", async (req: any) => { const run = runOf(req.params.run); const ui = { ...readJson<any>(runFile(run, "ui.json"), {}), revealed: true }; writeJson(runFile(run, "ui.json"), ui); return ui; });
app.post("/api/runs/:run/suggestions/:sid", async (req: any) => {
  const run = runOf(req.params.run), b = req.body ?? {}, list = readJson<any[]>(runFile(run, "suggestions.json"), []);
  const s = list.find((x) => String(x.id) === req.params.sid);
  if (!s) throw bad("없는 의견입니다");
  if (!b.accept && !String(b.note ?? "").trim()) throw bad("반대하는 이유를 한 줄 적어 주세요");
  Object.assign(s, { state: b.accept ? "accepted" : "rejected", note: String(b.note ?? ""), reviewer: String(b.reviewer ?? "") });
  writeJson(runFile(run, "suggestions.json"), list);
  if (b.accept) {
    const fb = readJson<any[]>(runFile(run, "feedback.json"), []);
    fb.push({ id: Math.random().toString(16).slice(2, 10), quote: s.quote, comment: b.note || s.comment, kind: s.kind, category: null, occurrence: 0, from_suggestion: s.id, reviewer: String(b.reviewer ?? ""), at: new Date().toISOString() });
    writeJson(runFile(run, "feedback.json"), fb);
  }
  return s;
});
app.post("/api/runs/:run/grade", async (req: any) => {
  const run = runOf(req.params.run), b = req.body ?? {};
  if (!["must", "never", "any"].includes(b.grade)) throw bad("등급은 must · never · any 중 하나입니다");
  const g = { ...readJson<any>(runFile(run, "grades.json"), {}), [String(b.id)]: b.grade }; writeJson(runFile(run, "grades.json"), g); return g;
});
app.post("/api/runs/:run/propose", async (req: any) => { const run = runOf(req.params.run); const m = R.runMeta(run); return { job: start("propose", { projectId: m.project, run }, (ctx) => R.propose(ctx, run)) }; });
app.post("/api/runs/:run/decide", async (req: any) => {
  const run = runOf(req.params.run), b = req.body ?? {}, p = readJson<any>(runFile(run, "proposal.json"), null);
  const c = p?.changes?.find((x: any) => String(x.id) === String(b.id));
  if (!c) throw bad("없는 수정안입니다");
  Object.assign(c, { decision: b.approve ? "approved" : "rejected", decided_by: String(b.reviewer ?? ""), note: String(b.note ?? "") });
  writeJson(runFile(run, "proposal.json"), p);
  return c;
});
app.post("/api/runs/:run/apply", async (req: any) => {
  const run = runOf(req.params.run), p = R.loadProposal(run), cs = p?.changes ?? [];
  if (cs.some((c: any) => !c.decision)) throw bad("모든 수정안을 승인하거나 거절해 주세요");
  if (!cs.some((c: any) => c.decision === "approved")) throw bad("승인한 수정안이 없습니다");
  return { job: start("apply", { projectId: R.runMeta(run).project, run }, (ctx) => R.applyApproved(ctx, run)) };
});
app.post("/api/runs/:run/revert", async (req: any) => R.revertApplied(runOf(req.params.run)));
app.post("/api/runs/:run/verdict", async (req: any) => {
  const run = runOf(req.params.run), b = req.body ?? {};
  const v = { ok: !!b.ok, reason: String(b.reason ?? ""), reviewer: String(b.reviewer ?? ""), at: new Date().toISOString() }; writeJson(runFile(run, "verdict.json"), v); return v;
});
app.post("/api/runs/:run/golden", async (req: any) => R.freezeGolden(runOf(req.params.run), String(req.body?.reason ?? ""), String(req.body?.reviewer ?? "")));
app.post("/api/runs/:run/resolve", async (req: any) => {
  const run = runOf(req.params.run), b = req.body ?? {};
  if (!["fixed", "open", "worse"].includes(b.state)) throw bad("해결됨 · 아직 · 나빠짐 중 하나입니다");
  const ui = readJson<any>(runFile(run, "ui.json"), {}); ui.resolved = { ...(ui.resolved ?? {}), [String(b.id)]: b.state }; writeJson(runFile(run, "ui.json"), ui); return ui;
});

// ── 작업 진행 ──
app.get("/api/jobs/current", async () => ({ job: current() }));
app.get("/api/jobs/:id", async (req: any) => ({ job: getJob(req.params.id) }));
app.get("/api/jobs/:id/events", (req: any, reply) => {
  const job = getJob(req.params.id);
  if (!job) return reply.code(404).send({ error: "없는 작업입니다" });
  reply.raw.writeHead(200, { "Content-Type": "text/event-stream", "Cache-Control": "no-store", Connection: "keep-alive" });
  const send = (j: unknown) => reply.raw.write(`data: ${JSON.stringify(j)}\n\n`);
  send(job);
  const off = subscribe(job.id, (j) => { send(j); if (j.state !== "running") { off(); reply.raw.end(); } });
  req.raw.on("close", off);
});

// ── 내 판단 기준 · 골든 ──
app.get("/api/criteria", async () => criteria());
app.put("/api/criteria", async (req: any) => {
  const text = String(req.body?.text ?? "");
  if (!text.includes("## 판단 기준 순서")) throw bad("«## 판단 기준 순서» 제목은 남겨 주세요");
  if (current()) throw bad("작업이 끝난 뒤에 저장할 수 있습니다");
  writeText(PATHS.lens, text.trimEnd() + "\n");
  commitPaths("내 판단 기준 직접 수정", [path.relative(ROOT, PATHS.lens)]);
  return criteria();
});
app.get("/api/goldens", async () => ({ goldens: R.listGoldens() }));
app.post("/api/goldens/:dir/status", async (req: any) => R.setGoldenStatus(id(req.params.dir), String(req.body?.status ?? "")));

// ── 지식 DB 조회기 ──
app.get("/api/library/stats", async () => kb.stats());
app.get("/api/library/projects", async () => kb.projects());
app.get("/api/library/concepts", async (req: any) => kb.concepts(String(req.query.q ?? "")));
app.get("/api/library/concepts/:cid", async (req: any) => kb.concept(req.params.cid) ?? Promise.reject(bad("없는 개념입니다")));
app.get("/api/library/claims", async (req: any) => kb.claims({ q: req.query.q, project: req.query.project, limit: Number(req.query.limit ?? 300) }));
app.get("/api/library/sources", async () => kb.sources());
app.get("/api/library/runs", async (req: any) => kb.runs(req.query.project));
app.post("/api/library/query", async (req: any) => { try { return readOnlyQuery(PATHS.db, String(req.body?.sql ?? "")); } catch (e: any) { throw bad(e.message); } });

// ── 개발자 ──
app.get("/api/dev/results", async () => {
  const d = path.join(ROOT, "dev/results");
  return existsSync(d) ? readdirSync(d).filter((f) => f.endsWith(".json")).map((f) => { try { return JSON.parse(readFileSync(path.join(d, f), "utf8")); } catch { return null; } }).filter(Boolean) : [];
});

// ── 화면 ──
if (existsSync(PATHS.web)) {
  await app.register(fastifyStatic, { root: PATHS.web });
  app.setNotFoundHandler((req, reply) => (req.url.startsWith("/api/") ? reply.code(404).send({ error: "없음" }) : reply.sendFile("index.html")));
}
await app.listen({ host: "127.0.0.1", port: PORT });
console.log(`Market Intelligence 워크벤치: http://127.0.0.1:${PORT}  (모델 ${MODEL} · claude -p)`);
