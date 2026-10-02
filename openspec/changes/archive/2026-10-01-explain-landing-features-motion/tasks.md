## 1. 감사와 설계

- [x] 1.1 현재 hero 미리보기, 신청→재사용 스토리, 제품 화면, 기능 그림을 실제 Chromium에서 녹화·캡처하고 F1–F9를 근거와 함께 정리한다.
- [x] 1.2 공통 시각 어휘, 패널 상태 전이, 시나리오 데이터, 연속 장면, 테스트 범위를 design.md로 확정한다.

## 2. 구현

- [x] 2.1 `LandingOpsBoard`를 콘솔형 장면(요청/정책 확인/자원/재사용 panel)으로 재구성하고 시나리오별 자원·결과 객체, 대기 상태, SVG check, toggle 계약을 구현한다.
- [x] 2.2 `LandingJourney`를 지속 객체와 단계별 detail을 가진 연속 장면으로 재구성하고 GSAP·scrub을 제거해 scroll geometry 활성화와 token 전환으로 바꾼다.
- [x] 2.3 `LandingConsolePreview`로 제품 화면 3종을 콘솔 축약 화면으로 바꾸고, plate SVG 글자를 디자인 글꼴로 렌더링한다.
- [x] 2.4 `gsap`를 `frontend/package.json`, `package-lock.json`, `bun.lock`에서 제거하고 frozen install로 확인한다.

## 3. 테스트

- [x] 3.1 `LandingOpsBoard` 단계별 panel 전이와 toggle 계약 테스트를 갱신한다.
- [x] 3.2 `LandingJourney` 단계 선택·scroll 활성화·compact fallback 테스트를 추가한다.
- [x] 3.3 `LandingPage` 행동 테스트(건너뛰기, 콘솔 목적지, brand, footer, raster 부재, 기능→워크플로우, 제품 view)와 landing AA 음성 가드를 복원한다.

## 4. 검증과 기록

- [x] 4.1 감사와 같은 조건(1440×900 dark, 390×844 mobile, 시나리오 3종, 스토리 스크롤)에서 after를 녹화·캡처해 before와 나란히 비교하고 시각 문제를 반복 수정한다.
- [x] 4.2 320–1920px 경계 폭, 1024×700, 두 테마, reduced-motion, 키보드, 200% 확대, 가로 넘침과 44px 대상을 검증한다.
- [x] 4.3 전체 frontend 테스트, Svelte check, production build, 컨테이너 이미지(arm64·amd64) 빌드와 격리 실행을 확인한다.
- [x] 4.4 DESIGN.md(Editorial surfaces·Motion 예외·landing 구성), designSystemRules 문구 assertion, ARCHITECTURE.md, CHANGELOG.md를 갱신하고 architecture freshness를 확인한 뒤 archive한다.

## 반복 수정 기록

| 회차 | 발견 | 수정 |
| --- | --- | --- |
| 1 | 대기 자원·재사용 panel이 빈 점선 상자(모바일 약 230px 공백) | 만들어질 객체를 같은 크기의 점선 계획 상태로 표시하고, 활성화 시 opacity overlay로 실체화 |
| 1 | 시나리오마다 미리보기 높이가 달라 hero가 흔들림(750/775/845px) | 클러스터·공유 데이터 행을 1.75rem으로 줄이고 세 시나리오 본문을 같은 cell에 겹쳐 높이 고정(1440 719px) |
| 1 | 1440×900에서 미리보기가 첫 화면 밖(168→918px)으로 넘침 | 머리말·요청 행·패널 간격·진행 영역 여백을 줄여 168→887px |
| 1 | 스토리 단계 전환 중 이전·다음 글자가 겹쳐 보임 | fade-through(나가는 층 fast 후 들어오는 층 시작)로 바꾸고 프레임 표본 326개에서 동시 표시 1층 이하 확인 |
| 2 | 관측·재사용 환경 카드의 마지막 줄이 라벨 없는 굵은 글자 | `지표`, `레이어` 라벨이 있는 행으로 변경 |

## Verification

- Frontend 276 files/1,892 tests + 실행 로그 9, Svelte check 2,130 files 0 errors/0 warnings, production build(client에 ScrollTrigger chunk 없음).
- Dependency: 세 manifest/lockfile이 HEAD와 동일(`gsap` 제거), `bun install --frozen-lockfile --dry-run`과 `npm ci --dry-run` 통과.
- 실제 Chromium(dedicated profile, `127.0.0.1:3087` source preview)
  - 전후 녹화·비교: `~/.gstack/projects/afterglow/designs/landing-motion-audit-20261002/compare-1-hero.png`, `compare-2-journey.png`, `compare-3-product.png`. before/after 원본은 `before/`, `after/`에 있다.
  - 320/375/390/767/768/1023/1024×700/1024×768/1280/1440/1920에서 가로 넘침 0, 장면 글자 12px 미만 0, 44px 미만 대상 0.
  - 키보드 Space/Enter 시작·정지·재개(focus 유지), 시나리오 전환 idle 복귀, 스토리 단계 Space 선택, 제품 view Enter 전환.
  - reduced-motion 즉시 완료와 compact 스토리, dark/light, 200% zoom 등가 720×450 @2x(행동 16개 모두 도달·넘침 0).
- canonical `docker-compose.dev.yml`의 격리 project `afterglow-landing-explain-qa` frontend `127.0.0.1:3089`
  - arm64와 amd64(`linux/x64`) image가 healthy·`/health` ok였다. 미리보기 전 단계·스크롤 단계·제품 view 전환·애니메이션 라이브러리 요청 0·page error 0을 확인했다.
  - 확인 후 container·network·빈 project volume 5개·QA image만 제거했다. 공유 3080 frontend와 `afterglow-local-services_*` volume은 그대로다.
- Architecture: HEAD에 이 change 파일 12개만 더한 임시 index에서 `--staged --stamp`/`--staged`를 통과했다. `designSystemRules.test.ts`는 HEAD에 이 change의 한 줄만 더한 blob으로 넣었다. `source_sha256=ffd6ee8003ce6d577921e614ed73de66bc91157a7d203957e62c51459632e5d4`, 2,122 source files. 공유 review block은 원래 값으로 복원했고 실제 `.git/index` SHA-256(`56fcbb94…5373`)은 전후 동일했다. 최종 commit 범위에서는 다시 stamp해야 한다.
