## Implementation Tasks

- [x] 현재 public/auth/project/mockup 경계와 디자인·콘솔 동선을 조사한다.
- [x] Nova, Neutron, Octavia, Cinder, Manila 가이드를 source 근거로 작성한다.
- [x] Drover, Waygate, Lumen, Palimpsest 가이드를 source 근거로 작성한다.
- [x] Glance, Object Storage, Trove, Barbican 및 시작하기 가이드를 source 근거로 작성한다.
- [x] 공개 `/docs` 허브·검색·서비스별 페이지·목차·관련 문서·콘솔 링크를 구현한다.
- [x] 메인 페이지와 사용자 콘솔 공통 헤더·전체 메뉴·검색에 Docs 진입점을 연결한다.
- [x] 익명 direct navigation, 프로젝트 미선택, 인증 장애, mockup 및 잘못된 문서 slug 경계를 검증한다.
- [x] 실제 Chromium에서 본문·검색·목차·복사·양쪽 진입점과 light/dark responsive 화면을 확인한다.
- [x] 관련 frontend check/build/회귀를 실행하고 사용자 가이드·architecture·changelog를 갱신한다.

## Verification

- `npm run build`: production frontend build 통과.
- `npx vitest run src/hooks.server.test.ts src/lib/mockup/contracts.test.ts src/lib/components/__tests__/Sidebar.test.ts src/lib/components/__tests__/AdminSidebar.test.ts`: 4 files/93 tests 통과.
- `npm run check`: 2,198 files/0 errors/1 warning. Scrollable code region의 `tabindex="0"` 경고는 숨기지 않으며 실제 Chromium keyboard focus/ArrowRight horizontal scroll을 확인했다. Check/build가 동시에 `.svelte-kit/types`를 생성한 초기 ENOENT는 build 완료 뒤 직렬 check로 해소했다.
- 실제 Chromium: 14 guides와 99 section 목적지; normalized AND 본문/명령/링크 설명 검색·빈 결과·초기화; native clipboard exact bytes·거부 fallback; mobile menu/TOC·skip link·local code scrolling.
- Docs hub/article: dark/light 320,390,767,768,1023,1024,1280,1440px에서 page overflow 없음. Fully-enabled 합성 콘솔 header는 320,390,767,768,1023,1024,1279,1280,1379,1440px에서 검색·context·utility 충돌 없음.
- 익명 direct access/API unavailable, expired synthetic session, project-unselected synthetic session에서 본문을 유지하고 auth/me·refresh를 호출하지 않았다. Anonymous/authenticated unknown slug HTTP 404, `/docs-admin`의 로그인 redirect 및 tutorial docs→dashboard→docs 왕복을 확인했다.
- Optional service footer 링크는 disabled/enabled fixture에서 확인했고 Key Manager의 beta 메뉴 gate와 Barbican API service gate를 본문에서 구분한다. JSON/shell command example 9개는 syntax parsing만 수행했다.
- 사용자 가이드·README·문서 index·DESIGN·ARCHITECTURE·CHANGELOG를 갱신했다. 실제 index·공유 architecture review block은 보존하며 temporary-index scoped guard로 확인한다.
- 전체 `npm run test:gate`, 운영 배포, 실제 OpenStack 자원 변경·외부 AI provider 호출은 수행하지 않았다. Gbrain CLI 미설치로 sync는 수행하지 않았다.
