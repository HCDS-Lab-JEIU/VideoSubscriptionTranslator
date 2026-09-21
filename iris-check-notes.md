# classifier 전사 확인

확인 범위: 원본 영상의 **00:29:49–00:30:19**. 발음 자체를 평가한 것이 아니라 원음의 재전사 결과와 강의 화면을 대조했습니다.

- [강의 화면](iris-check-slide.png)에는 `petal length (cm) <= 2.45`와 `petal width (cm) <= 1.65`가 표시됩니다.
- 기존 전체 전사에서는 이 구간에 `배틀링스의 width가 1.75보다 작은 날에 비교를 해서`가 반복되었습니다.
- 같은 원음을 30초로 잘라 다시 요청하니 분류 기준과 decision tree 설명으로 바뀌었습니다. `배틀링스`는 이 구간에서 `petal length` 등의 용어를 잘못 인식한 것으로 판단할 근거가 있습니다.
- 수정한 Iris 힌트로는 `petal length`, `petal width`, `setosa`, `decision tree`, `Iris` 표기가 나왔습니다. 다만 `2.45`가 `1.45`로 인식된 응답도 있습니다. 용어 힌트만으로 정확성을 보장할 수 없습니다.
- 이 구간은 petal 특성을 설명하므로 sepal 발음의 정확성이나 오류 원인은 별도로 확인되지 않았습니다. 발음 문제만으로 단정하지 않습니다.

실제 반복 응답을 새 자동 복구 경로에 입력해 30초 원음을 재전사했고, 4개 구간의 TXT를 생성하며 정상 종료했습니다. 기존 전체 영상과 번역 결과는 변경하지 않았습니다.

검토 파일:

- [기존 힌트 / 수정한 Iris 힌트 / 다른 모델의 비교](output_runs/iris-term-check-kkvvjdd6/comparison.json)
- [실제 자동 복구 결과](output_runs/iris-recovery-validation/transcripts/sample.txt)
- [복구 기록](output_runs/iris-recovery-validation/transcripts/sample.recovery.json)

샘플 결과의 시간은 잘라낸 음성 기준입니다. 원본 영상 시각은 **29분 49초를 더해서** 확인합니다. `recovered`는 반복·형식 검사를 통과했다는 뜻이며 숫자와 의미까지 검증했다는 뜻이 아닙니다.

전사 프롬프트에 관련 용어를 제공하는 방식은 [OpenAI 공식 전사 가이드](https://developers.openai.com/api/docs/guides/speech-to-text#improving-reliability)를 참고했습니다. 이 프로젝트에서는 힌트 자체가 반복되는 실제 응답도 확인했으므로, 복구의 두 번째 시도에서는 힌트를 비웁니다.
