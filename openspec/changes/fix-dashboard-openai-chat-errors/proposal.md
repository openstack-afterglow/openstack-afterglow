## Why

운영 Afterglow 대시보드에서 OpenAI 모델을 선택한 Lumen 채팅이 실패한다. 직접 OpenAI API와 Codex의 Lumen Responses 경로는 동작하지만, 대시보드는 별도 Keystone 인증의 native durable run 경로를 사용한다. 두 경로를 동일한 성공 증거로 취급하면 원인을 놓친다. 현재 실패의 HTTP 오류 상태와 상세 내용은 사용자 화면에 충분히 드러나지 않고, 비동기 run 실패는 일반적인 안전 메시지만 노출된다.

## What Changes

- 대시보드 native 요청·BFF 프록시·Lumen native 모델 실행을 추적하여 실제로 확인한 OpenAI 경로 불일치를 수정한다. 확인되지 않은 공급자 오류를 UI에서 우회하거나 stateless compat 경로로 바꾸지 않는다.
- 채팅 접수의 비-2xx 응답은 제한된 안전 detail과 HTTP 상태를 표시한다. 기존 공용 API client가 원문 응답까지 메시지로 허용하는 모델 목록·대화 생성은 원문을 재출력하지 않고 HTTP 상태를 표시한다. JSON 오류 본문이 없거나 구조가 올바르지 않아도 상태를 표시한다.
- HTTP 202 이후의 durable run 실패는 안전 메시지와 안정적인 error_code를 표시한다. provider 원문, API 키, 내부 예외/프롬프트는 클라이언트로 보내지 않는다. 취소와 실패는 구별한다.
- 관련 native 경로의 회귀 검사와 운영 준비·인증된 성공/실패·배포 후 관찰 검증을 수행한다. 라이브 권한이 없으면 검증되지 않은 배포/모델 성공을 주장하지 않는다.

## Capabilities

### New Capabilities

- 없음.

### Modified Capabilities

- Lumen native chat: OpenAI 모델의 영속 채팅 실행 경로가 선택한 모델의 유효한 provider 요청과 일치한다.
- Afterglow chat UX: 제출 단계에서는 HTTP 상태 및 안전한 상세 내용, 실행 단계에서는 안전 메시지 및 오류 코드를 구분해 표시한다.

## Impact

기존 영속 대화·도구·승인·사용량 계약 및 대시보드의 Keystone 인증은 유지한다. Codex/API-key stateless Responses 계약과 혼동하지 않는다. 다른 제공자의 호출 형식, 공급자 비밀, 관리자 전용 응답은 변경하지 않는다. 운영 반영은 테스트가 통과한 불변 이미지와 정식 Kolla 경로로만 수행한다.
