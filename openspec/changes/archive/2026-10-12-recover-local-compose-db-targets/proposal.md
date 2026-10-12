## Why

사용자의 `docker compose -f docker-compose.dev.yml up -d backend frontend --force-recreate --build`는 이미지 빌드를 완료했으나 네 migration/bootstrap이 외부 `172.30.0.11:3306` 연결 timeout(MySQL 2003)으로 종료했다. Lumen의 `172.30.11`은 실제 컨테이너에서 같은 IP로 해석된다. DB 환경 변수 override를 제거한 plain Compose의 `.env` 렌더링이 실패한 컨테이너의 실제 URL과 일치한다. 기존 다섯 worker는 로컬 DB를 사용하며 SELECT 연결이 정상이다.

사용자가 복구 범위로 **기존 로컬 DB로 복구**를 선택했다. 명시적 외부 DB 선택을 일반적으로 금지하거나 Compose 기본 정책을 되돌리는 작업이 아니다.

## What Changes

- 사용자가 작업 중 `.env`의 외부 DB URL 다섯 개를 주석 처리한 변경을 그대로 보존한다. 아직 외부 URL을 저장한 ignored `.local-services/compose.env`의 Drover·Lumen·Waygate 세 값만 기존 worker의 로컬 URL로 맞춘다. Afterglow·Palimpsest는 현재 local fallback을 사용한다. 비밀 값은 출력·커밋하지 않는다.
- 현재 개발 스택의 키·private 설정·DB/cache/blob 볼륨·worker/datastore 컨테이너를 보존한다. 외부 DB에는 연결·migration/bootstrap·쓰기하지 않는다.
- 실제 Compose 렌더링의 14개 DB 소비자와 기존 키/volume 대응을 확인했다. 조사 중 동시 로컬 재기동으로 migration/bootstrap 네 개 exit0 및 API·backend/frontend healthy를 관측했으므로 중복 up/build는 실행하지 않았다.
- 후속 bridge 이동 시험 두 번은 test MariaDB의 published host port 연결을 유지하지 못해 원래 `172.30.0.0/16`·IP·alias로 rollback했다. 세 datastore의 ID·PID·StartedAt·tmpfs·mount·host port 설정과 실제 MySQL/PostgreSQL/Redis 연결 복구를 확인했다. 그 뒤 사용자가 미사용 컨테이너 전체 정리를 요청해 이동 계획을 대체했다.
- 중지 컨테이너 19개·빈 network 9개를 정리한 뒤 사용자가 실행 중 임시 QA 19개 전체 제거를 선택했다. 승인된 QA를 정상 중지해 제거하고 network 5개도 제거했다. 총 컨테이너 38개·network 14개를 exact ID로 삭제했으며 force/volume/prune은 사용하지 않았다. 승인된 tmpfs datastore 9개의 데이터는 폐기됐다.
- 최종 21개 컨테이너 중 실행 17개와 완료된 migration/bootstrap 네 개를 보존했다. 현재 개발 스택·BuildKit·별도 sandbox의 ID·PID·StartedAt·restart·mount·port·network 연속성과 전체 volume 25개 이름 불변을 확인했다. `172.30.0.0/16` bridge는 제거됐으며 개발 network `172.18.0.0/16`는 그대로다.
- 실제 Drover readiness는 HTTP200 및 DB/Redis/migration/Keystone 모두 `ok`다. 정리 후 canonical `npm run services:smoke`는 direct readiness/API contract를 통과하고 인증 BFF token 미설정으로 exit1이었다. 인증 dashboard/OpenStack 전체 smoke 성공으로 표기하지 않는다. 상세 증거는 `evidence/cleanup.json`과 기존 `evidence/runtime.json`에 남긴다.

## Impact

공개 코드·Dockerfile·Compose·API·DB schema·전역 DB 선택 정책은 변경하지 않는 machine-local 설정 복구와 사용자 승인 QA 정리다. 운영 `*_kolla`·Keystone IAM·기존 영구 데이터 복사/삭제·키 rotation·배포는 범위 밖이다. 승인된 tmpfs QA datastore 데이터만 중지와 함께 폐기했다. 전체 서비스 smoke의 상류 인증/OpenStack 실패는 숨기지 않는다.
