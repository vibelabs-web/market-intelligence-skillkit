#!/usr/bin/env node
// 테스트용 가짜 claude. FAKE_MODE 로 동작을 고른다
const mode = process.env.FAKE_MODE ?? "ok";
const args = process.argv.slice(2);
const out = (o) => process.stdout.write(JSON.stringify(o) + "\n");
out({ type: "system", subtype: "init", tools: [] });
if (mode === "web") {
  out({ type: "assistant", message: { content: [{ type: "tool_use", name: "WebSearch", input: { query: "베트남 전동기 라벨" } }] } });
  out({ type: "assistant", message: { content: [{ type: "tool_use", name: "WebFetch", input: { url: "https://example.org/a" } }] } });
}
if (mode === "fail-once" && !args.join(" ").includes("앞선 시도가 실패했다")) {
  out({ type: "result", subtype: "error_max_turns", is_error: true, result: "실패", total_cost_usd: 0.01 });
  process.exit(1);
}
if (mode === "no-result") process.exit(3);
out({ type: "result", subtype: "success", is_error: false, total_cost_usd: 0.02, duration_ms: 1200, num_turns: 2, result: "{}", structured_output: { ok: true, sawSchema: args.includes("--json-schema"), cwd: process.cwd() } });
