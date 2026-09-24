## Implementation Tasks

- [x] Inspect and classify upload bytes with bounded MIME/magic/archive checks; reject unsafe inputs before promotion.
- [x] Stream an independent SHA-256, attach inspection metadata, and verify quarantine size/digest and target copy.
- [x] Integrate upload inspection into the active endpoint, retain cancel/cleanup behavior, and return structured policy/integrity errors.
- [x] Serve authorized bounded image/PDF thumbnails, with previews for supported types and safe fallback.
- [x] Add backend scanner, archive, mismatch, cleanup, and thumbnail endpoint regression tests.
- [x] Persist per-browser folder grid/table preference and manage thumbnail blob URLs across navigation.
- [x] Compose keyboard-operable grid entries with existing selection, navigation, preview, and actions.
- [x] Hash uploads in the browser and display hashing, inspection, rejection, and verified success in the queue/modal.
- [x] Add frontend preference, grid, and upload-state tests.
- [x] Run focused and full tests, build and smoke affected images, and verify browser/upload flows.
- [x] Update architecture and changelog evidence and archive the completed change.

## 검증

- [x] Focused backend — `test_object_upload_inspection.py` 26, `test_object_storage_upload.py` 25, `test_object_storage_thumbnails.py` 12 통과.
- [x] Focused frontend — grid 8, uploadQueue·navigation 15, objectViewPreference 3, design guardrail 27 통과. `svelte-check` 0 errors / 0 warnings.
- [x] `npm run test:gate` — backend 2888, frontend 1407(246 files), contract 128, functional 27, backend lint, architecture guard 통과.
- [x] 이미지 빌드·배포 — `docker-compose.dev.yml`로 backend/frontend를 arm64 네이티브 빌드하고 `--no-deps`로 재생성, backend/frontend health 200. 빌드된 image 안에서 `pypdfium2` 153.0.7999.0 렌더링과 업로드 검사 거부를 직접 확인.
- [x] 실제 RGW 업로드 — PNG/PDF/ZIP/12 MiB binary 200, 위장 PNG·경로 탈출 ZIP·PE magic 422, 체크섬 불일치 409. metadata에 `sha256`/`inspection` 노출, thumbnail PNG(320×213)·PDF(248×320) WebP 200, ZIP 415.
- [x] 실제 브라우저 — 로그인 후 그리드 기본, 폴더 카드 더블클릭 진입, 이미지·PDF 축소본 표시, 미리보기 모달(이미지/PDF embed), 목록 토글이 reload 후에도 유지. 390/768/1024/1280/1440px에서 폴더 1·2·3·4·4, 파일 2·3·4·5·5 열과 가로 overflow 0. UI 업로드에서 `SHA-256 확인` pill과 거부 메시지 확인.
- [x] 검증에 사용한 테스트 버킷·객체는 모두 삭제해 계정을 원래 상태(0 컨테이너)로 되돌렸다.

## 발견해 함께 고친 결함

- `objectBrowser.svelte.ts`의 컨테이너 초기화 `$effect`가 `loadCurrent()`를 통해 `prefix`를 의존성으로 추적해, 폴더 진입이 즉시 루트로 되돌려지고 있었다(그리드 이전부터 존재). `untrack`으로 컨테이너·프로젝트 변경에만 반응하도록 고치고 회귀 테스트를 추가했다.
- `move_to_target`의 `MetadataDirective=REPLACE`가 `ContentType`을 함께 지정하지 않아 승격된 객체의 Content-Type이 `binary/octet-stream`으로 초기화됐다(실제 RGW smoke에서 thumbnail 415로 드러남). 검사된 content type을 copy에 복원하고 계약 테스트를 추가했다.
