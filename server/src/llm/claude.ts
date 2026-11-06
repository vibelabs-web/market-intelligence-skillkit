/**
 * claude -p 헤드리스 호출 — 이 앱에서 LLM 을 부르는 유일한 곳.
 *
 * - 빈 임시 폴더에서 실행해 모델이 저장소 파일을 읽거나 고치지 못하게 한다. 필요한 내용은 프롬프트로 넣는다.
 * - 사용자 설정 · MCP · 플러그인 · 스킬을 끄고 시스템 프롬프트를 직접 준다(교실 PC 마다 결과 · 비용이 달라지지 않게).
 * - 결과는 --json-schema 로 받은 구조화 출력이다. 서버가 그 값을 파일 · DB 에 쓴다.
 * - 웹 도구를 쓰면 검색어 · 연 페이지를 onEvent 로 실시간 알린다.
 */
import { spawn } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { CLAUDE_BIN, MODEL } from "../config.ts";

export type ClaudeEvent =
  | { kind: "search"; text: string }
  | { kind: "open"; text: string }
  | { kind: "note"; text: string };

export interface ClaudeRequest {
  prompt: string;
  system: string;
  schema: object;
  /** 허용할 도구. 기본은 없음(글만 읽고 쓴다). 리서치는 ["WebSearch","WebFetch"] */
  tools?: string[];
  model?: string;
  timeoutMs?: number;
  maxBudgetUsd?: number;
  onEvent?: (e: ClaudeEvent) => void;
}

export interface ClaudeResult<T> {
  data: T;
  costUsd: number;
  durationMs: number;
  turns: number;
  events: ClaudeEvent[];
}

export class ClaudeError extends Error {
  constructor(message: string, readonly detail = "") {
    super(message);
  }
}

function describe(name: string, input: Record<string, unknown>): ClaudeEvent | null {
  if (name === "WebSearch" && typeof input.query === "string") return { kind: "search", text: input.query };
  if (name === "WebFetch" && typeof input.url === "string") return { kind: "open", text: input.url };
  return null;
}

/** 한 번 실행. 구조화 출력이 없으면 ClaudeError */
function runOnce<T>(req: ClaudeRequest): Promise<ClaudeResult<T>> {
  const tools = req.tools ?? [];
  const args = [
    "-p", req.prompt,
    "--model", req.model ?? MODEL,
    "--output-format", "stream-json", "--verbose",
    "--setting-sources", "",
    "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
    "--disable-slash-commands", "--no-session-persistence",
    "--system-prompt", req.system,
    "--json-schema", JSON.stringify(req.schema),
    "--tools", tools.join(","),
  ];
  if (tools.length) args.push("--allowedTools", tools.join(","));
  if (req.maxBudgetUsd) args.push("--max-budget-usd", String(req.maxBudgetUsd));
  const cwd = mkdtempSync(path.join(tmpdir(), "mi-claude-"));
  const events: ClaudeEvent[] = [];
  return new Promise((resolve, reject) => {
    const child = spawn(CLAUDE_BIN, args, { cwd, stdio: ["ignore", "pipe", "pipe"] });
    let buf = "", err = "", result: any = null;
    const timer = setTimeout(() => { child.kill("SIGTERM"); }, req.timeoutMs ?? 15 * 60_000);
    const emit = (e: ClaudeEvent) => { events.push(e); req.onEvent?.(e); };
    child.stdout.on("data", (chunk: Buffer) => {
      buf += chunk.toString("utf8");
      let i: number;
      while ((i = buf.indexOf("\n")) >= 0) {
        const line = buf.slice(0, i).trim();
        buf = buf.slice(i + 1);
        if (!line) continue;
        let ev: any;
        try { ev = JSON.parse(line); } catch { continue; }
        if (ev.type === "assistant") {
          for (const c of ev.message?.content ?? []) {
            if (c.type === "tool_use") { const d = describe(c.name, c.input ?? {}); if (d) emit(d); }
          }
        } else if (ev.type === "result") result = ev;
      }
    });
    child.stderr.on("data", (c: Buffer) => { err += c.toString("utf8"); });
    child.on("error", (e) => { clearTimeout(timer); rmSync(cwd, { recursive: true, force: true }); reject(new ClaudeError(`claude 를 실행하지 못했습니다(${e.message}). Claude Code 가 설치되고 로그인되어 있어야 합니다.`)); });
    child.on("close", (code) => {
      clearTimeout(timer);
      rmSync(cwd, { recursive: true, force: true });
      if (!result) return reject(new ClaudeError(`claude 가 결과 없이 끝났습니다(종료 코드 ${code}).`, err.slice(-500)));
      if (result.is_error) return reject(new ClaudeError(`claude 작업 실패: ${String(result.result ?? result.subtype).slice(0, 300)}`, err.slice(-500)));
      const data = result.structured_output ?? (() => { try { return JSON.parse(result.result); } catch { return null; } })();
      if (data == null) return reject(new ClaudeError("구조화된 결과를 받지 못했습니다.", String(result.result ?? "").slice(0, 500)));
      resolve({ data, costUsd: result.total_cost_usd ?? 0, durationMs: result.duration_ms ?? 0, turns: result.num_turns ?? 0, events });
    });
  });
}

/** 형식이 맞지 않거나 실패하면 한 번 더 시도한다 */
export async function runClaude<T>(req: ClaudeRequest): Promise<ClaudeResult<T>> {
  try {
    return await runOnce<T>(req);
  } catch (e) {
    if (!(e instanceof ClaudeError) || /실행하지 못했습니다/.test(e.message)) throw e;
    req.onEvent?.({ kind: "note", text: "결과가 형식에 맞지 않아 한 번 더 요청합니다" });
    return await runOnce<T>({ ...req, prompt: req.prompt + "\n\n(앞선 시도가 실패했다. 요구한 형식의 결과를 반드시 낸다.)" });
  }
}
