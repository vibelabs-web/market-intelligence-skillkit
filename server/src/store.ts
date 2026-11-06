/** 프로젝트 · 실행 · 골든 파일 저장소 (data/ 아래, git 추적 안 함) */
import { mkdirSync, readFileSync, writeFileSync, existsSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import { PATHS } from "./config.ts";

export const readJson = <T>(f: string, fallback: T): T => { try { return JSON.parse(readFileSync(f, "utf8")); } catch { return fallback; } };
export const writeJson = (f: string, v: unknown) => { mkdirSync(path.dirname(f), { recursive: true }); writeFileSync(f, JSON.stringify(v, null, 1), "utf8"); };
export const writeText = (f: string, v: string) => { mkdirSync(path.dirname(f), { recursive: true }); writeFileSync(f, v, "utf8"); };
export const readText = (f: string) => (existsSync(f) ? readFileSync(f, "utf8") : "");
export const safeId = (s: string) => { if (!/^[\w가-힣.\-]+$/.test(s) || s.startsWith(".")) throw new Error(`잘못된 이름: ${s}`); return s; };

export interface Project { id: string; title: string; question: string; context: string; people: string; scope: string; numbers: string; created_at: string }

export const projectDir = (id: string) => path.join(PATHS.projects, safeId(id));
export const projectFiles = (id: string) => {
  const d = projectDir(id);
  return { dir: d, meta: path.join(d, "project.json"), brief: path.join(d, "brief.md"), people: path.join(d, "people"), register: path.join(d, "evidence-register.csv"),
    internal: path.join(d, "internal-data.csv"), notes: path.join(d, "notes.md") };
};
export function newProjectId() {
  const t = new Date(), p = (n: number) => String(n).padStart(2, "0");
  return `p${String(t.getFullYear()).slice(2)}${p(t.getMonth() + 1)}${p(t.getDate())}-${p(t.getHours())}${p(t.getMinutes())}${p(t.getSeconds())}`;
}

const csvCell = (v: unknown) => { const s = String(v ?? ""); return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
/** 컨설턴트가 넣은 «우리 회사 숫자»를 줄마다 I-001 … 로 저장한다. AI 가 만든 수치는 들어가지 않는다 */
export function writeInternal(id: string, numbers: string) {
  const lines = numbers.split("\n").map((l) => l.replace(/^[-*·\s]+/, "").trim()).filter(Boolean);
  const head = "evidence_id,domain,claim,quote,publisher,source_url,status,confidence,limitations,synthetic";
  const body = lines.map((l, i) => [`I-${String(i + 1).padStart(3, "0")}`, "internal", l, l, "컨설턴트 입력", "", "confirmed", "", "컨설턴트가 직접 넣은 회사 수치", "false"].map(csvCell).join(","));
  writeText(projectFiles(id).internal, [head, ...body].join("\n") + "\n");
  return lines.length;
}
export function writeBrief(p: Project) {
  const internal = p.numbers.trim() ? p.numbers.split("\n").filter((l) => l.trim()).map((l, i) => `- [I-${String(i + 1).padStart(3, "0")}] ${l.replace(/^[-*·\s]+/, "")}`).join("\n") : "- 없음. 금액 판단에 필요한 값은 «아직 모르는 것»에 쓴다.";
  writeText(projectFiles(p.id).brief, `# 프로젝트 브리프\n\n## 결정 질문\n${p.question}\n\n## 고객 상황 (컨설턴트 입력)\n${p.context || "적지 않음"}\n\n## 범위\n${p.scope || "적지 않음"}\n\n## 받는 사람 (역할)\n${p.people}\n\n## 우리 회사 숫자 (컨설턴트 입력)\n${internal}\n\n## 기준일\n${new Date().toISOString().slice(0, 10)}\n`);
}
export function people(id: string) {
  const d = projectFiles(id).people;
  if (!existsSync(d)) return [];
  return readdirSync(d).filter((f) => f.endsWith(".md")).sort().map((f) => {
    const text = readFileSync(path.join(d, f), "utf8");
    return { id: f.replace(/\.md$/, ""), title: (text.split("\n")[0] ?? "").replace(/^#\s*/, ""), text };
  });
}
export function listDirs(dir: string) {
  return existsSync(dir) ? readdirSync(dir).filter((n) => statSync(path.join(dir, n)).isDirectory()) : [];
}
