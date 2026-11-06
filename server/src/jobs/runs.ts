/** 브리핑 · 검토 · 수정안 · 적용 · 골든 — 판단 기준을 다듬는 흐름 */
import path from "node:path";
import { createHash } from "node:crypto";
import { existsSync, readdirSync, cpSync, mkdirSync, readFileSync, statSync } from "node:fs";
import { runClaude } from "../llm/claude.ts";
import { skill, read, API_NOTE, block } from "../prompts.ts";
import { PATHS, ROOT } from "../config.ts";
import { check, lengthIssue, parseCsv, norm, HARD_GATES, type Issue, type Rows } from "../checks/briefCheck.ts";
import { projectFiles, readJson, writeJson, writeText, readText, safeId, people, listDirs } from "../store.ts";
import { commitPaths, head, revertCommit } from "../git.ts";
import type { Ctx } from "./queue.ts";

const str = { type: "string" };
export const runDir = (run: string) => path.join(PATHS.runs, safeId(run));
const sha = (f: string) => (existsSync(f) ? createHash("sha256").update(readFileSync(f)).digest("hex").slice(0, 16) : null);

// ── 근거 · 검사 ──
export function rowsFor(projectId: string): Rows {
  const f = projectFiles(projectId), rows: Rows = {};
  for (const file of [f.register, f.internal]) for (const r of parseCsv(readText(file))) rows[r.evidence_id] = r;
  return rows;
}
export function checkBrief(projectId: string, person: string, text: string): Issue[] {
  const profile = readText(path.join(projectFiles(projectId).people, `${person}.md`));
  const allowed = new Set((profile.match(/(?<![\w.-])\d[\d,]*(?:\.\d+)?/g) ?? []).map(norm));
  const issues = check(text, rowsFor(projectId), new Set(), allowed);
  const len = lengthIssue(text, profile);
  return len ? [...issues, len] : issues;
}

// ── 이름 · 상태 ──
const ORD = ["첫", "두", "세", "네", "다섯", "여섯", "일곱", "여덟", "아홉", "열"];
export const runMeta = (run: string) => readJson<any>(path.join(runDir(run), "run.json"), {});
export function lineage(run: string): string[] {
  const seen: string[] = []; let cur: string | null = run; const project = runMeta(run).project;
  while (cur && !seen.includes(cur) && existsSync(runDir(cur)) && runMeta(cur).project === project) { seen.push(cur); cur = runMeta(cur).parent ?? null; }
  return seen;
}
export function personLabel(projectId: string, person: string) {
  const p = people(projectId).find((x) => x.id === person);
  return p ? p.title.split(/\s*[—-]\s*/)[0] : person;
}
export function runLabel(run: string) {
  const m = runMeta(run), n = lineage(run).length;
  return `${personLabel(m.project, m.person)} · ${n <= ORD.length ? ORD[n - 1] : n} 번째 브리핑`;
}
export function projectRuns(projectId: string) {
  return listDirs(PATHS.runs).filter((r) => runMeta(r).project === projectId && existsSync(path.join(runDir(r), "brief.md")))
    .sort((a, b) => statSync(runDir(b)).mtimeMs - statSync(runDir(a)).mtimeMs)
    .map((r) => ({ run: r, label: runLabel(r), status: runStatus(r), person: runMeta(r).person, parent: runMeta(r).parent ?? null, steps: runSteps(r) }));
}
export function runStatus(run: string) {
  const d = runDir(run);
  if (readJson<any>(path.join(d, "verdict.json"), {}).ok || listGoldens().some((g) => g.run === run)) return "승인됨";
  if (listDirs(PATHS.runs).some((r) => runMeta(r).parent === run)) return "이전 기준";
  if ((readJson<any>(path.join(d, "proposal.json"), null)?.changes ?? []).length) return "기준 개선 중";
  return "검토 필요";
}
export function runSteps(run: string) {
  const lin = lineage(run), fb = (r: string) => readJson<any[]>(path.join(runDir(r), "feedback.json"), []);
  return { brief: true, feedback: lin.some((r) => fb(r).length > 0), improve: lin.some((r) => existsSync(path.join(runDir(r), "applied.json"))),
    rerun: lin.length > 1, golden: listGoldens().some((g) => lin.includes(g.run)) };
}
function newRunName(projectId: string, person: string) {
  let n = 1;
  while (existsSync(runDir(`${projectId}-${person}-${String(n).padStart(2, "0")}`))) n++;
  return `${projectId}-${person}-${String(n).padStart(2, "0")}`;
}
const csv = (rows: { evidence_id: string; send: string; why: string }[]) =>
  "evidence_id,send,why\n" + rows.map((r) => [r.evidence_id, r.send, `"${(r.why ?? "").replace(/"/g, '""')}"`].join(",")).join("\n") + "\n";

