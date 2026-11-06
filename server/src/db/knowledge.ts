/**
 * 지식 DB (SQLite) — 리서치 자료를 쌓고 개념(위키 페이지)으로 묶어 다시 쓴다.
 *   sources   열어 본 페이지(URL 하나에 한 줄)
 *   claims    출처에서 확인한 사실 한 줄 + 원문 인용 (K-000001)
 *   concepts  여러 자료를 묶은 위키 페이지 (C-0001). 리서치마다 요약을 고쳐 쓴다
 *   project_claims  어느 프로젝트가 어떤 자료를 썼나 (프로젝트 안 번호 E-001)
 *   research_runs   리서치 기록(검색어 · 연 페이지 · 새 자료 · 재사용 · 비용)
 * 쓰기는 이 모듈 함수로만 한다. 조회기의 SQL 은 읽기 전용 연결로 돈다.
 */
import { DatabaseSync } from "node:sqlite";
import { createHash } from "node:crypto";
import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";

const SCHEMA = `
CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY, title TEXT, question TEXT, context TEXT, people TEXT, scope TEXT, numbers TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS sources(id TEXT PRIMARY KEY, url TEXT UNIQUE, title TEXT, publisher TEXT, source_type TEXT, published_at TEXT, first_seen TEXT, last_checked TEXT);
CREATE TABLE IF NOT EXISTS claims(id TEXT PRIMARY KEY, source_id TEXT, claim TEXT, quote TEXT, domain TEXT, region TEXT, data_period TEXT,
  status TEXT, confidence TEXT, limitations TEXT, fingerprint TEXT UNIQUE, created_at TEXT, last_checked TEXT);
CREATE TABLE IF NOT EXISTS concepts(id TEXT PRIMARY KEY, name TEXT UNIQUE, summary TEXT, updated_at TEXT, updated_by_project TEXT);
CREATE TABLE IF NOT EXISTS claim_concepts(claim_id TEXT, concept_id TEXT, PRIMARY KEY(claim_id, concept_id));
CREATE TABLE IF NOT EXISTS conflicts(a TEXT, b TEXT, note TEXT, PRIMARY KEY(a, b));
CREATE TABLE IF NOT EXISTS project_claims(project_id TEXT, claim_id TEXT, local_id TEXT, reused INTEGER, added_at TEXT, PRIMARY KEY(project_id, claim_id));
CREATE TABLE IF NOT EXISTS research_runs(id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT, started_at TEXT, finished_at TEXT,
  new_claims INTEGER, reused_claims INTEGER, concepts INTEGER, cost_usd REAL, searches TEXT, opened TEXT, gaps TEXT);
CREATE VIRTUAL TABLE IF NOT EXISTS claims_fts USING fts5(claim_id UNINDEXED, text, tokenize='unicode61');
CREATE VIRTUAL TABLE IF NOT EXISTS concepts_fts USING fts5(concept_id UNINDEXED, text, tokenize='unicode61');
`;

export const REGISTER_FIELDS = ["evidence_id", "domain", "country", "claim", "quote", "source_title", "source_url", "publisher", "published_at", "data_period",
  "retrieved_at", "source_type", "status", "confidence", "limitations", "conflict_with", "synthetic", "knowledge_id", "reused"] as const;

export interface ClaimIn {
  key?: string; knowledge_id?: string; claim: string; quote: string; source_url: string; source_title?: string; publisher?: string;
  published_at?: string; source_type?: string; domain?: string; region?: string; data_period?: string; status?: string; confidence?: string;
  limitations?: string; conflict_with?: string[];
}
export interface ConceptIn { name: string; summary: string; claims: string[] }
export interface ProjectIn { id: string; title: string; question: string; context?: string; people?: string; scope?: string; numbers?: string; created_at?: string }
type Row = Record<string, any>;

const now = () => new Date().toISOString();
const STOP = new Set(["어디", "무엇", "어떻게", "어디에", "중에", "있는가", "할까", "어디로", "그리고"]);
export const fingerprint = (url: string, quote: string) =>
  createHash("sha256").update(`${url.trim().toLowerCase()}|${quote.replace(/\s+/g, " ").trim().toLowerCase()}`).digest("hex").slice(0, 24);

export class Knowledge {
  readonly db: DatabaseSync;
  constructor(readonly file: string) {
    mkdirSync(path.dirname(file), { recursive: true });
    this.db = new DatabaseSync(file);
    this.db.exec(SCHEMA);
  }
  close() { this.db.close(); }

