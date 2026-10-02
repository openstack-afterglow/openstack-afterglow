## Implementation Tasks

- [x] 새 SVG 자산과 기존 UI/config/배포 로고·favicon 경로를 확인하고 커스텀 브랜딩 계약을 보존한다.
- [x] 로그인·랜딩·사이드바·favicon 기본 자산, frontend/backend/배포 설정과 관련 테스트를 SVG로 교체한다.
- [x] 새 wordmark의 테마 대비·로그인 크기 제약을 적용하고 구형 bundled 자산과 RingMark를 제거한다.
- [x] 새 SVG 로고·심볼·favicon의 실제 도형 경계와 좌우 여백을 맞추고 font fallback 없이 wordmark가 표시되게 한다. Chromium `getBBox`에서 logo 좌우·상하 36, symbol 좌우 38, favicon 좌우 2를 확인했다.
- [x] 실제 Chromium에서 다크/라이트·mobile/tablet/desktop·사용자/관리자·로그인/랜딩 브랜딩을 검증하고 관련 검사·문서·아키텍처 검토를 완료한다.

## Verification

- Chromium source preview: 390/767/768/1023/1024/1440px 및 640×450 CSS viewport의 로그인·랜딩 header/footer·사용자/관리자 sidebar·관리자 preview. 반대 OS/app scheme의 wordmark pixel 대비, 비율·containment·가로 overflow, custom PNG upload/reset의 합성 API 동선을 확인했다.
- 현행 local Compose: backend/frontend만 `--no-deps --no-build --wait`로 갱신해 healthy. 실제 `/api/v1/site-config`의 세 logo 경로와 favicon이 SVG이며 `:3080` 로그인 390/640/1440px·dark/light, 랜딩 및 favicon decode를 확인했다. 세 SVG 및 backend config SHA-256이 source와 일치했다. arm64·amd64 이미지를 빌드·실행했다.
- `npm run test:all`: JavaScript 102/26/13 passed(15 skipped), backend 3306, frontend 1744, frontend scripts 9, contract 136, functional 28 passed. `npm run check --prefix frontend`: 0 errors, 0 warnings. 변경 backend 파일 Ruff 통과.
- `DESIGN.md`, `ARCHITECTURE.md`, `CHANGELOG.md`, `docs/api/system-services.md`를 갱신했다. HEAD+SVG-only source와 shared 파일의 branding hunk만 임시 index에 투영해 `check_architecture.py --staged --stamp` 및 `--staged` 통과: `source_sha256=9c58af7280c8aced65a541db94bebaa1273d2c6e05ecf87edaa36fd9632b8811`, 2116 files. 실제 Git index SHA는 그대로다.

## Verification Limits

- 관리자 브라우저의 인증·업로드·reset은 합성 identity/status API로 확인했다. 실제 admin login/DB 업로드, Firefox/Safari, 실제 browser 200% zoom·전체 접근성 audit와 운영 배포는 수행하지 않았다. 640×450는 축소 CSS viewport 증거다.
- 기존 unrelated formatter debt와 전체 dirty tree의 combined architecture review는 이번 SVG-only 검토로 해소하지 않는다. 구형 bundled 경로를 명시한 외부 운영 설정은 새 이미지와 함께 이관해야 하며 legacy alias는 없다.
- 기존 DB/volume, unrelated 서비스·코드·사용자 설정·credentials와 실제 Git index를 보존했다. commit/push와 유료 provider 호출은 하지 않았다.