// ── 브리핑 ──
const BRIEF_SCHEMA = { type: "object", additionalProperties: false, required: ["decision_md", "brief_md", "selection"], properties: {
  decision_md: str, brief_md: str,
  selection: { type: "array", items: { type: "object", additionalProperties: false, required: ["evidence_id", "send", "why"],
    properties: { evidence_id: str, send: { type: "string", enum: ["yes", "no"] }, why: str } } } } };

export async function makeBrief(ctx: Ctx, projectId: string, person: string, parent: string | null = null) {
  const f = projectFiles(projectId), profile = readText(path.join(f.people, `${person}.md`));
  if (!profile) throw new Error("없는 받는 사람입니다");
  const run = newRunName(projectId, person), d = runDir(run);
  ctx.job.run = run;
  ctx.step("판단표를 만들고 브리핑을 쓰는 중", 1, 2, 240);
  const base = [block(`받는 사람 설정 (people/${person}.md)`, profile), block("프로젝트 브리프 (brief.md)", readText(f.brief)), block("내 판단 기준 (my/lens.md)", read(PATHS.lens)),
    block("근거 표 (evidence-register.csv)", readText(f.register)), block("우리 회사 숫자 (internal-data.csv)", readText(f.internal))].join("\n\n");
  let prompt = `${base}\n\n지시문의 판단표와 브리핑을 쓰고, 근거 표의 모든 E- 행에 대해 보낼지(selection)를 정해 JSON 으로 답한다.`;
  let out: any = null, issues: Issue[] = [];
  for (let attempt = 0; attempt < 2; attempt++) {
    const r = await runClaude<any>({ prompt, system: read(PATHS.playbook) + API_NOTE, schema: BRIEF_SCHEMA, onEvent: ctx.event });
    ctx.cost(r.costUsd);
    out = r.data;
    issues = checkBrief(projectId, person, out.brief_md);
    if (!issues.some((i) => HARD_GATES.includes(i.gate)) || attempt === 1) break;
    ctx.event({ kind: "note", text: `코드 검사에서 객관 오류 ${issues.length}건 — 고쳐서 다시 씁니다` });
    prompt += `\n\n앞선 초안을 코드 검사가 지적했다. 고쳐서 전체를 다시 쓴다:\n${JSON.stringify(issues)}`;
  }
  writeText(path.join(d, "brief.md"), out.brief_md);
  writeText(path.join(d, "decision.md"), out.decision_md);
  writeText(path.join(d, "selection.csv"), csv(out.selection));
  writeJson(path.join(d, "check.json"), { issues });
  writeJson(path.join(d, "run.json"), { project: projectId, person, parent, skill_commit: head(), lens_sha: sha(PATHS.lens), evidence_sha: sha(f.register), at: new Date().toISOString() });
  ctx.step("검토 에이전트가 새 맥락에서 읽는 중", 2, 2, 90);
  await review(ctx, run);
  return { run, issues: issues.length };
}

