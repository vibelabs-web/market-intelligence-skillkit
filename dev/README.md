# 개발자 과제 — 골든을 재현하는 에이전트

컨설턴트가 만족한 결과가 골든입니다. 같은 입력으로 **골든과 같은 판단을 내는 에이전트**를 직접 만듭니다. 스택은 자유입니다.

## 규칙
- 입력: `project/people/<id>.md` · `project/fact-pack/evidence-register.csv`
- 출력: `selection.csv`(`evidence_id,send,why`) · `brief.md`
- **에이전트가 골든과 이전 결과를 읽으면 실격입니다.** 깨끗한 폴더에서 돌립니다. 같은 폴더에 답이 있으면 점수가 부풀려집니다(자체 시험에서 18~23/24 가 24/24 로 올라갔습니다).
- 채점: `python3 tools/golden_compare.py golden/<이름> 결과1 결과2 결과3`

## «같다»의 뜻
문장 일치가 아닙니다. 선별 · 사실 · 판정 항목 · 반복 안정성을 봅니다.
