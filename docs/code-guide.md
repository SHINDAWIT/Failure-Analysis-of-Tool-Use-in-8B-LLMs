# 코드 안내

소스는 제공된 연구 자료의 스냅샷입니다. 기존 Python 파일은 바이트를 유지해 공개했으며 파일별 해시는 [공개 manifest](../publication_manifest.json)에 있습니다. 이번 공개를 위해 추가한 문서·검산 도구와 기존 연구 구현을 구분했습니다.

## 요청부터 결과 저장까지

~~~text
scripts/run_frontloop_when2call.py 또는 run_frontloop_loc.py
  → harness.run_when2call_attempt() / loc_harness.run_loc_attempt()
  → client.LlamaServerClient.chat()
  → JSON 해석·검증 / native XML 해석·검증
  → 행동 채점 / 도구 실행·관찰 추가·종료 판정
  → append_row(): 조건별 실행 원장 저장
  → summarize() 및 별도 집계 스크립트
~~~

## 주요 파일과 함수

| 구성 | 파일·함수 | 확인할 역할 |
| --- | --- | --- |
| 모델 요청 | [client.py](../experiments/monkeys-passk-frontloop/monkeys_passk_frontloop/client.py), LlamaServerClient.chat(), combine_output() | HTTP JSON 요청, seed·온도·생성 길이 전달, 출력·추론 채널 처리 |
| When2Call 실행 | [harness.py](../experiments/monkeys-passk-frontloop/monkeys_passk_frontloop/harness.py), run_when2call_attempt() | 시도별 새 요청, thinking 설정, 오류·형식·행동 결과 기록 |
| 행동 평가 | [evaluator.py](../experiments/monkeys-passk-frontloop/monkeys_passk_frontloop/evaluator.py), score_when2call() | 형식 유효성과 정답 행동 일치를 분리; 도구명 일치는 별도 필드 |
| JSON 계약 | [schema.py](../experiments/monkeys-passk-frontloop/monkeys_passk_frontloop/schema.py), extract_json_object(), repair_json_text(), parse_loc_action(), validate_loc_action() | JSON 후보 추출, lenient 조건부 복구, 도구·인자·최종 응답 검증 |
| Loc 반복 실행 | [loc_harness.py](../experiments/monkeys-passk-frontloop/monkeys_passk_frontloop/loc_harness.py), run_loc_attempt() | 도구 관찰을 이력에 추가, 형식 중단·final·한도 소진 판정, 종료 후 채점 |
| 탐색·정답 평가 | [loc_env.py](../experiments/monkeys-passk-frontloop/monkeys_passk_frontloop/loc_env.py), LocEnv, score_loc_final() | 파일 탐색·읽기·검색, 경로 제한, 파일·함수 일치 평가 |
| native XML | [loc_native.py](../experiments/monkeys-passk-frontloop/monkeys_passk_frontloop/loc_native.py), parse_loc_native_action(), validate_loc_native_action() | 태그 기반 호출 추출과 인자 검증 |
| 프롬프트 | [prompts.py](../experiments/monkeys-passk-frontloop/monkeys_passk_frontloop/prompts.py), [loc_prompts.py](../experiments/monkeys-passk-frontloop/monkeys_passk_frontloop/loc_prompts.py) | 행동 선택·JSON 출력 규약, 도구 목록과 최종 응답 형식 |
| 실행·저장 | [run_frontloop_when2call.py](../scripts/run_frontloop_when2call.py), [run_frontloop_loc.py](../scripts/run_frontloop_loc.py) | assignment_id, 기존 실행 건너뛰기, 조건별 JSONL 저장·요약 |
| Loc 집계 | [score_loc_arms.py](../scripts/score_loc_arms.py), block(), main() | strict 29문항 기록과 공통 28문항 비교 구분, 종료·정답 지표 집계 |
| When2Call 비교 | [score_arms_when2call.py](../scripts/score_arms_when2call.py), block(), paired_delta() | 문항별 8회 평균과 짝지은 부트스트랩 비교 |

## 구현을 해석할 때의 구체적 경계

1. **파서 복구 범위:** 숫자 뒤 큰따옴표 제거와 후행 쉼표 제거가 모두 repair_json_text()에 있습니다. 논문 설명과 이 스냅샷의 범위 차이를 유지합니다.
2. **호출 수:** Loc 루프에는 도구 실행 상한 8회와 모델 응답 반복 상한 10회가 따로 있습니다. final을 검사한 뒤 추가 도구 요청의 한도를 판단합니다.
3. **도구 목록:** JSON 프롬프트는 네 도구, native XML 프롬프트는 세 탐색 도구를 제시합니다. 공통 검증 스키마에는 run도 있으므로 프롬프트 목록과 파서 허용 집합을 동일시하지 않습니다.
4. **테스트 실행:** LocEnv.execute()의 run 분기는 테스트 미구성 응답을 반환합니다. run이라는 이름이 있다는 사실은 실제 테스트 실행·통과의 근거가 아닙니다.
5. **저장 한계:** Loc append_row()는 전체 outputs 대신 마지막 출력의 앞 1,500자와 단계 메타데이터를 저장합니다. 실행 중 이력에 넣은 모든 도구 반환 본문이 파일에 보존되는 것은 아닙니다.
6. **서버 모델:** CLI의 --model은 프로필·기록 라벨을 선택합니다. 클라이언트가 서버에 모델 로딩을 지시하거나 실제 가중치와 라벨의 일치를 검증하는 기능은 아닙니다.

## 데이터 준비 코드와 공개용 추가물

[materialize_when2call.py](../scripts/materialize_when2call.py), [materialize_locbench.py](../scripts/materialize_locbench.py), [clone_locbench.py](../scripts/clone_locbench.py)는 당시 환경에 의존하는 준비 코드로 함께 보존했습니다. 일부 Windows 캐시 경로와 별도 데이터 준비 의존성을 포함하므로 환경별 조정이 필요합니다.

[verify_public_results.py](../scripts/verify_public_results.py)는 이번 저장소 공개를 위해 추가한 독립 검산 도구입니다. 연구 코드를 import하거나 모델·서버·벤치마크에 연결하지 않습니다.

기존 [test_native_parser_symmetry.py](../scripts/test_native_parser_symmetry.py)는 작성된 입력 사례의 JSON/native 수용·거부 비교를, [test_frontloop_p0.py](../scripts/test_frontloop_p0.py)는 fixture 분리와 행동 평가·스키마 검사를 담고 있습니다. 두 파일은 원본 그대로 보존했으며 이번 공개 과정에서 테스트를 실행하지 않았습니다. 특히 P0 테스트는 로컬 데이터 준비와 fixture 작성을 요구합니다. 코드에 포함된 테스트 의도와 실제 테스트 통과 이력은 구분합니다.
