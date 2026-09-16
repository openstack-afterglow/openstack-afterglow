## Implementation Tasks

- [x] SDK 연결 안내를 인증된 Lumen discovery 기반으로 교체하고 완전한 Python 예제 및 오류/재시도/오래된 응답 차단을 구현한다.
- [x] 연결 주소 추론 재발, discovery 실패/재시도, 세션 변경 중 stale 응답을 소비자 관점의 회귀 테스트로 검증한다.
- [x] 모바일 설정 메뉴를 가로 탭으로 배치해 SDK 코드 영역이 기존 95px로 좁아지던 문제를 수정한다.
- [x] 실제 화면에서 예제를 추출해 제공된 테스트 키로 양 SDK를 실행하고 responsive/키보드 및 관련 named target을 검증한다.
- [x] 기존 외부 API 문서와 CHANGELOG를 수정하고 문서의 Python 블록 4개를 구문 검증했다. 임시 browser 페이지·전용 Chromium process/profile 및 screenshot 7개를 제거했다.

## Verification

- `.env`의 `LUMEN_TEST_API_KEY`는 subprocess 내부에서만 읽고 출력하지 않았다. API 키 발급·폐기, TLS 우회, 서비스 배포 변경은 하지 않았다.
- 기존 `https://api.cloud.dmslab.re.kr/v1` 호출은 `APIConnectionError` → `ConnectError` → certificate name mismatch로 실패했다. 인증서 SAN은 `*.dmslab.re.kr`/`dmslab.re.kr`이며 이 호스트를 포함하지 않는다.
- Live `https://lumen.dmslab.re.kr/v1/compat`의 SDK base URL을 확인했다. OpenAI는 `https://lumen.dmslab.re.kr/v1`, Anthropic은 `https://lumen.dmslab.re.kr`이다.
- OpenAI 3.8.0: models.list HTTP 200 및 `gpt-5.6-luna` 포함, 일반 completion HTTP 200/3.47s/시 응답/59 tokens, 스트리밍 HTTP 200/1.40s/`Ocean stream OK`/stop/19 tokens.
- Anthropic 1.4.0: 일반 messages HTTP 200/1.14s/`Ocean Anthropic OK`, 스트리밍 1.27s/`Ocean Anthropic stream OK`/end_turn.
- 실제 ChatSettingsOverlay를 Chromium에서 렌더링하고 live discovery JSON을 로컬 BFF 응답 fixture로 공급했다. 두 `<pre><code>`의 textContent를 그대로 추출해 `LUMEN_API_KEY=LUMEN_TEST_API_KEY`, `LUMEN_MODEL=gpt-5.6-luna` 환경으로 실행했다. OpenAI 5.27s/56 tokens, Anthropic 2.41s/58 tokens로 각각 실제 시 응답을 출력했다. 실제 운영 BFF의 Keystone 브라우저 세션 검증과 API 키 생성/폐기는 이 시나리오에서 수행하지 않았다.
- 390/820/1440px light/dark 모두 코드 줄바꿈 보존, 본문 수평 overflow 없음, mobile 가로 탭/tablet·desktop 좌측 메뉴를 확인했다. mobile 코드 영역은 281px이며 긴 코드는 자체 스크롤한다. 503 상태에서 예제 숨김/키 관리 유지, Enter 재시도, 키보드 ArrowRight 코드 스크롤을 확인했다.
- 회귀 테스트: 수정 전 4개 실패, 수정 후 관련 3 files/9 tests 통과. named lumen: backend 19 + frontend 66 통과. design: 17 files/85 tests 통과.
- 전체 frontend Vitest: 196 files/991 tests 통과. 후속 `frontend/scripts/run-with-file-log.test.mjs:166` runner subprocess exit 기대값 검증 1개 실패(8 pass/1 fail). 해당 로깅 파일은 이 작업에서 수정하지 않았다.
- `npm run test:all`: 오케스트레이터/Kolla 검사 통과 후 backend 2640 pass/7 fail. 실패는 `test_endpoint_inventory.py`의 internal GPU admission, `test_instance_boot_from_volume.py` 4개 및 `test_instance_existing_upper.py` 1개의 Invalid flavor ID, `test_mutation_invalidate_coverage.py`의 internal_k3s cache invalidation이다. 해당 backend 파일은 이 작업에서 수정하지 않았다. 파이프라인 중단으로 후속 전체 contract/functional 단계는 실행되지 않았다.
- 커밋·푸시·배포는 하지 않았다.