// ── 독립 검토 ──
const REVIEW_SCHEMA = { type: "object", additionalProperties: false, required: ["review_md", "suggestions"], properties: { review_md: str,
  suggestions: { type: "array", items: { type: "object", additionalProperties: false, required: ["id", "quote", "comment", "kind", "who", "severity", "gate"],
    properties: { id: str, quote: str, comment: str, kind: { type: "string", enum: ["fix", "remove", "missing"] }, who: str,
      severity: { type: "string", enum: ["치명", "중요"] }, gate: { type: "string", enum: ["hard", "review"] } } } } } };

export async function review(ctx: Ctx, run: string) {
  const m = runMeta(run), d = runDir(run), f = projectFiles(m.project);
  const prompt = [block("브리핑 (brief.md)", readText(path.join(d, "brief.md"))), block("판단표 (decision.md)", readText(path.join(d, "decision.md"))),
    block("선별 (selection.csv)", readText(path.join(d, "selection.csv"))), block(`받는 사람 설정 (people/${m.person}.md)`, readText(path.join(f.people, `${m.person}.md`))),
    block("프로젝트 브리프", readText(f.brief)), block("평가 루브릭 (project/rubric.md)", read(PATHS.rubric)), block("내 판단 기준 (my/lens.md)", read(PATHS.lens)),
    block("근거 표", readText(f.register)), block("우리 회사 숫자", readText(f.internal))].join("\n\n");
  const r = await runClaude<any>({ prompt: prompt + "\n\n지시문대로 평가하고 JSON 으로 답한다.", system: skill("mi-review") + API_NOTE, schema: REVIEW_SCHEMA, onEvent: ctx.event });
  ctx.cost(r.costUsd);
  writeText(path.join(d, "review.md"), r.data.review_md);
  writeJson(path.join(d, "suggestions.json"), r.data.suggestions.slice(0, 5).map((s: any, i: number) => ({ ...s, id: s.id || `s${i + 1}` })));
  return { suggestions: r.data.suggestions.length };
}

// ── 수정안 ──
export const EDITABLE: Record<string, (projectId: string) => string> = {
  "playbook/mi-brief.md": () => PATHS.playbook, "my/lens.md": () => PATHS.lens, "project/rubric.md": () => PATHS.rubric,
};
export const TARGET_NAME: Record<string, string> = { "playbook/mi-brief.md": "공통 작업 규칙", "my/lens.md": "내 판단 기준", "project/rubric.md": "평가 루브릭" };
export function targetPath(file: string, projectId: string) {
  if (EDITABLE[file]) return EDITABLE[file](projectId);
  const m = file.match(/^people\/([a-z][a-z0-9-]*)\.md$/);
  if (m && existsSync(path.join(projectFiles(projectId).people, `${m[1]}.md`))) return path.join(projectFiles(projectId).people, `${m[1]}.md`);
  return null;
}
export const targetName = (file: string) => TARGET_NAME[file] ?? (file.startsWith("people/") ? "받는 사람 설정" : file);
export function checkChange(projectId: string, c: any): string {
  const p = targetPath(String(c.file ?? ""), projectId);
  if (!p) return `고칠 수 없는 파일입니다: ${c.file}`;
  const before = String(c.before ?? "");
  const n = before ? readText(p).split(before).length - 1 : 0;
  return n === 1 ? "" : `바꿀 문구가 파일에 ${n}번 있습니다(한 번이어야 합니다)`;
}
const PROPOSAL_SCHEMA = { type: "object", additionalProperties: false, required: ["changes", "warnings", "needs_data"], properties: {
  changes: { type: "array", items: { type: "object", additionalProperties: false, required: ["id", "file", "kind", "before", "after", "reason", "from_feedback"],
    properties: { id: str, file: str, kind: { type: "string", enum: ["add", "modify", "delete"] }, before: str, after: str, reason: str, from_feedback: { type: "array", items: str } } } },
  warnings: { type: "array", items: { type: "object", additionalProperties: false, required: ["feedback", "message"], properties: { feedback: str, message: str } } },
  needs_data: { type: "array", items: { type: "object", additionalProperties: false, required: ["what", "why", "feedback"], properties: { what: str, why: str, feedback: str } } } } };

