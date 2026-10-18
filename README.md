# Failure Analysis of Tool Use in 8B LLMs

**로컬 LLM 실행 계층의 실패 진단과 변경 영향 검증**

[논문 PDF](CISC-W_2026_paper__196.pdf) · [프로젝트 소개서](docs/project-summary.ko.md) · [코드 안내](docs/code-guide.md) · [실험 방법·한계](docs/methodology.md) · [English](README.en.md)

## 프로젝트 개요

LLM 에이전트의 최종 오답에는 출력 파싱 실패, 잘못된 행동 선택, 호출 한도 내 응답 미제출이 함께 포함될 수 있습니다. 이 연구에서는 두 로컬 8B 모델의 실행을 **형식 준수 → 행동 선택 → 실행 종료 → 정답 평가**로 나누어 분석했습니다.

직접 수행한 연구의 문제 분석, 진단 조건 비교, 결과 해석을 정리한 저장소입니다. 기존 모델과 llama.cpp를 사용했으며, 공개 소스의 함수별 개인 작성 범위를 단독 개발 성과로 확대하지 않았습니다.

| 평가 축 | 확인하려던 문제 | 규모 |
| --- | --- | --- |
| When2Call | 출력 형식이 맞아도 행동을 잘못 선택하는가? | 조건별 40문항 × 8회 = 320회 |
| Loc-Bench Security | 형식 중단을 완화한 조건에서 종료 상태·정답은 어떻게 달라지는가? | 조건별 공통 28문항 × 8회 = 224회 |

## 핵심 결과

Granite JSON의 사후 진단 조건에서 형식 중단은 **86.6% → 51.8%, −34.8%p**로 줄었지만, 호출 한도 소진은 **10.7% → 38.8%, +28.1%p**로 늘었습니다. 최종 응답 제출과 함수 정답도 별도로 집계했습니다.

![Loc-Bench Security의 조건별 종료 상태 분포](docs/assets/loc-termination.png)

각 막대는 224회입니다. 녹색 final은 최종 응답 제출이며 정답 여부는 별도로 평가합니다.

| 조건 | 형식 중단 | 호출 한도 소진 | 응답 제출 | 파일 일치 | 함수 일치 |
| --- | --- | --- | --- | --- | --- |
| Granite JSON strict | 194 (86.6%) | 24 (10.7%) | 6 (2.7%) | 6 (2.7%) | 4 (1.8%) |
| Granite JSON parser-relaxed | 116 (51.8%) | 87 (38.8%) | 21 (9.4%) | 21 (9.4%) | 17 (7.6%) |
| Granite native XML | 57 (25.4%) | 129 (57.6%) | 38 (17.0%) | 34 (15.2%) | 24 (10.7%) |
| Ministral JSON | 34 (15.2%) | 90 (40.2%) | 100 (44.6%) | 36 (16.1%) | 7 (3.1%) |

모든 비율의 분모는 조건별 전체 224회입니다. Function accuracy는 예측한 **코드 위치의 파일 경로·함수명 일치율**입니다.

When2Call에서는 형식 준수율이 96.3–99.1%인 반면 행동 선택 정확도는 41.3–65.0%였습니다. 형식이 유효하면서 정답 행동과 일치해야 행동 정답으로 처리했습니다. [전체 수치와 정의](docs/methodology.md)

## 소프트웨어 엔지니어링 관점에서 볼 부분

| 역량 | 이 연구에서 수행한 분석 | 읽을 자료 |
| --- | --- | --- |
| 기존 실행 흐름 이해 | 모델 요청, 출력 해석, 도구 실행, 종료·채점 경계를 구분했습니다. | [코드의 연결 관계](docs/code-guide.md) |
| 장애 분석 | 형식 중단, 행동 오선택, 호출 한도 소진과 제출 후 오답을 분리했습니다. | [연구 방법](docs/methodology.md) |
| 변경 영향 검증 | 진단 조건 전후의 종료 분포와 정답 지표를 함께 비교했습니다. | [정수 집계](results/paper_results.json) |
| 기술 커뮤니케이션 | 개선된 지표, 남은 문제, 해석할 수 없는 원인을 구분했습니다. | [프로젝트 소개서](docs/project-summary.ko.md) |

연구 환경에서의 분석·검증 경험입니다. 실제 반도체 설비 운용이나 고객사 장애 대응 경험으로 서술하지 않았습니다.

## 코드와 공개 수치 살펴보기

- [모델 요청](experiments/monkeys-passk-frontloop/monkeys_passk_frontloop/client.py): Python urllib.request를 통한 llama.cpp HTTP 연동
- [JSON 해석·검증](experiments/monkeys-passk-frontloop/monkeys_passk_frontloop/schema.py): strict 해석, 조건부 복구, 도구·인자 검증
- [반복 실행·종료 판정](experiments/monkeys-passk-frontloop/monkeys_passk_frontloop/loc_harness.py): 도구 관찰, 호출 한도, final·format_stop·tool_cap 구분
- [결과 저장](scripts/run_frontloop_loc.py): 조건별 JSONL 저장과 요약
- [전체 코드 안내](docs/code-guide.md): 함수와 역할, 기존 도구와 연구 코드의 경계

GPU나 모델 다운로드 없이 공개 표의 산술·저장 요약 대응·원본 파일 해시를 확인할 수 있습니다. Python 3.10 이상이 필요하며 추가 Python 패키지는 사용하지 않습니다.

~~~bash
git clone https://github.com/SHINDAWIT/Failure-Analysis-of-Tool-Use-in-8B-LLMs.git
cd Failure-Analysis-of-Tool-Use-in-8B-LLMs
python3 -B scripts/verify_public_results.py
~~~

이 검사는 저장소 공개를 위해 추가한 검산 도구입니다. 원시 원장의 재채점이나 GPU 실험 재현은 포함하지 않습니다. [실험 환경 복원 절차](docs/reproducibility.md)

## 결과를 읽을 때의 범위

- parser-relaxed는 실패 관찰 후 설정한 사후 진단입니다. **보존 코드에는 숫자 뒤 큰따옴표 제거 외에 후행 쉼표 제거도 포함**돼 있어, 논문의 설명과 코드의 처리 범위를 구분했습니다.
- native XML은 JSON과 출력 규약·프롬프트 도구 목록이 다릅니다. 같은 개입의 효과로 합치지 않았습니다.
- tool_cap만으로 무한 반복, 종료 로직 결함, 탐색 예산 부족 중 하나를 원인으로 확정할 수 없습니다.
- 조건별 집계 차이는 개별 실행의 상태 전이를 입증하지 않습니다. 모델별 기본 추론 설정도 달라 순수 모델 효과로 해석하지 않았습니다.
- 일부 중간 모델 출력·도구 반환 본문이 보존되지 않았습니다. 원시 출력·정답 파일·모델 가중치는 이 저장소에 배포하지 않았습니다.

[자료 출처·공개용 변경](docs/provenance.md) · [벤치마크와 기존 도구](THIRD_PARTY_NOTICES.md)
