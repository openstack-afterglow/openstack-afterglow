## Why

신규 공급자 모델을 Lumen 재배포 없이 조회·검토·등록하고 Afterglow 채팅에서 사용해야 한다. 계정에서 발견된 모델 ID와 정적 가격/capability 메타데이터, 실제 추론 가능 여부는 서로 다른 사실이다.

## What Changes

- Lumen이 Anthropic, OpenAI 호환, Gemini의 저장된 API-key 자격으로 bounded live discovery를 수행한다. 정상 빈 결과와 실패를 구분하며 live 실패에서 정적 fallback 또는 부분 목록을 반환하지 않는다. 정적 참고 목록은 live 미지원 인증/설정에만 제공한다.
- 기존 `models`/`source`와 함께 provider, 조회 시각, completeness, safe error, 최소 candidate metadata를 전달한다. discovery는 DB를 변경하지 않는다.
- Afterglow는 후보의 표시명·가격·지원 범위를 검토한 뒤 기존 POST로 등록·활성화하거나 비활성 저장한다. 가격 미확인은 활성화를 차단하며 discovery를 실행 가능 증거로 표현하지 않는다.
- generation/provider/token/project fences가 오래된 discovery 응답과 순차 등록의 provider 혼합을 막는다. 모델 변경 후 열린 채팅은 명시적 새로고침·focus/visible 및 invalidation으로 목록만 갱신하며 유효한 선택을 유지한다.

## Capabilities

### New Capabilities

- live-provider-model-onboarding: 최신의 계정별 opaque 모델 ID 조회와 검토 등록.

### Modified Capabilities

- 관리자 모델 설정: safe source/status/retry와 등록/가격/capability 준비 상태 분리.
- 채팅 모델 목록: 재시작 없는 목록 갱신과 stale request 격리.

## Impact

Lumen은 discovery, credentials, routing, pricing/admission 정본을 계속 소유한다. Afterglow는 UI와 authenticated BFF만 소유한다. 모델명 hardcode, LiteLLM 업그레이드, fuzzy 가격/capability 추정, 비밀 노출, discovery 중 자동 등록/덮어쓰기는 금지한다. 기존 prompt-cache 가격 작업을 보존한다. 두 dev checkout만 변경하며 commit/push/운영 배포는 하지 않는다. 실제 provider와 Keystone 증거는 합성 테스트와 분리한다.
