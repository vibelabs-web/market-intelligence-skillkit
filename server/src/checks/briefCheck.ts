/**
 * 브리핑 코드 검사 — tools/check_brief.py 를 옮긴 것 (G1 출처 · G2 상태 · G3 숫자 · G4 계산 · G5 가상 표시 · G6 분량)
 * 하드 게이트(객관 오류): G1~G4. 형식: G5 · G6.
 * 한계: 글자 대조와 정규식이다. 숫자는 맞지만 다른 근거를 인용한 경우 · 논리 비약 · 권한 밖 행동 · 날짜 순서는 못 잡는다.
 */
export interface Issue { gate: string; sentence: string; why: string }
export type Rows = Record<string, { quote?: string; claim?: string; status?: string }>;
export const HARD_GATES = ["G1", "G2", "G3", "G4"];

const ID = /(?:[EI]-\d{3}|SIG-\d{5})/g;
const NUM = /(?<![\w.-])\d[\d,]*(?:\.\d+)?/g;
const FIRM = /시행\s*중|확정(?!되면|되고|돼도|될|되지|이\s*아)|발효|의무화(?:됐|되었)|in force|mandatory/i;
const HEDGE = /초안|검토|추진|예정|미확정|불확실|proposed|draft|가능성|확인\s*필요/;
const SPAN = /\(([^()]*[=×÷≈+−][^()]*)\)|((?:[^().;]|(?<=\d)\.(?=\d))*[=×÷≈](?:[^().;]|(?<=\d)\.(?=\d))*)/g;
const TERM = /(\d[\d,]*(?:\.\d+)?)\s*(천만|억|만|천|%)?/g;
const UNIT: Record<string, number> = { 천만: 1e7, 억: 1e8, 만: 1e4, 천: 1e3, "%": 0.01, "": 1 };
const SYN = /\(?\s*(?:synthetic|내부\s*집계|내부\s*자료)\s*\)?/i;

export function norm(n: string) {
  n = n.replace(/,/g, "").replace(/\.$/, "");
  return n.includes(".") ? n.replace(/0+$/, "").replace(/\.$/, "") : n;
}
const ids = (s: string) => s.match(ID) ?? [];
const nums = (s: string) => s.match(NUM) ?? [];

function formulaSpans(s: string) {
  return [...s.matchAll(SPAN)].map((m) => m[1] ?? m[2]).filter(Boolean) as string[];
}

function badFormula(span: string): string | null {
  if (/[월일주]/.test(span)) return null;
  const m = span.match(/(.+?)\s*[=≈]\s*(.+)/);
  if (!m) return null;
  const [, left, right] = m;
  const terms = [...left.matchAll(TERM)], ops = left.match(/[×÷+]/g) ?? [];
  const ans = [...right.matchAll(TERM)][0];
  if (!ans || !ops.length || terms.length !== ops.length + 1) return null;
  const val = (t: RegExpMatchArray) => parseFloat(t[1].replace(/,/g, "")) * UNIT[t[2] ?? ""];
  let got = val(terms[0]);
  for (let i = 0; i < ops.length; i++) {
    const v = val(terms[i + 1]);
    if (ops[i] === "÷" && !v) return null;
    got = ops[i] === "×" ? got * v : ops[i] === "÷" ? got / v : got + v;
  }
  const want = val(ans);
  return want && Math.abs(got - want) / Math.abs(want) <= 0.02 ? null : `계산이 맞지 않음: ${span.trim()} (계산하면 약 ${Number(got.toPrecision(4)).toLocaleString("en-US")})`;
}

function sentences(text: string): string[] {
  const out: string[] = [];
  let fresh = false;
  for (let line of text.split("\n")) {
    line = line.trim();
    if (!line || line.startsWith("#") || /^[|:\-\s]+$/.test(line)) continue;
    line = line.replace(/^(?:[-*]|\d+[.)])\s+/, "");
    for (let s of line.split(/(?<=[.!?])\s+/)) {
      s = s.trim();
      if (!s) continue;
      if (out.length && fresh && /^(?:\[?(?:E-\d{3}|SIG-\d{5})\]?[\s,.·]*)+$/.test(s)) out[out.length - 1] += " " + s;
      else out.push(s);
      fresh = true;
    }
    fresh = false;
  }
  return out;
}