export async function propose(ctx: Ctx, run: string) {
  const m = runMeta(run), d = runDir(run), f = projectFiles(m.project);
  const fb = readJson<any[]>(path.join(d, "feedback.json"), []);
  if (!fb.length) throw new Error("반영할 피드백이 없습니다");
  ctx.step("피드백을 자료와 대조해 기준 수정안을 만드는 중", 1, 1, 60);
  const files = ["playbook/mi-brief.md", "my/lens.md", "project/rubric.md", `people/${m.person}.md`];
  const prompt = [block("피드백 (feedback.json)", JSON.stringify(fb, null, 1)), block("AI 검토 의견과 컨설턴트의 동의 · 반대 (suggestions.json)", readText(path.join(d, "suggestions.json"))),
    block("브리핑", readText(path.join(d, "brief.md"))), block("판단표", readText(path.join(d, "decision.md"))), block("선별", readText(path.join(d, "selection.csv"))),
    block("프로젝트 브리프", readText(f.brief)), block("근거 표", readText(f.register)),
    ...files.map((x) => block(`고칠 수 있는 파일 ${x}`, readText(targetPath(x, m.project)!))),
    `수정안의 file 은 반드시 다음 중 하나다: ${files.join(", ")}. before 는 그 파일에 글자 그대로 한 번만 나오는 문자열이다. JSON 으로 답한다.`].join("\n\n");
  const r = await runClaude<any>({ prompt, system: skill("mi-feedback") + API_NOTE, schema: PROPOSAL_SCHEMA, onEvent: ctx.event });
  ctx.cost(r.costUsd);
  writeJson(path.join(d, "proposal.json"), r.data);
  return { changes: r.data.changes.length };
}
export function loadProposal(run: string) {
  const p = readJson<any>(path.join(runDir(run), "proposal.json"), null);
  if (!p) return null;
  const project = runMeta(run).project;
  let growth = 0;
  for (const c of p.changes ?? []) {
    c.problem = checkChange(project, c);
    c.target = targetName(c.file);
    const lost = String(c.before ?? "").split(/(?<=[.!?])\s+|\n+/).map((s: string) => s.trim()).filter((s: string) => s && !String(c.after ?? "").includes(s));
    if (lost.length) { c.removes = true; c.removed = lost; }
    if (String(c.file).startsWith("playbook/")) growth += String(c.after ?? "").length - String(c.before ?? "").length;
  }
  p.playbook_growth = growth;
  return p;
}

// ── 승인 적용 → 새 판 ──
export async function applyApproved(ctx: Ctx, run: string) {
  const m = runMeta(run), d = runDir(run), prop = loadProposal(run);
  const ok = (prop?.changes ?? []).filter((c: any) => c.decision === "approved");
  if (!ok.length) throw new Error("승인한 수정안이 없습니다");
  const bad = ok.filter((c: any) => c.problem);
  if (bad.length) throw new Error("적용할 수 없는 수정안을 승인했습니다: " + bad.map((c: any) => c.id).join(","));
  ctx.step("승인한 기준을 반영하는 중", 1, 2, 5);
  const texts = new Map<string, string>(), before = new Map<string, string>();
  for (const c of ok) {
    const p = targetPath(c.file, m.project)!;
    const cur = texts.get(p) ?? readText(p);
    if (!before.has(p)) before.set(p, cur);
    if (cur.split(c.before).length - 1 !== 1) throw new Error(`${c.id}: 다른 수정안과 겹칩니다`);
    texts.set(p, cur.replace(c.before, c.after ?? ""));
  }
  for (const [p, t] of texts) writeText(p, t);
  const repoFiles = [...texts.keys()].filter((p) => p.startsWith(ROOT + path.sep) && !p.startsWith(PATHS.projects)).map((p) => path.relative(ROOT, p));
  const commit = commitPaths(`기준 승인 반영: ${ok.map((c: any) => c.id).join(" · ")}`, repoFiles);
  ctx.step("승인한 기준으로 새 판을 만드는 중", 2, 2, 300);
  const made = await makeBrief(ctx, m.project, m.person, run);
  writeJson(path.join(runDir(made.run), "applied.json"), { from_run: run, commit, files: [...texts.keys()].map((p) => path.relative(ROOT, p)),
    before: Object.fromEntries([...before].filter(([p]) => p.startsWith(PATHS.projects)).map(([p, t]) => [path.relative(ROOT, p), t])) });
  return { new_run: made.run };
}
export function revertApplied(newRun: string) {
  const f = path.join(runDir(newRun), "applied.json"), a = readJson<any>(f, null);
  if (!a) throw new Error("되돌릴 변경이 없습니다");
  if (a.reverted) throw new Error("이미 되돌렸습니다");
  if (a.files.some((x: string) => !x.startsWith("data/"))) revertCommit(a.commit);
  for (const [rel, text] of Object.entries(a.before ?? {})) writeText(path.join(ROOT, rel), String(text));
  writeJson(f, { ...a, reverted: true });
  return { reverted: true };
}

