---
name: mi-golden
description: 컨설턴트가 승인한 골든(판단 기준의 스냅샷)을 개발자가 재현 시험할 수 있는 판정 항목으로 바꾼다. 검토 화면에서 골든을 남긴 뒤 쓴다.
argument-hint: "[골든 폴더 이름]"
---

# 골든을 시험 항목으로

골든은 정답지가 아니다. 한 컨설턴트가 특정 고객 · 받는 사람 · 시점 · 근거에서 **승인한 판단 기준의 기록**이다. 같은 사람 · 사례에 여러 버전이 있고 `golden.json` 의 `status`(active · superseded · retired)로 구분한다. 화면이 저장할 때 승인 이유 · 기준 버전(`lens_sha`) · 근거 스냅샷(`fact-pack/`) · 객관 검사(`objective-checks.json`) · 비교 메모를 함께 동결한다.

## 입력
`golden/<이름>/` 의 `golden.json` · `brief.md` · `decision.md` · `selection.csv` · `lens.md` · `feedback-history.jsonl` · `comparison-notes.md`. 없으면 멈춘다.

## 절차
피드백 · 판단표 · 승인 이유에서 **재현을 판단할 항목**을 뽑고 층을 붙인다.
- `layer: objective` — 누가 봐도 틀린 것(권한 밖 행동, 확정처럼 쓴 미확정 정책, 계산). `contains` · `not_contains` 또는 `llm`.
- `layer: alignment` — 이 컨설턴트의 선별 · 판단 순서를 따랐는가. 주로 `llm`.
- `layer: review` — 결론 방향처럼 다른 답도 합리적일 수 있는 것. 어긋나면 실패가 아니라 «차이 검토».
- 평가관이 말하지 않은 기준을 만들지 않는다. 각 항목에 근거 피드백 id 또는 승인 이유를 적는다.

## 출력
`golden/<이름>/assertions.jsonl` — 줄마다 `{"id","kind","value","layer","source"}`.

## 권한
골든의 다른 파일을 고치지 않는다. 이전 버전을 지우지 않는다.