  private one<T = Row>(sql: string, ...p: any[]): T | undefined { return this.db.prepare(sql).get(...p) as T | undefined; }
  private all<T = Row>(sql: string, ...p: any[]): T[] { return this.db.prepare(sql).all(...p) as T[]; }
  private run(sql: string, ...p: any[]) { return this.db.prepare(sql).run(...p); }
  private nextId(table: string, prefix: string, width: number) {
    let n = (this.one<{ c: number }>(`SELECT COUNT(*) c FROM ${table}`)!.c) + 1;
    const id = () => `${prefix}${String(n).padStart(width, "0")}`;
    while (this.one(`SELECT 1 FROM ${table} WHERE id=?`, id())) n++;
    return id();
  }

  saveProject(p: ProjectIn) {
    this.run(`INSERT INTO projects(id,title,question,context,people,scope,numbers,created_at) VALUES(?,?,?,?,?,?,?,?)
      ON CONFLICT(id) DO UPDATE SET title=excluded.title,question=excluded.question,context=excluded.context,people=excluded.people,scope=excluded.scope,numbers=excluded.numbers`,
      p.id, p.title, p.question, p.context ?? "", p.people ?? "", p.scope ?? "", p.numbers ?? "", p.created_at ?? now());
  }
  project(id: string) { return this.one("SELECT * FROM projects WHERE id=?", id); }
  projects() {
    return this.all(`SELECT p.*, (SELECT COUNT(*) FROM project_claims pc WHERE pc.project_id=p.id) AS claims,
      (SELECT MAX(finished_at) FROM research_runs r WHERE r.project_id=p.id) AS researched_at FROM projects p ORDER BY created_at DESC`);
  }

  private matchQuery(text: string) {
    const words = [...new Set((text.match(/[\p{L}\p{N}]{2,}/gu) ?? []).filter((w) => !STOP.has(w)))].slice(0, 14);
    return words.length ? words.map((w) => `"${w.replace(/"/g, "")}"*`).join(" OR ") : null;      // 한국어는 조사가 붙으므로 앞부분 일치
  }
  /** 질문과 겹치는 자료 — 리서치 전에 «이미 아는 것»으로 넘긴다 */
  search(text: string, limit = 40): Row[] {
    const q = this.matchQuery(text);
    if (!q) return [];
    return this.all(`SELECT c.*, s.url, s.title AS source_title, s.publisher, s.published_at, s.source_type FROM claims_fts f
      JOIN claims c ON c.id=f.claim_id LEFT JOIN sources s ON s.id=c.source_id WHERE claims_fts MATCH ? ORDER BY bm25(claims_fts) LIMIT ?`, q, limit);
  }
  searchConcepts(text: string, limit = 15): Row[] {
    const q = this.matchQuery(text);
    if (!q) return [];
    return this.all(`SELECT k.* FROM concepts_fts f JOIN concepts k ON k.id=f.concept_id WHERE concepts_fts MATCH ? ORDER BY bm25(concepts_fts) LIMIT ?`, q, limit);
  }

