import { describe, it, expect } from "vitest";
import { check, lengthIssue, parseCsv } from "../src/checks/briefCheck.ts";

const ROWS = { "E-001": { quote: "imports reached 1,234 million in 2024", claim: "수입 1,234", status: "confirmed" }, "E-002": { quote: "the draft rule is under review", claim: "초안", status: "proposed" } };
const gates = (t: string, syn: string[] = [], allowed: string[] = []) => [...new Set(check(t, ROWS, new Set(syn), new Set(allowed)).map((i) => i.gate))].sort();

describe("브리핑 코드 검사 (Python 판과 같은 사례)", () => {
  it.each([
    ["수입은 1,234 입니다 [E-001].", []],
    ["수입이 늘었습니다 [E-099].", ["G1"]],
    ["시장은 500 규모입니다.", ["G1"]],
    ["수입은 9,999 입니다 [E-001].", ["G3"]],
    ["이 규제는 시행 중입니다 [E-002].", ["G2"]],
    ["이 규제는 초안이며 시행 중인지 확인 필요합니다 [E-002].", []],
    ["수입은 123 입니다 [E-001].", ["G3"]],
    ["수입은 9,999 입니다(2 × 2 = 4) [E-001].", ["G3"]],
    ["내부 자료 기준 수입은 9,999 입니다 [E-001].", ["G3"]],
    ["프리미엄은 756,000 입니다(420 × 180 = 756,000) [E-001].", ["G4"]],
    ["프리미엄은 75,600 입니다(420 × 180 = 75,600) [E-001].", []],
    ["건당 96만 입니다(2.6억 ÷ 27 ≈ 96만) [E-001].", ["G4"]],
    ["매출은 620억 × 22% = 136.4억 입니다 [E-001].", []],
    ["이 규제가 확정되면 줄입니다 [E-002].", []],
    ["10주 공백(16 − 6)이 남습니다 [E-001].", []],
    ["99주 공백(16 − 6)이 남습니다 [E-001].", ["G3"]],
    ["협상은 12/1 에 시작합니다.", []],
    ["수입은 1,234 입니다. 그래서 줄입니다 [E-001].", []],
    ["후보 2개를 고른다.", []],
    ["11월 10일까지 확인하고 90일 안에 끝냅니다.", []],
    ["11월 10일 기준 시장은 500 규모입니다.", ["G1"]],
    ["차이는 (1,234 − 234) = 1,000 입니다 [E-001].", []],
  ])("%s", (text, want) => { expect(gates(text as string)).toEqual(want); });
  it("프로필 숫자는 근거 없이 써도 된다", () => { expect(gates("승인 한도는 50억 입니다.", [], ["50"])).toEqual([]); });
  it("분량", () => {
    expect(lengthIssue("가".repeat(500), "- **형식:** 1분 안에 읽는다.")).not.toBeNull();
    expect(lengthIssue("가".repeat(400), "- **형식:** 1분 안에 읽는다.")).toBeNull();
    expect(lengthIssue("가".repeat(9000), "- **형식:** 수치와 기한.")).toBeNull();
  });
  it("CSV", () => { expect(parseCsv('a,b\n"x, y","z ""q"""\n')).toEqual([{ a: "x, y", b: 'z "q"' }]); });
});
