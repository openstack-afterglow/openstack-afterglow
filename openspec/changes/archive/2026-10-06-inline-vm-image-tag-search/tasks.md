## Implementation Tasks

- [x] 이미지별 태그 검색을 추가한다.
- [x] 선택한 이미지 카드를 펼쳐 바로 아래에서 태그를 선택하게 한다.
- [x] 태그를 이름·해시값·업로드 시각·용량의 단일 행 목록으로 표시한다.
- [x] current UUID·선택 불가·정렬·기존 catalog digest 소비자 계약을 유지하고 관련 회귀를 검증한다.
- [x] 실제 Chromium의 반응형·언어·theme·검색/선택 경로를 검증한다.
- [x] 상세 문서·architecture·changelog에 실제 검증 범위를 기록한다.

## Verification Evidence

- `SelectImage.test.ts` + `ImageCard.test.ts`: 2 files / 23 tests passed.
- `ImageRepositoryTrust.test.ts -t 'reveals older uploads'`: SHA-512·UUID·정확한 concrete 이미지 선택 1 test passed.
- `npm run i18n:check`: 0 errors / 0 warnings, 37 namespaces / 9149 source messages.
- 실제 dashboard layout의 `VmCreatePanel`·current source·loopback native HTTP 합성 fixture: 공백/대소문자 검색, 빈 결과, repository 전환의 검색 초기화, 선택한 repository 접기/재열기, 선택 UUID 보존, inactive 최신 업로드 차단, 태그 선택 후 자동 step 2와 이전 복귀를 확인했다.
- ko/en/ja/zh-CN × light/dark × 390/768/1440px의 24개 조건에서 각 current 태그 13개는 네 열의 단일 행이다. 행·열 정렬 차이와 페이지 가로 넘침은 0px이며 좁은 16개 조건만 목록 안 가로 스크롤을 사용한다. 실제 ArrowRight 입력으로 390px 목록의 `scrollLeft=459` 끝까지 접근했다.
- 전체 SHA title·접근성 이름, 초 단위 날짜와 전체 ISO title, 긴 태그 title, 미확인 날짜/크기 `-`를 확인했다. 증거: `~/.gstack/projects/afterglow/designs/inline-vm-image-tags-20261007/`의 screenshots·`responsive.json`·`functional.json`·`horizontal-scroll.json`.
- `DESIGN.md`, `ARCHITECTURE.md`, `docs/api/images.md`, `CHANGELOG.md`의 현재 계약을 갱신했다. 기존 완료 archive·공유 architecture-review block·실제 Git index는 보존한다.
- 초기 3파일 전체 실행에서 chooser의 빈 결과 query helper를 수정했다. 기존 trust-count의 SPAN 구현 predicate가 `AnimatedNumber` wrapper·child를 중복 매칭하는 실패는 이 변경과 무관하여 수정하지 않았다. 위 의미 있는 SHA·UUID 회귀만 별도로 통과했다. 전체 typecheck/gate·gbrain 동기화(CLI 미설치)·운영 배포·실제 OpenStack 인증/VM 생성은 수행하지 않았다.
- Scoped temporary-index architecture `--staged`: `source_sha256=4b90ab4a7a1fa67e8c263ccab3b3e83c1d706e29bf86e03e9a35ffaf5049d8a2`, 2,374 source files / 이번 source 7개 현재 내용 + HEAD. 실제 index와 공유 review block byte/hash는 유지했다. Chromium의 component 2개·catalog 4개와 현재 source SHA-256도 일치했다.
- `npm run i18n:scan`: 983 files / 3,619 hard-coded Korean lines로 실패했다. 이번 `SelectImage.svelte`·`ImageDigest.svelte`는 scan 결과에 없고 범위 밖 전역 지적은 수정하지 않았다.
- `openspec archive inline-vm-image-tag-search --skip-specs --yes`: 6 tasks complete, `2026-10-06-inline-vm-image-tag-search`로 archive 완료. Rapid schema에는 specs layer가 없으므로 no-delta proposal warning은 비차단이며 specs를 새로 만들거나 동기화하지 않았다.
- Native HTTP fixture가 기록한 439 요청은 모두 GET이며 28 image 목록·30 flavor 조회를 포함한다. VM 생성 등 mutation 요청은 0이다.
