## Why

모델 한 개를 이동할 때마다 저장 중 이동 조작이 잠기고, 완료 후 전체 `load()`가 기존 카드를 skeleton으로 교체하여 연속 이동과 포커스를 끊는다. 이미 노출된 목록은 유지하고 서버 저장 내용이 현재 내용과 다른 경우에만 반영해야 한다.

## What Changes

- `ChatConfiguration`의 순서 이동은 즉시 optimistic 상태를 반영하며 저장 중에도 드래그·위/아래 이동을 허용한다.
- 순서 저장은 직렬 실행한다. 같은 provider에서 저장 대기 중인 여러 이동은 최신 순서 하나로 합치고, 다음 CAS 요청은 마지막 서버 확정 순서를 사용한다.
- 순서 저장 성공의 전체 provider/model/billing reload를 제거한다. 204 응답으로 확정된 순서와 현재 순서가 다르면 대기 순서만 계속 저장하며, 모두 저장된 뒤 모델 목록을 background 조회하여 실제 변경만 반영한다. 오래된 조회 결과는 이후 이동을 덮어쓰지 않는다.
- 실패/409에서 대기 순서를 중단하고 카드 목록을 숨기지 않은 채 서버 내용과 동기화한다. scope 변경과 unmount의 늦은 완료는 무시한다.
- provider 범위, 종류 필터의 숨은 슬롯 보존, keyed card/포커스, 기존 오류·저장 문구 및 사용자 모델 목록 invalidation을 유지한다.

## Capabilities

### New Capabilities

없음.

### Modified Capabilities

- 관리자 모델 표시 순서: 연속 이동과 최신 상태 자동 저장, 동일 서버 결과의 무변경 반영.

## Impact

Afterglow frontend `ChatConfiguration.svelte`와 기존 `provider_catalog.test.ts` 및 관련 문서만 변경한다. 기존 Lumen CAS/204 계약을 사용하며 BFF, DB, provider 추론, CLI 설치기, 운영 서비스는 변경하지 않는다. 최신 `origin/dev` ec5894c 기반 격리 worktree `/Users/pieroot/code/afterglow-model-reorder`에서 작업한다. 공유 checkout의 미해결 merge와 이전 CLI 작업은 보존한다. 커밋·push·배포는 이 요청에 포함하지 않는다.
