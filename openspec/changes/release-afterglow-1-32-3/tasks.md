## Implementation Tasks

- [x] 현재 dev·원격·184path public snapshot을 고정하고 private/index·후속 동시 변경을 보존한다.
- [x] 독립 backend/frontend 검토와 구조·schema/cohort 선행 조건을 확인하고 native wire/ID blocker를 실패 전후 회귀·실행으로 해결한다.
- [x] metadata1.32.3·architecture/changelog를 동기화하고 최종 전체 gate·production build·실행 smoke를 검증한다.
- [ ] 검증된 snapshot을 기본 dev에 커밋·정상 push하고 정확한 SHA CI 성공을 확인한다.
- [ ] 불변 numeric1.32.3 tag·GitHub Release·release/latest image digest/revision·Helm과 image runtime 버전을 확인한다.
- [ ] 검증 증거·운영 미배포 경계를 기록하고 own isolation을 정리·archive한다.

## Source Qualification

- Final fingerprint1ebd48228e8989d0ee63c3425ca707fe4620a631a78c1814af8a5b5d271ec038/3988files. 지원Python 전체 gate exit0(artifact729): backend12691/106skip, frontend509files6618tests, contract183, functional167/37deselected, Ruff833. Frontend check0errors/기존17warnings, i18n0/45와 production build 완료.
- Canonical amd64 backend/frontend/worker 실제 build/load·network-none/read-only/non-root runtime1.32.3. API mail401/no-store·64자 ID schema, worker import/AEAD 목적격리, frontend health/recover200·cold-source302; 실제 Chromium390px login continuation overflow0. Native Pydantic→compiled parser9events와 whole-app TCP/SQLite64자 recipient202/dedup/dispatch 검증.
- Native·관리자·SMTP는 합성이며 API lifespan off이고 운영 Kolla/native/schema/공유 DB·실물 메일·형제 repository 배포는 하지 않았다. SQL105/schema-before-writer·원 key·동일 cohort·SSO native-v2/103과 Lumen source/history 호환성은 별도 운영 선행 조건이다.
