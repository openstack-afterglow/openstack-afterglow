## Why

관리자 모델 카드의 표시 순서를 바꾸려면 각 모델의 숫자 입력 modal을 열어야 한다. 카드 자체를 위아래로 끌어 놓아 순서를 조정하고 실제 사용자 모델 목록에도 같은 순서가 저장되어야 한다.

## What Changes

- 모델 순서 수정 버튼·숫자 입력 modal·관련 state를 제거하고 카드 전체의 비대화형 영역을 native drag source/drop target으로 만든다. 동일 프로바이더 안에서 before/after 위치를 표시하고 drop 시 저장한다.
- 순서 grip은 keyboard 및 touch용 위/아래 이동 대안을 제공한다. 가격·기능·활성·삭제·체크박스 조작은 드래그를 시작하지 않는다.
- 프로바이더 그룹을 유지한다. 종류 필터로 숨긴 모델은 원래 전체 순서의 slot을 보존하고 보이는 모델만 그 slot 사이에서 재배열한다.
- Lumen `POST /v1/admin/models/reorder`를 BFF의 `/api/v1/chat/admin/models/reorder`로 호출한다. `{provider_id, expected_model_ids, model_ids}`는 프로바이더의 전체 기존 ID 순서와 새 순서다. 서버는 현재 순서·membership를 대조하고 하나의 transaction으로 rank만 변경한다. 성공은 204, stale/membership 및 기존 active-run mutation conflict는 409다.
- 저장 중 재진입을 막고 성공 후 catalog를 무효화·재조회한다. 실패를 inline으로 표시하고 보존된 실제 순서로 되돌린다. filter/auth/unmount 변경은 gesture와 늦은 UI 완료를 fence한다.

## Capabilities

### New Capabilities

관리자 모델 카드 drag/keyboard/touch 순서 조정과 원자적 순서 저장.

### Modified Capabilities

기존 모델 표시 순서 숫자 modal을 카드 기반 조작으로 교체한다. 프로바이더 순서 편집은 유지한다.

## Impact

Afterglow ChatConfiguration, 기존 shared surface/accent/focus token을 쓰는 sortable-card treatment, 소비자 회귀와 가격·기능·선택 조작 보존. Lumen은 별도 repo-local change로 atomic reorder endpoint·repository를 구현한다. 새로운 dependency·migration·가격/기능/credential 변경·운영 배포는 없다. 이전 단방향 가격 수정과 사용자/동시 변경을 보존한다.
