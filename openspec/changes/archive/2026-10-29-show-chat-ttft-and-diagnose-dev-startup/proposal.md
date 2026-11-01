## Why

채팅 전송 뒤 최초 응답까지의 대기 시간을 사용자가 확인할 수 없다. 개발 Compose는 이미지 빌드 성공 뒤 네 migration/bootstrap 작업이 exit 1로 종료되어 실행되지 않는다.

## What Changes

- 기존 채팅 send/regenerate/retry 경로에서 브라우저의 monotonic clock으로 요청 제출부터 첫 비어 있지 않은 답변 텍스트 수신까지 측정하고 TTFT를 표시한다. 접힐 수 있는 reasoning과 heartbeat/status/tool metadata는 측정 종료 신호가 아니다.
- 완료·취소·실패·thread 전환에서 측정값의 소유권을 보존하고, 관측하지 않은 과거 응답이나 토큰 없는 실패에는 값을 만들지 않는다. 서버/DB에 새로운 timing authority를 만들지 않는다.
- 기존 실패 컨테이너 로그와 실제 effective configuration으로 네 startup 실패의 원인을 확인한다. 증명된 source 결함만 최소 수정하고 외부 DB/키/볼륨은 보존한다.

## Capabilities

### New Capabilities

- 채팅 응답별 client-observed TTFT 표시.

### Modified Capabilities

- 원인이 source에 있을 때만 개발 startup 경로를 수정한다. 외부 인프라 실패는 증거와 안전한 복구 전제조건을 보고한다.

## Impact

Frontend chat state/presentation와 지원 언어 카탈로그, 관련 문서. backend protocol/schema/provider 동작은 변경하지 않는다. dev 브랜치의 기존 변경을 보존한다. 실제 브라우저의 지연 SSE·취소/오류/재요청 경로와 frontend 이미지 빌드/실행을 검증한다. 운영 DB restart/bootstrap/migration·endpoint 전환·prune은 범위 밖이다. 로컬/synthetic 검증과 실제 provider/운영 증거를 분리한다.
