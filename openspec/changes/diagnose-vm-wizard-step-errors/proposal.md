# VM 생성 마법사 단계 데이터 오류 진단·로딩 정지 수정

## Why

사용자 보고: VM 생성 설정 단계에서 "현재 단계의 일부 데이터를 불러오지 못했습니다" 배너가 반복해서 나타나지만 실제 생성은 성공한다. 배너는 어떤 조회가 왜 실패했는지 표시하지 않았다.

2026-11-02 읽기 전용 운영 관측(v1.32.0, controller1~3 `afterglow_backend` 요청 로그):

- 1·3단계 경로(images, volumes, flavors, networks, keypairs, security-groups, networks/default)는 모두 200이었고 최대 약 11초로 브라우저 제한 30초보다 짧았다.
- 공개 endpoint는 HTTP/2이다.
- 스크린샷에서 네트워크(Default)와 보안 그룹(default)은 채워졌으므로 실패 후보는 키페어 또는 기본 네트워크 조회다.
- 따라서 실패는 브라우저 측(토큰 refresh 실패에 따른 미전송 401, 30초 시간 초과, 네트워크 오류)으로 추정되며 로그만으로 확정할 수 없다.

코드 검토 중 재현한 별도 결함: 같은 project scope의 쓰기 요청(`withMutationInvalidation`)이 진행 중인 공유 GET을 무효화하면 해당 읽기는 `AbortError`로 끝나고 `loadOption`이 상태를 `loading`으로 남겨 영구 로딩·재시도 불가가 된다.

## What Changes

- `vmCreateStore`의 `optionError`가 `ApiError`(HTTP 상태), `TimeoutError`, `TypeError`(네트워크), 기타 브라우저 오류를 구분한다.
- `currentStepErrors`가 현재 단계의 실패 항목과 원인을 제공하고 `VmCreatePanel` 배너가 목록으로 표시한다(9개 언어).
- Timeout은 일반 GET·token refresh/직전 실패의 경로에 따라 달라지므로9개 언어의 오류 문구에서 고정30초라는 단정을 제거한다. 플레이버는 기존 composer 오류 경로를 쓰고 파일 스토리지는 단계 배너 대상이 아니다.
- scope가 그대로인데 무효화로 중단된 옵션 조회는 `idle`로 되돌리고 현재 단계에 필요하면 다시 요청한다. scope 변경·destroy로 인한 중단은 기존처럼 무시한다.

## Non-goals

- 운영 배포, backend 변경, 원래 배너의 근본 원인 확정(다음 발생 시 화면 원인으로 확정).
