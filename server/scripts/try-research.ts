// 리서치 작업을 화면 없이 한 번 돌려 본다: MI_DATA=<폴더> npx tsx server/scripts/try-research.ts
import { Knowledge } from "../src/db/knowledge.ts";
import { PATHS } from "../src/config.ts";
import { start, subscribe } from "../src/jobs/queue.ts";
import { research } from "../src/jobs/research.ts";
import { newProjectId, writeBrief, writeInternal, writeJson, projectFiles, type Project } from "../src/store.ts";

const kb = new Knowledge(PATHS.db);
const p: Project = { id: newProjectId(), title: process.argv[2] ?? "한국 산업용 전동기 제조사의 수출 우선순위", question: process.argv[3] ?? "한국 산업용 저압 전동기 제조사는 베트남과 태국 중 어디부터 수출을 늘려야 하는가",
  context: "국내 산업용 저압 3상 전동기 제조사. 동남아 수출을 검토 중이다.", people: "대표 · 구매 책임자 · 해외영업 책임자", scope: "두 나라의 전동기 수요 · 효율 규제와 인증 · 관세 · 경쟁사 · 원자재(구리 · 희토류 자석)", numbers: "", created_at: new Date().toISOString() };
kb.saveProject(p); writeJson(projectFiles(p.id).meta, p); writeBrief(p); writeInternal(p.id, p.numbers);
const job = start("research", { projectId: p.id }, (ctx) => research(ctx, kb, p));
let last = 0;
subscribe(job.id, (j) => {
  for (const e of j.log.slice(last)) console.log(`  ${e.kind === "search" ? "검색" : e.kind === "open" ? "열기" : "메모"}: ${e.text}`);
  last = j.log.length;
  if (j.state !== "running") { console.log(j.state, JSON.stringify(j.result ?? j.error), "비용", j.costUsd.toFixed(3)); console.log("project", p.id); process.exit(j.state === "done" ? 0 : 1); }
});
