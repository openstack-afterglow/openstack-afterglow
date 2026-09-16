## Why

메시지 작성창의 모델 선택 목록에서 외부 OpenAI/Anthropic 호환 API의 `model` 인자에 붙여 넣을 모델 이름을 바로 복사할 수 있어야 한다. 내부 숫자 `id`와 표시 이름 `display_name`이 아니라 `AvailableModel.model_name`이 API ID다 (`docs/api/chat.md`).

## What Changes

- 기존 모델 선택 overlay의 각 행에 API ID를 항상 표시하고, 공용 `Button`으로 독립적인 `ID 복사` 액션을 추가한다.
- `model_name` 원문만 복사한다. 따옴표, `model=` 접두사, 표시 이름, 내부 관리 ID를 붙이지 않는다.
- 복사 성공/실패는 기존 toast 패턴으로 알린다. 복사는 모델 선택이나 modal 닫기를 유발하지 않는다.
- 모델명 선택은 기존 `onSelect(model_name)` 및 닫기 계약을 유지한다.
- mobile/tablet/desktop에서 긴 이름, capability 배지와 복사 버튼이 겹치지 않게 배치하고 키보드 초점과 닫기를 유지한다.

## Capabilities

### New Capabilities

- chat-api-model-copy: 메시지 전송 전 모델 선택 목록에서 API 호출용 모델 이름을 복사한다.

### Modified Capabilities

- 없음. 모델 선택 callback, BFF, Lumen 실행 및 외부 API 계약은 변경하지 않는다.

## Impact

- 구현 범위: `frontend/src/lib/components/chat/ModelPickerOverlay.svelte` 및 기존 외부 API 가이드/변경 기록.
- 기존 semantic tokens, `Button`, toast를 재사용한다. 신규 의존성 및 디자인 토큰은 없다.
- `dev`에서 작업하며 이미 존재하는 다른 변경은 수정하거나 되돌리지 않는다. 커밋·푸시·배포는 범위 밖이다.
- 완료 기준: 실제 Svelte overlay를 Chromium에서 렌더해 서로 다른 id/display_name/model_name, 복사 성공·권한 거부·Clipboard API 부재, 선택 불변, 기존 선택 callback, 검색과 키보드, mobile/tablet/desktop 및 두 테마를 확인한다. 기존 관련 검사로 호환성을 확인한다.