  /** 리서치 결과를 쌓는다. 같은 URL · 같은 인용은 한 번만 저장하고 확인 날짜만 고친다 */
  ingest(projectId: string, claims: ClaimIn[], concepts: ConceptIn[], meta: { costUsd?: number; searches?: string[]; opened?: string[]; gaps?: string[] } = {}) {
    const t = now();
    const keymap = new Map<string, string>();
    let fresh = 0, reused = 0, skipped = 0;
    this.db.exec("BEGIN");
    try {
      for (const c of claims) {
        let kid = (c.knowledge_id ?? "").trim();
        let wasReuse = false;
        if (kid && this.one("SELECT 1 FROM claims WHERE id=?", kid)) {
          this.run("UPDATE claims SET last_checked=? WHERE id=?", t, kid);
          wasReuse = true;
        } else {
          const url = (c.source_url ?? "").trim();
          if (!url || !(c.quote ?? "").trim()) { skipped++; continue; }      // 출처 · 원문 인용이 없으면 자료로 받지 않는다
          let src = this.one<{ id: string }>("SELECT id FROM sources WHERE url=?", url);
          if (src) this.run("UPDATE sources SET last_checked=? WHERE id=?", t, src.id);
          else {
            src = { id: this.nextId("sources", "SRC-", 5) };
            this.run("INSERT INTO sources VALUES(?,?,?,?,?,?,?,?)", src.id, url, c.source_title ?? "", c.publisher ?? "", c.source_type ?? "", c.published_at ?? "", t, t);
          }
          const fp = fingerprint(url, c.quote);
          const old = this.one<{ id: string }>("SELECT id FROM claims WHERE fingerprint=?", fp);
          if (old) {
            kid = old.id;
            this.run("UPDATE claims SET last_checked=?, status=?, limitations=? WHERE id=?", t, c.status ?? "confirmed", c.limitations ?? "", kid);
            wasReuse = true;
          } else {
            kid = this.nextId("claims", "K-", 6);
            this.run("INSERT INTO claims VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", kid, src.id, c.claim, c.quote, c.domain ?? "", c.region ?? "", c.data_period ?? "",
              c.status ?? "confirmed", c.confidence ?? "", c.limitations ?? "", fp, t, t);
            this.run("INSERT INTO claims_fts VALUES(?,?)", kid, `${c.claim} ${c.quote} ${c.domain ?? ""} ${c.region ?? ""}`);
            fresh++;
          }
        }
        if (wasReuse) reused++;
        if (c.key) keymap.set(String(c.key), kid);
        keymap.set(kid, kid);
        if (!this.one("SELECT 1 FROM project_claims WHERE project_id=? AND claim_id=?", projectId, kid)) {
          const n = this.one<{ c: number }>("SELECT COUNT(*) c FROM project_claims WHERE project_id=?", projectId)!.c + 1;
          this.run("INSERT INTO project_claims VALUES(?,?,?,?,?)", projectId, kid, `E-${String(n).padStart(3, "0")}`, wasReuse ? 1 : 0, t);
        }
      }
      for (const c of claims) {
        const a = keymap.get(String(c.key ?? c.knowledge_id ?? ""));
        for (const o of c.conflict_with ?? []) {
          const b = keymap.get(String(o));
          if (a && b && a !== b) this.run("INSERT OR IGNORE INTO conflicts VALUES(?,?,?)", a < b ? a : b, a < b ? b : a, "");
        }
      }
      let conceptCount = 0;
      for (const k of concepts) {
        const name = (k.name ?? "").trim();
        if (!name) continue;
        conceptCount++;
        const row = this.one<{ id: string }>("SELECT id FROM concepts WHERE name=?", name);
        const cid = row?.id ?? this.nextId("concepts", "C-", 4);
        if (row) {
          this.run("UPDATE concepts SET summary=?, updated_at=?, updated_by_project=? WHERE id=?", k.summary, t, projectId, cid);
          this.run("DELETE FROM concepts_fts WHERE concept_id=?", cid);
        } else this.run("INSERT INTO concepts VALUES(?,?,?,?,?)", cid, name, k.summary, t, projectId);
        this.run("INSERT INTO concepts_fts VALUES(?,?)", cid, `${name} ${k.summary}`);
        for (const ref of k.claims ?? []) {
          const kid = keymap.get(String(ref));
          if (kid) this.run("INSERT OR IGNORE INTO claim_concepts VALUES(?,?)", kid, cid);
        }
      }
      this.run("INSERT INTO research_runs(project_id,started_at,finished_at,new_claims,reused_claims,concepts,cost_usd,searches,opened,gaps) VALUES(?,?,?,?,?,?,?,?,?,?)",
        projectId, t, t, fresh, reused, conceptCount, meta.costUsd ?? 0, JSON.stringify(meta.searches ?? []), JSON.stringify(meta.opened ?? []), JSON.stringify(meta.gaps ?? []));
      this.db.exec("COMMIT");
      return { new: fresh, reused, skipped, concepts: conceptCount };
    } catch (e) {
      this.db.exec("ROLLBACK");
      throw e;
    }
  }

