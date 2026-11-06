/** 내 판단 기준 — 순서 · 변화 기록 */
import path from "node:path";
import { existsSync } from "node:fs";
import { PATHS } from "./config.ts";
import { read } from "./prompts.ts";
import { git } from "./git.ts";
import { readJson, listDirs } from "./store.ts";
import { runDir, runLabel, runMeta, targetName } from "./jobs/runs.ts";

export function lensOrder(): string[] {
  const m = read(PATHS.lens).match(/## 판단 기준 순서[^\n]*\n(?:(?!\s*\d+\.)[^\n]*\n)*?((?:[ \t]*\d+\.[^\n]*\n?)+)/);
  return m ? m[1].split("\n").map((l) => l.replace(/^\s*\d+\.\s*/, "").trim()).filter(Boolean) : [];
}
export function history() {
  const rows: any[] = [];
  for (const r of listDirs(PATHS.runs)) {
    const a = readJson<any>(path.join(runDir(r), "applied.json"), null);
    if (!a) continue;
    const src = a.from_run, prop = readJson<any>(path.join(runDir(src), "proposal.json"), {}), fb = readJson<any[]>(path.join(runDir(src), "feedback.json"), []);
    const ok = (prop.changes ?? []).filter((c: any) => c.decision === "approved");
    rows.push({ at: readJson<any>(path.join(runDir(r), "run.json"), {}).at ?? "", from_run: src, new_run: r, project: runMeta(r).project,
      from_label: existsSync(runDir(src)) ? runLabel(src) : src, new_label: runLabel(r), commit: a.commit, reverted: !!a.reverted,
      feedback: ok.flatMap((c: any) => c.from_feedback ?? []).map((id: string) => fb.find((x) => x.id === id)).filter(Boolean).map((x: any) => x.comment || x.quote).slice(0, 3),
      changes: ok.map((c: any) => ({ target: targetName(c.file), reason: c.reason })), approver: [...new Set(ok.map((c: any) => c.decided_by || "컨설턴트"))].join(", ") });
  }
  for (const line of git(["log", "--format=%h|%cI|%s", "--", "my/lens.md"]).out.split("\n")) {
    const [h, at, subj] = line.split("|");
    if (subj?.startsWith("내 판단 기준 직접 수정")) rows.push({ at, commit: h, reverted: false, feedback: ["(피드백 없이 직접 수정)"], changes: [{ target: "내 판단 기준", reason: "판단 순서 · 기준을 직접 고침" }], approver: "컨설턴트" });
  }
  rows.sort((a, b) => String(a.at).localeCompare(String(b.at)));
  let v = 1;
  for (const r of rows) if (!r.reverted) r.version = ++v;
  return rows;
}
export const criteria = () => { const h = history(); return { version: 1 + h.filter((r) => !r.reverted).length, order: lensOrder(), lens: read(PATHS.lens), history: h }; };
