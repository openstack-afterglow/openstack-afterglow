## Implementation Tasks

- [x] 프로젝트 관리에 전체 목록 검색·상태/도메인 필터, 결과 수·초기화·page reset을 추가하고 refresh/prefetch 조건을 보존한다.
- [x] 그룹 관리에 검색·도메인 필터, 결과 수·초기화·empty state를 추가하고 기존 관리 동선을 유지한다.
- [x] API의 전체 최신 생성순 정렬과 nullable 생성일 투영, 정확한 생성 이벤트 기록 및 inventory cache 무효화를 구현한다.
- [x] 관련 API/페이지 소비자 동작 회귀와 타입 검증을 실행하고 실제 Chromium에서 조건 조합·페이지 이동·최신순 및 responsive/theme 화면을 확인한다.

## Verification

- `npm run test:target -- access`: 143 passed.
- 프로젝트 페이지 회귀: 2 passed; Svelte check: 2,117 files, 0 errors/warnings.
- `npm run test:gate`: architecture freshness 및 테스트 단계 통과(backend 3,321, frontend 1,747, contract 136, functional 28). Ruff lint는 통과했으나 `backend/app/main.py`, `backend/app/services/layer_build.py`, `backend/tests/test_logging_contract.py`의 작업 범위 밖 기존 변경 때문에 format check가 실패했다. 해당 파일을 재포맷하지 않았다.
- 실제 Chromium→격리 FastAPI admin router·합성 Keystone inventory·SQLite에서 전역 검색/최신순 marker page, 조건 변경 page reset, status/domain AND, no-match/reset, refresh 조건 유지, 그룹 멤버 동선과 생성 후 최상단 표시를 검증했다.
- 390/767/768/1023/1024/1440px, dark/light에서 새 검색 controls가 viewport 안에 있고 document 가로 overflow가 0이었다. Lookup 실패가 Alert/결과 미확인으로 표시되고 empty/0개로 오인되지 않는 것도 확인했다.
- 실제 OpenStack 변경·운영 배포는 하지 않았고 임시 API/preview와 격리 browser를 종료했다. `gbrain`이 PATH에 없고 canonical detect executable도 없어 search-index 동기화는 미실행했다.
