/** 경로 · 모델 설정. 환경 변수로 바꿀 수 있다 */
import { fileURLToPath } from "node:url";
import path from "node:path";

export const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
export const DATA = path.resolve(process.env.MI_DATA ?? path.join(ROOT, "data"));
export const PATHS = {
  db: path.join(DATA, "mi.db"),
  projects: path.join(DATA, "projects"),
  runs: path.join(DATA, "runs"),
  golden: path.join(DATA, "golden"),
  playbook: path.join(ROOT, "playbook/mi-brief.md"),
  lens: path.join(ROOT, "my/lens.md"),
  rubric: path.join(ROOT, "project/rubric.md"),
  skills: path.join(ROOT, ".claude/skills"),
  web: path.join(ROOT, "web/dist"),
};
export const MODEL = process.env.MI_MODEL ?? "claude-sonnet-5-5";
export const CLAUDE_BIN = process.env.MI_CLAUDE_BIN ?? "claude";
export const PORT = Number(process.env.PORT ?? 8765);
