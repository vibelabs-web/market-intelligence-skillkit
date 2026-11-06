---
name: mi-review
description: 쓴 과정과 분리된 새 컨텍스트에서 브리핑을 평가 기준으로 찢어 본다. 평가관이 보기 전 사전 점검이나 사람 판정과 비교할 때 쓴다.
argument-hint: "[실행 이름]"
context: fork
---

# 독립 평가

## 입력
`runs/<실행>/brief.md` · `selection.csv` · `run.json` · 해당 `project/people/<id>.md` · `project/rubric.md` · `project/fact-pack/evidence-register.csv`.

## 절차
1. 근거 ID 를 실제 행과 대조한다. 대조하지 않은 것을 맞다고 쓰지 않는다.
2. 층별로 PASS · FAIL 과 그 근거 문장을 적는다. 칭찬으로 시작하지 않는다.
3. 최종 질문에 답하고 못 보낼 이유를 큰 순서로 쓴다.

## 출력
`runs/<실행>/review.md`

## 권한
결과물을 고치지 않는다. 이 평가는 보조 자료이고 판정은 사람이 한다.
