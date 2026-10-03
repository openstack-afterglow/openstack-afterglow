## Implementation Tasks

- [x] 생성/편집 입력·provider transport·직접 API 계약과 웹 자동 처리 설계를 확인한다.
- [x] 웹의 수동 생성/수정 toggle을 제거하고 첨부 없이 자동 생성하는 단일 composer를 구현한다.
- [x] 첨부와 사용자 프롬프트를 image-input 경로로 함께 보내 참고 생성/편집을 모델이 처리하게 하고 제거·업로드 실패·프로젝트 전환·intent 경계를 유지한다.
- [x] 직접 이미지 API의 endpoint·schema·인가·소유권·과금 계약을 변경하지 않고 관련 기존 회귀를 검증한다.
- [x] 실제 브라우저에서 자동 요청·입력 보존·결과·오류·반응형·테마를 확인하고 영향받는 frontend 이미지를 build/deploy해 runtime smoke를 완료한다.
- [x] 현행 문서·changelog·범위 한정 architecture review와 완료 증거·검증 한계를 갱신한 뒤 change를 archive한다.

## Verification Evidence

- Focused Afterglow `ImageStudio.test.ts`: 14 passed. 생성/첨부 요청, 명시적 제거, 업로드 지연·실패, provider 입력 거부, 프로젝트 전환과 idempotency 경계를 확인했다.
- Lumen의 기존 `tests/test_image_transport.py tests/test_image_compat_api.py`: 20 passed. 직접 생성·편집 계약과 provider transport 구현은 변경하지 않았다.
- `npm run test:lumen`: backend 41, frontend 142 passed. `npm run check --prefix frontend`: 2,117 files, 0 errors, 0 warnings.
- `npm run test:all`: orchestration 102, Kolla 26, installer 13 pass/15 PowerShell skip; backend unit 3,306, frontend unit 1,747, frontend scripts 9, contract 136, isolated functional 28 passed. 전체 `test:gate` 성공은 주장하지 않으며 이전 unrelated formatter debt는 수정하지 않았다.
- 실제 Chromium에서 source preview `:5180`와 배포 frontend `:3080`의 무첨부 `generations`, 참고 생성·원본 수정의 `edits`/입력 asset ID/사용자 prompt, project header와 intent, 결과 이미지 decode를 확인했다. 입력 가격 422 뒤 첨부 유지·자동 생성 fallback 없음, 명시적 제거 뒤 새 생성 intent, Gemini형 capability, credential 미설정·빈 모델 목록의 제출 차단과 업로드 503 뒤 미리보기 유지·제출 차단을 확인했다.
- 배포 화면의 390/767/768/1023/1024/1440px dark/light에서 가로 overflow 없음, 제출 버튼 hit test, 자동 처리 안내·수동 mode 없음과 모바일 drawer Escape/focus 복원을 확인했다. 초기 위치 검사의 실패는 viewport 변경 직후 기존 sidebar transition 중 측정한 것으로, drawer가 실제 닫힌 상태를 기다린 뒤 검증했다. CORS fixture는 mutation의 `X-Afterglow-Page` 헤더를 preflight allowlist에 포함했다.
- Canonical frontend Dockerfile의 arm64 `afterglow-local-services/frontend:current` 및 amd64 `afterglow-auto-image-qa/frontend:amd64` 빌드 완료. amd64 실행은 `arch=x64`, Studio assets와 favicon 존재를 확인했다. 빌드 로그의 npm moderate vulnerability 1건은 이 기능 범위에서 분석·해소하지 않았다.
- 기존 canonical project에서 `docker compose --env-file .local-services/compose.env --project-name afterglow-local-services -f docker-compose.dev.yml up --no-deps --no-build --wait --wait-timeout 120 frontend`로 frontend만 갱신했다. `/health` 200 `{"status":"ok"}` 및 frontend/backend healthy를 확인했고 기존 DB·volume·다른 서비스는 유지했다.
- `DESIGN.md`, `ARCHITECTURE.md`, `docs/api/chat.md`, `CHANGELOG.md`의 수동 mode 설명을 자동 composer 계약과 검증 수준에 맞춰 갱신했다.
- 임시 Git index의 HEAD + 현재 `ImageStudio.svelte`/component test 두 경로(해당 shared 파일의 선행 media composition 포함)에 범위를 한정해 architecture stamp/check를 수행했다. `source_sha256=0c359ea335517348da8616432d36a2892afa99ab31e31ab4f2316e69f0be567f`, 2,120 files의 staged check passed. 다른 dirty source의 combined freshness를 인증하지 않으며 실제 index SHA-256은 시작 값 `c72c36d9d089ad7e7543da090c73c12f584af95b100f5694a224ec98cfe80482`를 유지했다.

## Verification Limits

- API fixture와 identity는 합성이므로 실제 provider가 참고 생성/원본 수정을 이해하는지, 생성 품질·정확 과금·scanner·live OpenStack 인증을 입증하지 않는다. 유료 inference, 운영 배포, Firefox/Safari, 실제 200% browser zoom·전체 접근성 audit, commit/push는 수행하지 않았다.
- 자동 선택은 첨부 유무에 따른 기존 API 경로 선택이다. 별도 prompt 분류기·keyword heuristic·숨겨진 prompt 변환·입력 폐기 fallback은 없으며 기존의 가시 스타일 지시문은 유지한다.
- GBrain CLI는 이 환경의 PATH에 없어 optional search-index refresh를 수행하지 않았다.
