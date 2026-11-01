## Why
현재 생성기는 표준 CPU/memory/GPU flavor를 사전 생성하지만 VM wizard는 큰 목록에서 사용자가 이름으로 조합을 찾게 한다. 코어·메모리·GPU 모델/개수를 직접 고르고 저장·재사용하며 새로고침/탐색 뒤 복원하는 흐름이 필요하다.

## What Changes
- 기본 직접 구성 UI와 저장 구성·기존 catalog 보조 경로.
- 같은 eligible 컴퓨트의 현재 CPU/RAM/GPU 및 native/domain/project quota를 결합한 조건부 선택 범위. GPU primary와 companion 및 max_unit 유지, 소진/미확인 선택 불가 명시.
- 서버 검증 후 deterministic native flavor 저장/재사용, durable custom intent와 사용자/프로젝트별 bounded 저장 이력. 권한·graph/policy·dispatched-unknown·소유/readback 보호 유지.
- 비밀 없는 자원 옵션의 actor/home/project/surface별 browser 복원. 복원은 재검증만 수행하고 저장·VM 생성은 하지 않는다.

## Capabilities
### New Capabilities
직접 flavor 조합, 현재 same-host 조건부 자원 범위, 저장 구성 이력과 안전한 새로고침 복원.
### Modified Capabilities
VM flavor chooser 기본 동작과 관리 flavor lifecycle에 custom shape를 통합한다. 기존 ID/name/VM 참조·fresh VM admission은 보존한다.

## Impact
Backend 사용자/관리자 target API, managed flavor intent와 history, frontend wizard/API/store/9locale, tests와 ARCHITECTURE/DESIGN/API/deployment/testing 문서. 기존 RuntimeSetting을 재사용하되 mixed writer는 지원하지 않는다. SQL migration/설정 추가·자동화 자동 활성화·native quota 변경·운영 배포는 범위 밖이다. 임시 native SDK/HTTP/SQL 및 synthetic identity Chromium으로 검증하며 실제 GPU scheduling/예약을 주장하지 않는다.
