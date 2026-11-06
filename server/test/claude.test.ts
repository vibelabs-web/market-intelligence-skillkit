import { describe, it, expect, beforeAll } from "vitest";
import path from "node:path";
import { fileURLToPath } from "node:url";

const fake = path.join(path.dirname(fileURLToPath(import.meta.url)), "fake-claude.mjs");
process.env.MI_CLAUDE_BIN = fake;
let runClaude: typeof import("../src/llm/claude.ts").runClaude;
beforeAll(async () => { ({ runClaude } = await import("../src/llm/claude.ts")); });
const req = { prompt: "x", system: "s", schema: { type: "object" } };

describe("claude -p 호출", () => {
  it("구조화 출력 · 비용을 받고, 빈 임시 폴더에서 실행한다", async () => {
    process.env.FAKE_MODE = "ok";
    const r = await runClaude<any>(req);
    expect(r.data.ok).toBe(true);
    expect(r.data.sawSchema).toBe(true);
    expect(r.data.cwd).toMatch(/mi-claude-/);
    expect(r.costUsd).toBe(0.02);
  });
  it("검색어 · 연 페이지를 실시간으로 알린다", async () => {
    process.env.FAKE_MODE = "web";
    const seen: string[] = [];
    const r = await runClaude<any>({ ...req, tools: ["WebSearch", "WebFetch"], onEvent: (e) => seen.push(`${e.kind}:${e.text}`) });
    expect(seen).toEqual(["search:베트남 전동기 라벨", "open:https://example.org/a"]);
    expect(r.events.length).toBe(2);
  });
  it("실패하면 한 번 더 시도한다", async () => {
    process.env.FAKE_MODE = "fail-once";
    const notes: string[] = [];
    const r = await runClaude<any>({ ...req, onEvent: (e) => notes.push(e.kind) });
    expect(r.data.ok).toBe(true);
    expect(notes).toContain("note");
  });
  it("결과가 없으면 알기 쉬운 오류", async () => {
    process.env.FAKE_MODE = "no-result";
    await expect(runClaude<any>(req)).rejects.toThrow(/결과 없이/);
  });
});
