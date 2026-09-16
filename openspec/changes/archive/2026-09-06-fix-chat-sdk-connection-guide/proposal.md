## Why

사용자가 API 키 설정 화면에 제공된 OpenAI 예제로 `https://api.cloud.dmslab.re.kr/v1` 및 `gpt-5.6-luna`를 호출하면 APIConnectionError가 발생했다. `.env`의 LUMEN_TEST_API_KEY를 출력하지 않고 실제 SDK 호출한 결과 서버 인증서 SAN은 `*.dmslab.re.kr`/`dmslab.re.kr`만 포함하며 `api.cloud.dmslab.re.kr`과 불일치했다.

현재 ChatApiKeysManager는 window.location.host 앞에 `api.`를 붙여 주소를 추측하고 있어 localhost에서도 존재하지 않는 `api.localhost`를 안내한다. 예제의 `<code>`는 줄바꿈도 보존하지 않으며 `messages=[...]`는 실행 가능한 요청이 아니다.

## What Changes

- 기존 인증 BFF `/api/v1/chat/compat`를 통해 Lumen `/v1/compat`의 SDK별 `endpoints.*.sdk_base_url`을 사용한다. 임의 호스트 추론, 프로덕션 URL 하드코딩, 중복 `/v1` 추가를 하지 않는다.
- 연결 정보를 가져오지 못하거나 URL이 잘못되면 추측 예제 대신 오류와 재시도 액션을 표시한다. 세션/프로젝트 변경 및 unmount 이후 오래된 응답은 버린다.
- `LUMEN_API_KEY`와 `LUMEN_MODEL` 환경 변수, 실제 messages 배열과 출력 코드를 사용하는 완전한 OpenAI/Anthropic Python 예제를 `<pre><code>`로 표시한다. 모델 선택창의 복사된 API ID를 LUMEN_MODEL 값으로 안내한다.
- 기존 API 키 생성·목록·폐기 동작, BFF 인증과 Lumen 실행 경계는 유지한다. 기존 Button/Alert 및 semantic token만 재사용한다.

## Capabilities

### New Capabilities

- 없음.

### Modified Capabilities

- chat-sdk-connection-guide: 서버의 배포별 discovery 정보와 실제로 실행 검증한 SDK 예제를 제공한다.

브라우저 검증 중 기존 설정의 고정 11rem 좌측 메뉴가 390px 화면에서 코드 영역을 95px로 줄이는 문제를 확인했다. `ChatSettingsOverlay.svelte`의 mobile media rule만 추가해 메뉴를 가로 탭으로 배치했으며 코드 영역은 281px가 됐다. 이전 모델 복사 작업에서 추가한 backdrop의 중복 `role="button"`도 제거해 신규 컴파일 경고를 정리했다.

## Impact

- 구현 범위는 ChatApiKeysManager와 해당 회귀 테스트, 기존 외부 API 가이드/CHANGELOG다. 다른 dirty 작업과 Lumen 서비스 소스·배포 설정·인증서는 수정하지 않는다.
- 현재 live `/v1/compat`은 OpenAI `https://lumen.dmslab.re.kr/v1`, Anthropic `https://lumen.dmslab.re.kr`을 광고한다. TLS 검증을 유지한 모델 조회/비스트리밍 호출은 HTTP 200, 양 SDK 스트리밍도 완료했다.
- 완료 기준: authoritative URL 사용/실패 및 stale 응답 회귀, 실제 렌더링된 예제를 추출해 SDK 실행, mobile/tablet/desktop의 줄바꿈·스크롤·오류/재시도 시각 확인, 관련 named target 검증.
- API 키는 로그/도구 출력/기록/소스에 포함하지 않는다. 커밋·푸시·배포는 범위 밖이다.
