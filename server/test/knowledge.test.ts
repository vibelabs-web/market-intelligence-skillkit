import { describe, it, expect, beforeEach } from "vitest";
import { mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { Knowledge, readOnlyQuery } from "../src/db/knowledge.ts";

let dir: string, k: Knowledge;
const claim = (over: object = {}) => ({ key: "a", claim: "베트남은 전동기에 에너지 라벨을 의무화했다", quote: "Electric motors shall bear energy labels", source_url: "https://moit.gov.vn/x", source_title: "통상산업부 고시", domain: "regulation", region: "VN", status: "confirmed", ...over });
beforeEach(() => {
  dir = mkdtempSync(path.join(tmpdir(), "mi-kb-"));
  k = new Knowledge(path.join(dir, "mi.db"));
  k.saveProject({ id: "p1", title: "첫 프로젝트", question: "베트남 진출" });
  k.saveProject({ id: "p2", title: "둘째 프로젝트", question: "베트남 전동기 인증" });
});

describe("지식 DB", () => {
  it("자료를 쌓고 개념 · 프로젝트에 잇는다", () => {
    const r = k.ingest("p1", [claim()], [{ name: "베트남 전동기 라벨 제도", summary: "의무화됐다", claims: ["a"] }]);
    expect(r).toEqual({ new: 1, reused: 0, skipped: 0, concepts: 1 });
    expect(k.projectClaims("p1")[0].local_id).toBe("E-001");
    const c = k.concepts()[0];
    expect(k.concept(c.id)!.claimRows.length).toBe(1);
  });
  it("같은 URL · 인용은 한 번만 저장하고 다른 프로젝트에서 재사용으로 센다", () => {
    k.ingest("p1", [claim()], []);
    const r = k.ingest("p2", [claim({ key: "b" })], []);
    expect(r).toMatchObject({ new: 0, reused: 1 });
    expect(k.stats().claims).toBe(1);
    expect(k.projectClaims("p2")[0].reused).toBe(1);
  });
  it("K-id 로 재사용을 표시할 수 있다", () => {
    k.ingest("p1", [claim()], []);
    const kid = k.claims()[0].id;
    expect(k.ingest("p2", [{ knowledge_id: kid } as any], [])).toMatchObject({ reused: 1 });
  });
  it("출처나 인용이 없는 자료는 받지 않는다", () => {
    expect(k.ingest("p1", [claim({ quote: "" })], []).skipped).toBe(1);
  });
  it("검색으로 다음 리서치에 넘길 자료를 찾는다", () => {
    k.ingest("p1", [claim()], [{ name: "베트남 전동기 라벨 제도", summary: "의무화", claims: ["a"] }]);
    expect(k.search("베트남 전동기 인증 일정").length).toBe(1);
    expect(k.searchConcepts("전동기 라벨").length).toBe(1);
  });
  it("프로젝트별 · 전체 조회가 모두 된다", () => {
    k.ingest("p1", [claim()], []);
    k.ingest("p2", [claim({ key: "z", quote: "Thailand requires TISI", source_url: "https://tisi.go.th/y" })], []);
    expect(k.claims().length).toBe(2);
    expect(k.claims({ project: "p1" }).length).toBe(1);
    expect(k.projects().find((p: any) => p.id === "p2")!.claims).toBe(1);
  });
  it("엇갈리는 자료와 근거 표 내보내기", () => {
    k.ingest("p1", [claim(), claim({ key: "b", quote: "labels are voluntary", conflict_with: ["a"] })], []);
    const f = path.join(dir, "reg.csv");
    expect(k.exportRegister("p1", f)).toBe(2);
    const text = readFileSync(f, "utf8");
    expect(text.split("\n")[0]).toContain("evidence_id");
    expect(text).toContain("E-002");
    expect(text).toMatch(/E-001.*E-002|E-002.*E-001/s);
  });
  it("조회기 SQL 은 읽기 전용이다", () => {
    k.ingest("p1", [claim()], []);
    expect(readOnlyQuery(k.file, "SELECT id FROM claims").rows.length).toBe(1);
    expect(() => readOnlyQuery(k.file, "DELETE FROM claims")).toThrow();
    expect(() => readOnlyQuery(k.file, "SELECT 1; DELETE FROM claims")).toThrow();
  });
});
