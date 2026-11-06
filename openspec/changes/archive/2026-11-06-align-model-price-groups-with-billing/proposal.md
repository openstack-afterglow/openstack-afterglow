## Why
앞선 종류별 가격 그룹 변경은 image/unit·audio/duration 기본 과금에서도 token 그룹을 자동 선택하여 실제 사용하는 단가와 보관된 다른 기준의 단가를 혼동할 수 있다. 공유 아키텍처 marker는 다른 진행 작업의 원래 값으로 보존해야 한다.

## What Changes
- 새 미디어 모델의 토큰 그룹은 선택한 과금 기준이 tokens일 때만 기본 선택한다. Unit/duration/characters/session의 기존 관련 가격 입력은 유지한다.
- 모델 종류 또는 과금 기준 변경은 표시 기본값을 다시 계산한다. 이미 입력·저장한 token 단가는 계속 표시하고 숨김은 삭제가 아니다.
- token 외 과금에서 token 단가가 존재한다는 이유만으로 저장을 금지하지 않는다. 다른 기준의 단가 보존·명시 전환 계약과 충돌하기 때문이다. Tokens 기준의 양수 reservation 검증은 유지한다.
- 다른 진행 중인 변경의 root architecture marker를 원래 값으로 복원·보존하고 이번 source는 격리 index로만 검증한다.
- TTS 이름 단서 조회 범위와 남아 있는 Lumen models.dev endpoint3개를 보고서에서 명시한다. 운영 변경 없음.

## Capabilities
### New Capabilities
없음.
### Modified Capabilities
관리자 가격 그룹의 basis-aware 기본 표시.

## Impact
ModelMediaPricingEditor와 관련 consumer regression, 기존 문서·검증 receipt. API/schema/권한/native 과금 변경 없음.
