---
name: mi-golden
description: 평가관이 저장한 골든을 개발자가 재현 시험할 수 있는 판정 항목으로 바꾼다. 검토 화면에서 골든을 저장한 뒤 쓴다.
argument-hint: "[골든 이름]"
---

# 골든을 시험 항목으로

## 입력
`golden/<이름>/` 의 `golden.json` · `selection.csv` · `brief.md` · `feedback-history.jsonl`. 없으면 멈춘다.

## 절차
피드백과 결과에서 **재현을 판단할 항목**을 뽑아 분류한다.
- `contains` · `not_contains` — 반드시 있어야 / 없어야 하는 표현이나 값. 표현이 달라도 되면 쓰지 않는다.
- `llm` — 읽고 판단해야 하는 것(예: 결론의 방향, 권한 안의 행동).
- 평가관이 말하지 않은 기준을 만들지 않는다. 각 항목에 근거 피드백 id 또는 판정 이유를 적는다.

## 출력
`golden/<이름>/assertions.jsonl` — 줄마다 `{"id","kind","value","source"}`.

## 권한
골든의 다른 파일을 고치지 않는다.
