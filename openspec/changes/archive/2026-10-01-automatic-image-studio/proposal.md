## Why

웹 Image Studio 사용자는 생성/수정 endpoint를 선택하기보다 원하는 결과를 프롬프트로 설명해야 한다. 현재 수동 toggle은 첨부 이미지를 보존하면서도 생성 mode에서 조용히 사용하지 않는 상태를 만들 수 있다. API 소비자의 명시적인 생성/편집 계약은 그대로 유지한다.

## What Changes

- 웹 composer에서 생성/수정 toggle과 별도의 edit mode 상태를 제거하고 하나의 이미지 요청 CTA를 제공한다.
- 첨부 없는 요청은 기존 `/api/v1/chat/images/generations`로 자동 제출한다.
- 첨부 있는 요청은 업로드 완료 뒤 기존 `/api/v1/chat/images/edits`에 `input_asset_id`와 사용자 프롬프트를 함께 제출한다. 생성 endpoint는 입력 이미지를 허용하지 않으므로, 참고 이미지를 이용한 새 이미지 생성도 이미지 입력을 지원하는 경로를 사용한다.
- 생성/편집의 의미 판단은 이미지 모델의 native prompt/image 이해에 맡긴다. 별도의 분류 모델 호출, 키워드 heuristic, 숨겨진 prompt 재작성, 사용자 첨부 폐기는 하지 않는다.
- 첨부 제거는 텍스트 기반 생성으로 즉시 복귀한다. 업로드 중·실패·프로젝트 전환·중복 제출·불확실한 응답의 기존 격리와 intent key 계약을 유지한다.
- Web copy와 접근성 이름을 생성/수정 전용에서 중립적인 이미지 요청/입력 이미지로 바꾸고 자동 처리 설명을 제공한다.

## Capabilities

### New Capabilities

- 웹 Image Studio의 단일 자동 입력 workflow: text-to-image와 image-conditioned reference generation/editing.

### Modified Capabilities

- Image Studio의 input preview, attachment lifecycle 및 request fingerprint에서 수동 edit mode를 제거한다.
- 직접 native/OpenAI 호환 이미지 API의 endpoint 선택, schema, 인증·소유권·durable run·가격·과금 계약은 변경하지 않는다.

## Impact

- 구현: `frontend/src/lib/components/chat/ImageStudio.svelte`와 기존 component behavior tests.
- 문서: `DESIGN.md`, `ARCHITECTURE.md`, `docs/api/chat.md`, `CHANGELOG.md`.
- Lumen 및 Afterglow backend source, 모델/키/가격 설정은 변경하지 않는다. 현재 route는 OpenAI GPT Image와 Gemini native image 입력을 이미 지원한다.
- 실제 프롬프트 의미 이해와 결과 품질은 등록된 provider/model이 담당한다. 합성 API 브라우저 QA는 UI와 요청 선택의 증거이며 유료 provider inference의 증거가 아니다.
- 기존 SVG/media 작업과 다른 세션의 uncommitted changes 및 실제 Git index를 보존한다.
