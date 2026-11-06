---
name: mi-review
description: 쓴 과정과 분리된 새 컨텍스트에서 브리핑을 평가 기준으로 찢어 본다. 평가관이 보기 전 사전 점검이나 사람 판정과 비교할 때 쓴다.
argument-hint: "[실행 이름]"
context: fork
---

# 독립 평가

## 입력
`runs/<실행>/brief.md` · `decision.md` · `selection.csv` · `run.json` · 해당 `project/people/<id>.md` · `project/brief.md` · `project/rubric.md` · `my/lens.md` · `project/fact-pack/evidence-register.csv` · `project/fact-pack/internal-data.csv`.

## 절차
1. 근거 ID 를 실제 행과 대조한다. 대조하지 않은 것을 맞다고 쓰지 않는다.
2. 브리핑의 결론이 `decision.md` 의 결론과 같은지, 판단표가 `my/lens.md` 의 순서를 따랐는지 본다. 판단이 틀렸다면 표의 어느 칸이 틀렸는지 짚는다.
2-1. 층별로 PASS · FAIL 과 그 근거 문장을 적는다. 칭찬으로 시작하지 않는다.
3. 근거 묶음과 프로필 · 브리프에 있는 사실을 없다고 지적하지 않는다. 지적 전에 입력 파일에서 찾아본다.
4. 최종 질문에 답한다 — 이 시스템을 고객에게 납품해도 되는가. 안 된다면 이유를 큰 순서로 쓴다.

## 출력
`runs/<실행>/review.md`

또한 평가관이 먼저 볼 제안을 `runs/<실행>/suggestions.jsonl` 에 줄마다 `{"id","file","quote","comment","kind","who","severity"}` 로 쓴다. id 는 `s1` 같은 문자열, file 은 `brief.md` 처럼 파일 이름만 쓴다. quote 는 결과물의 문장을 글자 그대로 옮긴다. kind 는 fix · remove · missing. who 는 그 지적을 하는 관점(받는 사람 · 깐깐한 파트너 · 사실 검사). severity 는 `치명`(결론이나 행동을 틀리게 만들어 고객에게 보낼 수 없음) · `중요`(보내기 전에 고쳐야 함) · `사소`(취향 · 다듬기). **납품을 막는 것만 쓴다.** 치명과 중요가 없으면 지적을 만들지 말고 빈 파일로 둔다 — 건수를 채우지 않는다. 사소는 쓰지 않는다. 5건 이내, 가장 심각한 순서로. 칭찬은 쓰지 않는다.

## 권한
결과물을 고치지 않는다. 이 평가는 보조 자료이고 판정은 사람이 한다.