// ── 골든 ──
export function listGoldens() {
  return listDirs(PATHS.golden).map((g) => ({ dir: g, ...readJson<any>(path.join(PATHS.golden, g, "golden.json"), {}) })).filter((g) => g.golden_id);
}
export function freezeGolden(run: string, reason: string, reviewer: string) {
  if (!reason.trim()) throw new Error("왜 이 결과를 승인하는지 한 줄 적어 주세요");
  const d = runDir(run), m = runMeta(run), grades = readJson<Record<string, string>>(path.join(d, "grades.json"), {});
  if (!Object.values(grades).includes("must") || !Object.values(grades).includes("never")) throw new Error("«누구에게 보내나»에서 꼭 보낼 근거와 절대 뺄 근거를 하나 이상 정해 주세요");
  const same = listGoldens().filter((g) => g.scope?.project === m.project && g.scope?.persona === m.person);
  const version = Math.max(0, ...same.map((g) => g.golden_version)) + 1;
  const prev = same.find((g) => g.status === "active");
  const id = `${m.project}-${m.person}-v${version}`, g = path.join(PATHS.golden, id);
  mkdirSync(g, { recursive: true });
  for (const n of readdirSync(d)) cpSync(path.join(d, n), path.join(g, n));
  const f = projectFiles(m.project);
  mkdirSync(path.join(g, "fact-pack"), { recursive: true });
  cpSync(f.register, path.join(g, "fact-pack/evidence-register.csv"));
  cpSync(f.internal, path.join(g, "fact-pack/internal-data.csv"));
  cpSync(path.join(f.people, `${m.person}.md`), path.join(g, "profile.md"));
  cpSync(PATHS.lens, path.join(g, "lens.md"));
  const meta = { golden_id: id, golden_version: version, status: "active", supersedes: prev?.golden_id ?? null,
    scope: { project: m.project, persona: m.person }, approved_by: reviewer || "컨설턴트", approved_at: new Date().toISOString(), approval_reason: reason.trim(),
    skill_commit: m.skill_commit ?? head(), lens_sha: sha(PATHS.lens), evidence_sha: sha(f.register), run, lineage: lineage(run), person: m.person,
    verdict: readJson(path.join(d, "verdict.json"), null) };
  writeJson(path.join(g, "golden.json"), meta);
  if (prev) setGoldenStatus(prev.dir, "superseded");
  return meta;
}
export function setGoldenStatus(dir: string, status: string) {
  if (!["active", "superseded", "retired"].includes(status)) throw new Error("상태는 active · superseded · retired 중 하나입니다");
  const f = path.join(PATHS.golden, safeId(dir), "golden.json"), m = readJson<any>(f, null);
  if (!m) throw new Error("없는 골든입니다");
  writeJson(f, { ...m, status });
  return { ...m, status, dir };
}
