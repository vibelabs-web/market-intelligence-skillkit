/** 리서치 — 정한 방향으로 새로 조사하고, 자료를 지식 DB 에 쌓고, 프로젝트 근거 표 · 받는 사람 설정을 만든다 */
import path from "node:path";
import { runClaude } from "../llm/claude.ts";
import { Knowledge } from "../db/knowledge.ts";
import type { ClaimIn, ConceptIn } from "../db/knowledge.ts";
import { skill, API_NOTE, block } from "../prompts.ts";
import { projectFiles, writeText, type Project } from "../store.ts";
import type { Ctx } from "./queue.ts";

const str = { type: "string" };
export const RESEARCH_SCHEMA = {
  type: "object", additionalProperties: false,
  required: ["claims", "concepts", "people", "gaps"],
  properties: {
    claims: { type: "array", items: { type: "object", additionalProperties: false, required: ["key", "claim", "quote", "source_url"],
      properties: { key: str, knowledge_id: str, claim: str, quote: str, source_url: str, source_title: str, publisher: str, published_at: str, source_type: str,
        domain: { type: "string", enum: ["demand", "regulation", "competitor", "supply", "macro", "other"] }, region: str, data_period: str,
        status: { type: "string", enum: ["confirmed", "proposed", "uncertain"] }, confidence: str, limitations: str, conflict_with: { type: "array", items: str } } } },
    concepts: { type: "array", items: { type: "object", additionalProperties: false, required: ["name", "summary", "claims"],
      properties: { name: str, summary: str, claims: { type: "array", items: str } } } },
    people: { type: "array", items: { type: "object", additionalProperties: false,
      required: ["id", "role", "decides", "deadline", "authority", "avoid_surprise", "watch", "not_needed", "format"],
      properties: { id: { type: "string", pattern: "^[a-z][a-z0-9-]{1,24}$" }, role: str, decides: str, deadline: str, authority: str, avoid_surprise: str, watch: str, not_needed: str, format: str } } },
    gaps: { type: "array", items: str },
  },
};
interface ResearchOut { claims: (ClaimIn & { key: string })[]; concepts: ConceptIn[]; people: Record<string, string>[]; gaps: string[] }

export function knownBlock(kb: Knowledge, p: Project) {
  const q = `${p.question} ${p.scope} ${p.context}`;
  const claims = kb.search(q, 40), concepts = kb.searchConcepts(q, 12);
  const lines = [
    ...concepts.map((c) => `[개념 ${c.id}] ${c.name} — ${c.summary}`),
    ...claims.map((c) => `[${c.id}] ${c.claim} | 상태 ${c.status} | 출처 ${c.publisher || c.source_title || ""} ${c.url} | 마지막 확인 ${String(c.last_checked).slice(0, 10)}`),
  ];
  return { text: lines.join("\n"), claims: claims.length, concepts: concepts.length };
}

export async function research(ctx: Ctx, kb: Knowledge, p: Project) {
  const f = projectFiles(p.id);
  ctx.step("지식 DB 에서 이미 아는 자료를 찾는 중", 1, 3, 3);
  const known = knownBlock(kb, p);
  ctx.event({ kind: "note", text: `지식 DB 에서 관련 자료 ${known.claims}건 · 개념 ${known.concepts}개를 찾았습니다` });
  ctx.step("웹에서 새로 조사하는 중 (검색 → 페이지 확인)", 2, 3, 900);
  const prompt = [
    block("결정 질문", p.question), block("고객 상황 (컨설턴트 입력)", p.context), block("받는 사람 (역할)", p.people), block("범위", p.scope),
    block("이미 아는 것 (지식 DB)", known.text), `오늘은 ${new Date().toISOString().slice(0, 10)} 이다. 지시문대로 조사하고 JSON 으로 답한다.`,
  ].join("\n\n");
  const r = await runClaude<ResearchOut>({ prompt, system: skill("mi-topic") + API_NOTE, schema: RESEARCH_SCHEMA, tools: ["WebSearch", "WebFetch"],
    timeoutMs: 30 * 60_000, maxBudgetUsd: Number(process.env.MI_RESEARCH_BUDGET ?? 6), onEvent: ctx.event });
  ctx.cost(r.costUsd);
  ctx.step("자료를 지식 DB 에 쌓고 개념으로 정리하는 중", 3, 3, 5);
  const out = r.data;
  const searches = r.events.filter((e) => e.kind === "search").map((e) => e.text), opened = r.events.filter((e) => e.kind === "open").map((e) => e.text);
  const ing = kb.ingest(p.id, out.claims, out.concepts, { costUsd: r.costUsd, searches, opened, gaps: out.gaps });
  const n = kb.exportRegister(p.id, f.register);
  for (const pp of out.people) {
    writeText(path.join(f.people, `${pp.id}.md`), `# ${pp.role}\n- **결정할 일:** ${pp.decides}\n- **결정 시점:** ${pp.deadline}\n- **권한:** ${pp.authority}\n- **놀라고 싶지 않은 것:** ${pp.avoid_surprise}\n- **더 알아야 할 주체:** ${pp.watch}\n- **안 받아도 되는 것:** ${pp.not_needed}\n- **형식:** ${pp.format}\n`);
  }
  writeText(f.notes, `# 리서치 메모\n\n조사일: ${new Date().toISOString().slice(0, 10)} · 새 자료 ${ing.new}건 · 재사용 ${ing.reused}건 · 개념 ${ing.concepts}개 · 비용 $${r.costUsd.toFixed(2)}\n\n## 찾지 못한 것\n${out.gaps.map((g) => `- ${g}`).join("\n") || "- 없음"}\n\n## 검색어\n${searches.map((s) => `- ${s}`).join("\n")}\n\n## 연 페이지\n${opened.map((s) => `- ${s}`).join("\n")}\n`);
  return { ...ing, register: n, people: out.people.length, gaps: out.gaps.length, costUsd: r.costUsd };
}
