## Implementation Tasks

- [x] 1. 기존 public landing, motion token, 접근성, responsive 계약을 검토하고 hero/scroll/체험 설계를 확정한다.
- [x] 2. GSAP를 public surface에 지연 로드하고 기존 semantic token/duration을 사용하는 패턴을 DESIGN.md에 정의한다.
- [x] 3. 운영 보드에 실제 API를 호출하지 않는 시나리오별 유한 환경 구성 체험, 진행 상태와 실행/정지/재실행을 구현한다.
- [x] 4. overview와 중복 method를 신청/배정/관측/재사용 스크롤 스토리로 통합하고 desktop scroll 및 compact/touch/keyboard 탐색을 구현한다.
- [x] 5. hero·기능별 workflow 진입·제품 화면 전환을 통합하고 모든 화면 폭과 reduced-motion에서 정보/액션을 유지한다.
- [x] 6. 변경된 사용자-visible 계약을 검증하고 wording/source-shape 테스트를 제거한다. 실제 Chromium에서 desktop/mobile/tablet/경계 폭/짧은 화면/두 테마/reduced-motion/키보드 및 실행 정지·재실행·시나리오 전환을 exercise한다.
- [x] 7. 확인된 소스를 ARCHITECTURE.md/CHANGELOG.md와 기존 상세 계약에 기록하고 architecture freshness를 확인한 뒤 change를 archive한다.

## Verification

- Frontend 275 files/1,876 tests + 실행 로그 9, landing 3 files/20 tests, Svelte check 2161 files 0 errors(기존 Palimpsest packages 경고 2), production build.
- 실제 Chromium: source preview `127.0.0.1:3087`; canonical `docker-compose.dev.yml` 격리 project `afterglow-landing-qa` frontend `127.0.0.1:3089`의 arm64와 amd64(`linux/x64`) image, healthy·`/health` ok. 확인 후 해당 container/network/빈 project volume/QA image만 제거했다. 공유 3080 frontend는 교체하지 않았다.
- Architecture: HEAD + 이 change 파일만 담은 임시 index에서 `--staged --stamp`/`--staged` 통과 `09ee40aa3e562b8832f62398be30616be0487dbbefae2be91ff7e747a6871769` (2120 source files). 공유 review block은 원래 값으로 복원했고 실제 `.git/index` SHA-256은 전후 동일했다. 최종 commit 범위에서는 다시 stamp해야 한다.
