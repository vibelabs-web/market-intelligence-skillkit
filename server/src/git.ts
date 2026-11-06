/** 기준 파일(작업 규칙 · 판단 기준 · 루브릭)의 승인 기록을 git 으로 남긴다 */
import { execFileSync } from "node:child_process";
import { ROOT } from "./config.ts";

export function git(args: string[], cwd = ROOT): { ok: boolean; out: string } {
  try {
    return { ok: true, out: execFileSync("git", ["-c", "user.name=mi-workbench", "-c", "user.email=mi@local", ...args], { cwd, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] }) };
  } catch (e: any) {
    return { ok: false, out: String(e.stderr ?? e.message) };
  }
}
export const head = (cwd = ROOT) => git(["rev-parse", "--short", "HEAD"], cwd).out.trim();
/** 이 파일만 커밋한다. 다른 변경은 같이 커밋하지 않는다 */
export function commitPaths(message: string, files: string[], cwd = ROOT) {
  if (!files.length) return head(cwd);
  git(["add", "--", ...files], cwd);
  const r = git(["commit", "-qm", message, "--", ...files], cwd);
  if (!r.ok && !/nothing to commit|no changes added/.test(r.out)) throw new Error("커밋하지 못했습니다: " + r.out.slice(0, 200));
  return head(cwd);
}
/** 그 승인만 되돌린다. 뒤의 승인과 겹치면 아무것도 바꾸지 않는다 */
export function revertCommit(commit: string, cwd = ROOT) {
  const r = git(["revert", "--no-edit", commit], cwd);
  if (!r.ok) { git(["revert", "--abort"], cwd); throw new Error("뒤에 승인한 수정과 겹쳐 되돌리지 못했습니다. 바뀐 파일은 없습니다"); }
}
