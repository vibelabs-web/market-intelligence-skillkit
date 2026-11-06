---
name: mi-review
description: 쓴 사람과 분리된 눈으로 보고서를 루브릭에 따라 채점한다. 보고서가 나온 뒤 평가할 때, 또는 사람의 채점과 비교할 때 쓴다.
argument-hint: "[run-id] [역할]"
context: fork
---

# 독립 평가

새 컨텍스트에서 일한다. 보고서를 쓰는 과정의 대화를 근거로 삼지 않는다.

## 입력
`runs/<run-id>/brief-<역할>.md` · `project/rubric.md` · `project/brief.md` · `project/fact-pack/evidence-register.csv` · `my/lens.md`.

## 절차
1. 근거 ID 를 실제 행과 대조해 G1~G6 을 판정한다. 대조하지 않은 관문은 PASS 라고 쓰지 않는다.
2. 영역별 단계(0~4)를 매기고, **근거가 된 문장을 그대로** 옮긴다.
3. 최종 질문에 답한다. 칭찬으로 시작하지 않고 고객에게 못 보낼 이유부터 쓴다.

## 출력
`runs/<run-id>/review-<역할>.md` 와, 같은 내용을 `runs/<run-id>/review-<역할>.csv`(머리글 `criterion,verdict,level,quote,reason`)로 남긴다. verdict 는 관문이면 PASS · FAIL, 영역이면 빈칸.

## 완료 조건
FAIL · 낮은 단계마다 문장과 이유가 있다.

## 실패하면
보고서나 근거가 없으면 채점하지 않고 없는 파일을 말한다.

## 권한
보고서를 고치지 않는다. 이 판정은 보조 자료이며 최종 승인은 사람이 한다.