function bareNumbers(s: string): string[] {
  s = s.replace(ID, " ")
    .replace(/(?<![\d,.])20\d\d(?:[-./]\d{1,2}){0,2}(?!\d)/g, " ")
    .replace(/(?<![\d,.])\d{1,2}\/\d{1,2}(?![\d/])/g, " ")
    .replace(/\d{1,2}월(?:\s*\d{1,2}일)?|\d{1,2}일|\d{1,2}분기/g, " ")
    .replace(/\d{1,3}\s*(?:개월|주|분)\s*(?:안|내|동안|뒤|전)/g, " ")
    .replace(/(?:최근|지난)\s*\d{1,3}\s*(?:개월|주|년)/g, " ")
    .replace(/(?<![\w])1\s*(?:건|대|인|톤|품목)당|(?<![\d,.])1건(?!\s*당)/g, " ")
    .replace(/\d{1,2}\s*(?:개(?!국|월)|가지|단계|품목|차례)/g, " ");
  return nums(s).map(norm);
}

/** allowed: 받는 사람 프로필에 있어 근거 번호 없이 써도 되는 숫자 */
export function check(text: string, rows: Rows, synthetic: Set<string> = new Set(), allowed: Set<string> = new Set()): Issue[] {
  const issues: Issue[] = [];
  const add = (gate: string, sent: string, why: string) => issues.push({ gate, sentence: sent.slice(0, 160), why });
  for (const line of text.replace(/\*\*/g, "").split("\n")) {
    for (const s of sentences(line)) {
      const found = ids(s).length ? ids(s) : ids(line);
      const spans = formulaSpans(s);
      const shown = new Set(spans.flatMap(bareNumbers));
      for (const m of s.matchAll(/(\d[\d,.]*)[^\d()]{0,8}\(\s*(\d[\d,.]*)\D*?−\s*(\d[\d,.]*)\D*\)/g)) {
        if (parseFloat(m[2].replace(/,/g, "")) - parseFloat(m[3].replace(/,/g, "")) === parseFloat(m[1].replace(/,/g, "").replace(/\.$/, ""))) shown.add(norm(m[1]));
      }
      for (const n of [...shown]) shown.add(n.split(".")[0]);
      const ns = bareNumbers(s).filter((n) => !shown.has(n) && !allowed.has(n));
      const isSyn = SYN.test(s) && !found.length;
      for (const x of spans) { const why = badFormula(x); if (why) add("G4", s, why); }
      for (const i of found) if (!rows[i]) add("G1", s, `근거 묶음에 없는 ID ${i}`);
      const known = found.filter((i) => rows[i]).map((i) => rows[i]);
      if (ns.length && !found.length && !isSyn) add("G1", s, `숫자 [${ns.join(", ")}] 에 근거 ID · synthetic 표시가 없음`);
      if (known.length) {
        const hay = new Set(nums(known.map((r) => `${r.quote ?? ""} ${r.claim ?? ""}`).join(" ")).map(norm));
        for (const n of ns) if (!hay.has(n) && !isSyn) add("G3", s, `숫자 ${n} 이 인용한 근거에 없음`);
        if (known.some((r) => r.status === "proposed" || r.status === "uncertain") && FIRM.test(s) && !HEDGE.test(s)) add("G2", s, "검토 · 불확실 근거를 확정처럼 씀");
      }
      if (!isSyn && [...synthetic].some((v) => ns.includes(v))) add("G5", s, "가상 내부 수치에 synthetic 표시가 없음");
    }
  }
  return issues;
}

/** 프로필 «형식» 줄의 분량 · 읽는 시간보다 20% 넘게 길면 알린다 (1분 ≈ 350자) */
export function lengthIssue(text: string, profile: string): Issue | null {
  const line = profile.split("\n").find((l) => l.includes("형식")) ?? "";
  const chars = line.match(/(\d[\d,]*)\s*자/), mins = line.match(/(\d+)\s*분/);
  if (!chars && !mins) return null;
  const limit = chars ? parseInt(chars[1].replace(/,/g, "")) : parseInt(mins![1]) * 350;
  const n = text.replace(ID, "").replace(/[#*|`>[\]]/g, "").replace(/\s+/g, " ").trim().length;
  return n <= limit * 1.2 ? null : { gate: "G6", sentence: `${n}자`, why: `프로필 기준 ${limit}자보다 많이 깁니다 (${n}자)` };
}

/** 근거 표 CSV(evidence-register · internal-data) → Rows */
export function parseCsv(text: string): Record<string, string>[] {
  const rows: string[][] = [];
  let cur: string[] = [], f = "", q = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (q) { if (c === '"' && text[i + 1] === '"') { f += '"'; i++; } else if (c === '"') q = false; else f += c; }
    else if (c === '"') q = true;
    else if (c === ",") { cur.push(f); f = ""; }
    else if (c === "\n") { cur.push(f); rows.push(cur); cur = []; f = ""; }
    else if (c !== "\r") f += c;
  }
  if (f || cur.length) { cur.push(f); rows.push(cur); }
  const [head, ...body] = rows.filter((r) => r.some((x) => x.trim()));
  return head ? body.map((r) => Object.fromEntries(head.map((h, i) => [h, r[i] ?? ""]))) : [];
}