  projectClaims(projectId: string): Row[] {
    return this.all(`SELECT pc.local_id, pc.reused, c.*, s.url, s.title AS source_title, s.publisher, s.published_at, s.source_type
      FROM project_claims pc JOIN claims c ON c.id=pc.claim_id LEFT JOIN sources s ON s.id=c.source_id WHERE pc.project_id=? ORDER BY pc.local_id`, projectId);
  }
  /** 프로젝트가 쓰는 자료를 브리핑이 읽는 근거 표로 내보낸다. 이 파일이 그 시점의 스냅샷이다 */
  exportRegister(projectId: string, file: string) {
    const rows = this.projectClaims(projectId);
    const local = new Map(rows.map((r) => [r.id, r.local_id]));
    const esc = (v: unknown) => { const s = String(v ?? ""); return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
    const lines = [REGISTER_FIELDS.join(",")];
    for (const r of rows) {
      const conf = this.all<{ a: string; b: string }>("SELECT a,b FROM conflicts WHERE a=? OR b=?", r.id, r.id)
        .map((x) => (x.a === r.id ? x.b : x.a)).filter((x) => local.has(x)).map((x) => local.get(x));
      const rec: Record<string, unknown> = { evidence_id: r.local_id, domain: r.domain, country: r.region, claim: r.claim, quote: r.quote, source_title: r.source_title,
        source_url: r.url, publisher: r.publisher, published_at: r.published_at, data_period: r.data_period, retrieved_at: String(r.last_checked ?? "").slice(0, 10),
        source_type: r.source_type, status: r.status, confidence: r.confidence, limitations: r.limitations, conflict_with: conf.join(";"), synthetic: "false",
        knowledge_id: r.id, reused: r.reused ? "true" : "false" };
      lines.push(REGISTER_FIELDS.map((f) => esc(rec[f])).join(","));
    }
    mkdirSync(path.dirname(file), { recursive: true });
    writeFileSync(file, lines.join("\n") + "\n", "utf8");
    return rows.length;
  }

  // ── 조회기 ──
  stats() {
    const c = (t: string) => this.one<{ c: number }>(`SELECT COUNT(*) c FROM ${t}`)!.c;
    return { projects: c("projects"), sources: c("sources"), claims: c("claims"), concepts: c("concepts"), links: c("project_claims"), runs: c("research_runs") };
  }
  concepts(q = ""): Row[] {
    const base = `SELECT k.*, (SELECT COUNT(*) FROM claim_concepts cc WHERE cc.concept_id=k.id) AS claims FROM concepts k`;
    if (!q.trim()) return this.all(`${base} ORDER BY updated_at DESC LIMIT 300`);
    const ids = this.searchConcepts(q, 100).map((r) => r.id);
    return ids.length ? this.all(`${base} WHERE k.id IN (${ids.map(() => "?").join(",")})`, ...ids) : [];
  }
  concept(id: string) {
    const k = this.one("SELECT * FROM concepts WHERE id=?", id);
    if (!k) return null;
    const claims = this.all(`SELECT c.*, s.url, s.title AS source_title, s.publisher FROM claim_concepts cc JOIN claims c ON c.id=cc.claim_id
      LEFT JOIN sources s ON s.id=c.source_id WHERE cc.concept_id=? ORDER BY c.last_checked DESC`, id);
    const projects = this.all(`SELECT DISTINCT p.id, p.title FROM claim_concepts cc JOIN project_claims pc ON pc.claim_id=cc.claim_id JOIN projects p ON p.id=pc.project_id WHERE cc.concept_id=?`, id);
    return { ...k, claimRows: claims, projects };
  }
  claims(opts: { q?: string; project?: string; limit?: number } = {}): Row[] {
    const lim = Math.min(opts.limit ?? 300, 1000);
    let ids: string[] | null = null;
    if (opts.q?.trim()) ids = this.search(opts.q, lim).map((r) => r.id);
    const where: string[] = [], p: any[] = [];
    if (ids) { if (!ids.length) return []; where.push(`c.id IN (${ids.map(() => "?").join(",")})`); p.push(...ids); }
    if (opts.project) { where.push("c.id IN (SELECT claim_id FROM project_claims WHERE project_id=?)"); p.push(opts.project); }
    return this.all(`SELECT c.*, s.url, s.title AS source_title, s.publisher,
      (SELECT GROUP_CONCAT(pc.project_id) FROM project_claims pc WHERE pc.claim_id=c.id) AS project_ids,
      (SELECT GROUP_CONCAT(k.name, ' · ') FROM claim_concepts cc JOIN concepts k ON k.id=cc.concept_id WHERE cc.claim_id=c.id) AS concept_names
      FROM claims c LEFT JOIN sources s ON s.id=c.source_id ${where.length ? "WHERE " + where.join(" AND ") : ""} ORDER BY c.last_checked DESC LIMIT ?`, ...p, lim);
  }
  sources(): Row[] {
    return this.all(`SELECT s.*, (SELECT COUNT(*) FROM claims c WHERE c.source_id=s.id) AS claims FROM sources s ORDER BY last_checked DESC LIMIT 1000`);
  }
  runs(projectId?: string): Row[] {
    return projectId ? this.all("SELECT * FROM research_runs WHERE project_id=? ORDER BY id DESC", projectId) : this.all("SELECT * FROM research_runs ORDER BY id DESC LIMIT 200");
  }
}

/** 조회기의 SQL 칸. 읽기 전용으로 열어 쓰기 문장은 실패한다 */
export function readOnlyQuery(file: string, sql: string, limit = 500) {
  const s = sql.trim().replace(/;\s*$/, "");
  if (!/^(select|with)\b/i.test(s) || s.includes(";")) throw new Error("SELECT 문 하나만 실행할 수 있습니다");
  const db = new DatabaseSync(file, { readOnly: true });
  try {
    const stmt = db.prepare(s);
    const rows = stmt.all() as Row[];
    const columns = rows.length ? Object.keys(rows[0]) : stmt.columns().map((c: any) => c.name);
    return { columns, rows: rows.slice(0, limit).map((r) => columns.map((c) => r[c])), truncated: rows.length > limit };
  } finally {
    db.close();
  }
}
