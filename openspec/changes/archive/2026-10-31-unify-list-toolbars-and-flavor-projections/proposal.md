## Why

목록 filter toolbar는 label 있는 sort와 label 없는 search/status, 다른 새로고침 배치를 섞어 높이/기준선이 맞지 않는다. VM wizard는 수백 개 flavor를 읽을 때 native spec/ACL 및 fresh host fitting을 반복하고 전체 page 버튼을 한 줄에 렌더링하여 응답과 가로 레이아웃 문제가 발생한다.

## What Changes

- 기존 Field/input/ResourceToolbar 규칙으로 관련 목록 filter header의 label/컨트롤 정렬과 반응형 배치를 통일한다.
- Wizard의 unbounded 페이지 버튼을 기존 bounded Pagination으로 대체한다.
- 백엔드가 global flavor metadata와 project-independent host capacity 관측을 주기적으로 준비하여 Redis에 제한된 수명으로 저장한다. 목록은 현재 native visibility와 프로젝트/domain quota를 다시 확인하고 저장된 공통 관측으로 필요한 결과만 계산한다.
- 실제 create admission은 snapshot을 허가로 취급하지 않고 exact flavor, 현재 권한, quota, fresh host capacity를 계속 확인한다. 미수집/만료/실패/정책 변경은 unknown 또는 fresh 검증으로 처리하고 부족을 허용으로 바꾸지 않는다.

## Capabilities

### New Capabilities

기존 dispatcher가 관리하는 read-only flavor discovery snapshot과 빠른 목록 projection.

### Modified Capabilities

사용자/관리자 flavor 목록과 공용 filter/pagination 표현. Native quota 및 VM 생성 API 권위는 변경하지 않는다.

## Impact

Frontend shared toolbar, wizard pager, backend flavor discovery/eligibility/capacity, 기존 API 및 lifecycle, 관련 behavior regression과 문서. 새 SQL schema/migration·권한 부여·GPU profile/domain 한도·운영 배포는 없다. Redis snapshot은 파생 데이터이며 실패하거나 오래된 값은 quota 권위나 VM 예약이 아니다. 공유 worktree/index/review marker를 보존한다. 검증은 합성 runtime과 승인 범위 내 읽기 전용 native 측정을 구분한다.
