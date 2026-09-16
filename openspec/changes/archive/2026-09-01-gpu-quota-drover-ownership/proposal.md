# GPU quota Drover 소유권 복구

## Why

관리자 GPU quota 기본값 조회는 Drover가 소유한 `gpu_quotas` 데이터를 조회한다. 그러나 Afterglow 라우터가 자신의 데이터베이스 상태를 먼저 요구해, Afterglow DB가 일시적으로 사용할 수 없을 때 정상 Drover 응답까지 차단하고 HTTP 503으로 변환한다. 화면은 안전한 오류 처리 때문에 원인을 일반적인 내부 서버 오류로만 표시한다.

## What Changes

- Drover가 소유한 GPU quota CRUD 프록시 라우트에서 Afterglow DB 사전 조건을 제거한다.
- Drover가 정상 응답하는 경우 Afterglow DB breaker가 열려 있어도 기본값·프로젝트별 quota 조회와 변경이 계속 동작하도록 회귀 테스트한다.
- Drover 자체 DB/마이그레이션/서비스 문제는 기존처럼 503으로 fail-closed 한다.

## Scope

Afterglow API의 `/api/v1/admin/gpu-quotas/*` 프록시와 그 단위 테스트만 변경한다. Drover DB schema, Keystone catalog, Kolla 배포 설정은 별도 운영 검증 항목이며 이 변경으로 우회하지 않는다.

## Acceptance

- Afterglow DB가 unavailable이어도 mock Drover 성공 응답은 HTTP 200/204로 전달된다.
- Drover 호출 실패는 HTTP 503을 유지한다.
- GPU quota API의 관리자 인증은 변경되지 않는다.
