# 공개 수치 검산과 실험 환경 복원

## GPU 없이 공개 자료 검산

저장소 루트에서 Python 3.10 이상으로 실행합니다. 외부 패키지가 필요하지 않습니다.

~~~bash
python3 -B scripts/verify_public_results.py
~~~

공개용 검산 도구는 다음을 확인합니다.

1. 조건별 문항 수·반복 수·분모와 종료 상태 합계
2. 최종 응답·파일·함수 정답 수의 범위
3. 논문 표 전사값과 저장 요약에서 만든 집계 투영의 일치
4. 논문 PDF·그림·원본 소스 파일의 SHA-256
5. 보존 Python 소스의 문법 해석

검산 도구의 범위는 집계 수치·파일 해시·Python 문법 검사입니다. 연구 코드 import, 모델 추론, 원시 원장 재채점과 부트스트랩은 실행하지 않습니다. 함께 제공하는 두 테스트 소스의 실행은 별도 절차입니다.

## 공개 자료의 구성

| 자료 | 범위 |
| --- | --- |
| results/paper_results.json | 논문 표의 정수와 지표 정의를 정리한 파일 |
| results/reference_aggregates.json | 보존된 요약 JSON에서 집계 수치만 추린 투영. 원본 파일 식별자·해시 포함 |
| publication_manifest.json | 원본 그대로 복사한 파일의 해시와 공개용 변경 내역 |
| experiments/monkeys-passk-frontloop/spec/selected.json | When2Call 40개·Loc 29개 ID와 선택 방식. 문항 본문·정답·불필요한 보조 단계 제외 |
| experiments/monkeys-passk-frontloop/spec/f0.json | 당시 설정을 바탕으로 로컬 모델 경로·편집 메타데이터를 정리한 공개용 템플릿 |

원래 strict 원장에는 29문항·232회가 포함돼 있습니다. 논문의 28문항·224회 비교에는 제외 문항을 적용해야 합니다. 오프라인 재파싱의 29문항 통계를 공통 28문항 결과에 섞지 않습니다.

## 전체 추론을 다시 실행하기 위한 준비

전체 추론에는 벤치마크 문제·정답 파일, 평가 저장소와 모델 가중치 등 별도의 자료와 실행환경 준비가 필요합니다.

1. [기존 모델·벤치마크 자료](../THIRD_PARTY_NOTICES.md)를 각 제공처의 조건에 맞게 확보합니다. 설정 템플릿의 모델 revision과 When2Call snapshot을 확인합니다. Loc 데이터의 원래 revision은 이 템플릿에 고정돼 있지 않습니다.
2. 보존된 materialize_when2call.py와 materialize_locbench.py의 로컬 캐시 경로를 본인 환경에 맞춰 검토합니다. Loc 준비 스크립트는 pyarrow·huggingface_hub를 사용합니다. 공개 수치 검산에는 해당 패키지가 필요하지 않습니다.
3. fixtures/public·fixtures/private와 fixtures/loc_public·fixtures/loc_private 구조를 복원합니다. 공개 fixture에는 문제·도구가, 별도의 비공개 fixture에는 정답 라벨 또는 코드 위치 기준이 들어갑니다.
4. clone_locbench.py를 검토해 각 문제의 기준 commit에 해당하는 저장소를 repos/에 준비합니다. 실제 벤치마크 저장소 코드 실행은 이 연구의 파일 탐색·위치 식별과 구분합니다.
5. llama.cpp 서버에 해당 모델을 로드하고 모델 revision·양자화·추론 프로필·생성 예산을 확인합니다. 기존 클라이언트의 기본 주소는 로컬 8080 포트입니다. --model 인자만으로 서버의 모델이 바뀌지 않습니다.

준비가 완료된 환경에서의 실행 진입점 예시는 다음과 같습니다.

~~~bash
# When2Call: 서버에 Granite를 로드한 환경
python3 scripts/run_frontloop_when2call.py --model granite
python3 scripts/run_frontloop_when2call.py --model granite --arm T --thinking-off

# Loc-Bench: 공통 28문항, 서버에 Granite를 로드한 환경
python3 scripts/run_frontloop_loc.py --model granite --all --exclude fortra__impacket-1636
python3 scripts/run_frontloop_loc.py --model granite --all --arm B --lenient --exclude fortra__impacket-1636
python3 scripts/run_frontloop_loc.py --model granite --all --arm C --notation native --exclude fortra__impacket-1636

# 서버를 Ministral로 바꾼 뒤 별도 실행
python3 scripts/run_frontloop_when2call.py --model ministral
python3 scripts/run_frontloop_loc.py --model ministral --all --arm M --exclude fortra__impacket-1636
~~~

실행 원장은 runs/ 아래에 생성되며 Git에서 제외됩니다. 새 실행은 별도 깨끗한 체크아웃·결과 디렉터리에서 관리하고 기존 결과 파일과 섞지 마십시오. 이 명령 예시는 환경과 데이터 준비가 끝난 후에만 사용할 수 있습니다.

## 전체 실행 재현에 필요한 조건

보존 코드의 파서 복구 범위가 논문 설명보다 넓고 일부 중간 자료가 남아 있지 않아 원래 실행 전체를 동일하게 재생하기는 어렵습니다. 재실험 시 모델 바이너리·서버 빌드·데이터 revision·파서 버전을 함께 기록하고, 기존 집계와 새 실행의 차이를 비교해야 합니다.
