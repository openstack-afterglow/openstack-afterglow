## Implementation Tasks

> 마이그레이션 번호 주의: 착수 시점에 `053`~`056`이 커밋되지 않은 chat 플랫폼 작업에 선점돼 있다.
> Palimpsest는 **057**부터 사용하고, 파일 생성 직전 `ls backend/migrations/`로 빈 번호를 재확인한다.

### Phase 0 — OpenSpec change + Palimpsest 명명 (코드 동작 불변)

- [x] `openspec/changes/palimpsest-layered-vm/{proposal.md,tasks.md}` 생성 (rapid 스키마)
- [x] `docs/palimpsest.md` — 도메인 정의(3세대 흡수/폐기/보존 표), 용어집, digest 규칙, OverlayFS 제약
- [x] `union.md` · `docs/squashfs-layer-pipeline.md` 상단에 "Palimpsest로 통합됨" 안내 추가 (내용 삭제 금지 — 이력 보존)
- [x] `CLAUDE.md` — "Union Mount 설계" 절을 "Palimpsest (레이어드 VM) 설계"로 교체, 읽는 순서 명시, 프로젝트 구조 표에 `docs/palimpsest.md` 추가
- [x] 프론트 **사용자 대면 라벨만** 교체 — `AdminSidebar.svelte` 그룹 `라이브러리`→`Palimpsest` / 항목 `라이브러리 관리`→`레이어 관리`, `routes/admin/libraries/+page.svelte` PageHeader `라이브러리 관리`→`Palimpsest 레이어 관리`. 경로·API·타입명 불변
  > **범위 정정**: `routes/dashboard/library/**` · `lib/components/library/` · `lib/components/dashboard/library/` ·
  > `lib/types/layer.ts` · `wizard/SelectTemplate.svelte`는 **2세대 union UI**다(`/api/v1/union/layers`·
  > `/api/v1/union/templates` 호출, `LayerInfo`가 `content_hash`/`file_count` 형태). Phase 2 폐기 대상이므로
  > 리브랜딩하지 않는다 — 죽을 화면에 Palimpsest 이름을 붙이면 오해만 남는다.
  > `routes/admin/layers/`는 `/admin/libraries`로 가는 308 redirect stub이라 변경 불필요.
- [x] 게이트 확인 후 커밋 (내 파일 9개만 명시적 스테이징)
  - 백엔드 pytest `3475 passed, 79 skipped` / 프론트 vitest `810 passed (160 files)`
  - `ruff check`는 `app/services/chat/durable_runs.py` I001 1건 실패 — **미커밋 병렬 chat 작업 소유**.
    `git show HEAD:…/durable_runs.py | ruff check --stdin-filename`은 `All checks passed` → HEAD는 깨끗하고
    Phase 0은 백엔드 Python 무변경. 남의 WIP를 `--fix`하지 않는다
  - 프론트 계약 테스트 `libraries-layer-workflow.test.ts`가 옛 PageHeader 문자열을 고정하고 있어 함께 갱신

### Phase 1 — 콘텐츠 주소화

- [x] `backend/migrations/057_palimpsest_content_addressing.sql` — `layer_artifacts`에 `blob_digest` VARCHAR(71) / `blob_md5` CHAR(32) / `config_digest` VARCHAR(71) / `chain_id` VARCHAR(71) / `digest_state` VARCHAR(16) DEFAULT 'pending' + 인덱스 2개. 멱등(`information_schema` 체크), prepared stmt `palimpsest_digest_stmt`
- [x] `backend/migrations/manifest.txt`에 `057-palimpsest-content-addressing|…|<sha256>` 등록
  > 커밋 시 인덱스에는 **HEAD + 057 한 줄만** 올렸다. 작업 트리 manifest 에는 커밋되지 않은 병렬 chat 작업의
  > 053~056 항목이 들어 있는데, 그 `.sql` 파일들이 커밋에 없는 채로 manifest 만 커밋되면
  > `load_manifest()` 가 "references an invalid migration path" 로 **fail-closed** 되어 부팅·테스트가 깨진다
  > (`backend/scripts/baseline_migrations.py:59`).
- [x] 🔴 배포 순서 — dev 환경에서 ORM 이 먼저 반영되어 `Unknown column 'layer_artifacts.blob_digest'` 500 이
  실제로 재현됐고, 057 적용으로 복구했다. 적용 후 ORM SELECT 성공 / 기존 4행 `pending` / 재실행 멱등 확인
- [x] `backend/app/models/db.py` `LayerArtifact`에 신규 컬럼 추가
- [x] `services/palimpsest_digest.py` 신규 — 순수 함수(`normalize_digest`, `compute_chain_id`, `compute_config_digest`, `parse_digest_sentinels`). `scripts/layerbuild.py:131-168`의 해시 개념 이식
- [x] `services/palimpsest_layers.py` 신규 — 세션이 필요한 헬퍼(`load_lineage`/`load_ancestor_chain`/`resolve_digest_fields`/`recompute_descendant_chain_ids`). `layer_ops._artifact_lineage_rows`가 이쪽에 위임하도록 통합(계보 해석 이중화 제거)
- [x] `services/recipe_blocks.py` — 5개 squashfs 레시피 전부 `mksquashfs` 직후 `sha256sum`/`md5sum`/`stat` → `::AFTERGLOW::DIGEST::layer=<name> …` sentinel 출력. `|| true` 로 감싸 **digest 계산 실패가 빌드 실패가 되지 않게** 함(`set -euo pipefail` 환경)
  > sentinel 에 **레이어 이름을 싣는다** — Dockerfile import 는 한 번의 VM 실행으로 여러 레이어를 만들고,
  > 콘솔이 잘리면 위치 기반 매핑이 조용히 어긋나 잘못된 digest 가 붙는다
- [x] `services/layer_build.py` + `services/dockerfile_import.py` — 두 artifact 생성 경로 모두 sentinel 회수 → `digest_state='ready'`. 미확보 시 `pending` 으로 기록하고 빌드는 성공 처리
- [x] `chain_id` 계산 — 루트는 자기 digest, 이후 `sha256(parent_chain + " " + digest)`. 부모가 `pending`이면 자식 `chain_id`를 **만들지 않는다**(루트 취급하면 서로 다른 스택이 같은 chain_id 를 갖게 됨)
- [x] `backend/tests/test_palimpsest_digest.py` (36 케이스) — 정규화/검증, sentinel 이름 매핑·중복 last-wins·빈 sha256 스킵·size 누락 허용, chain_id 결정성 및 부모 민감성, config_digest 키 순서 무관, `resolve_digest_fields` 4 케이스, `recompute_descendant_chain_ids` 2 케이스, 계보 순서·사이클 방어, 5개 레시피 전부 sentinel 방출 + `|| true` 보장, ORM 컬럼/인덱스 존재
- [x] `POST /api/v1/admin/palimpsest/artifacts/backfill-digest` — `services/palimpsest_backfill.py`.
      **임시 Builder VM 한 대**로 배치 전체 처리 → share RO 마운트 → 해시 → access rule/VM 회수.
      실패는 `digest_state='failed'` + 사유, 배치는 계속. 완료 후 chain_id 재계산
  > ⚠ **계획 정정**: 계획서의 "상주 SSH Builder VM 경유"는 성립하지 않는다. `builder_vm.py` 는
  > *"Ephemeral(빌드별 임시) 경로만 지원"* 이고 상주 경로는 코드에서 제거됐다.
  > `afterglow.conf.example [builder]` 의 `persistent_server_id` / `ssh_host` / `ssh_private_key` 는
  > `config.py` 에 대응 필드가 **없는 낡은 문서**다(설정 동기화 의무 위반 — 기존 상태).
  > → 별도 정리 항목으로 남긴다.
- [x] `GET /api/v1/palimpsest/layers?digest=&digest_prefix=&md5=&chain_id=&name=&kind=` + `GET /…/{id}/ancestors`
      (공개+봉인 레이어만 노출, 미공개는 존재 여부도 흘리지 않고 404)
- [x] `GET /api/v1/admin/palimpsest/artifacts` + `GET /…/digest-status` (관리자 전용 전체 조회·분포)
- [x] `main.py` 마운트 + `_AUDIT_PREFIX_MAP` 에 `/api/v1/palimpsest`, `/api/v1/admin/palimpsest` 등록
- [x] `backend/tests/test_palimpsest_api.py` (33 케이스) — 감사 매핑·라우트 v1 단독, 검색 파라미터 9종 422,
      미인증 거부, 가시성 조건 강제, 미공개 404, 관리자 3종 403, 해시 명령 인젝션 거부(export path 4종 /
      sqsh 파일명 4종), RO 마운트 고정, 백필 성공/실패/예외 시 access rule·VM 회수

### 별도 정리 (범위 밖, 발견 사항)

- [ ] `afterglow.conf.example [builder]` 의 `persistent_server_id` / `ssh_host` / `ssh_private_key` 제거 또는
      `config.py` 필드 복구 — 현재 문서와 코드가 어긋나 있다(설정 동기화 의무). 어느 쪽이 의도인지 확인 필요

### Phase 2 — `/api/v1/palimpsest` 표면 + union 폐기

- [x] `backend/app/api/palimpsest/{layers,admin}.py` + `main.py` 마운트 + `_AUDIT_PREFIX_MAP` 등록 (Phase 1에서 완료)
- [x] 2세대 폐기 — `/api/v1/union` 마운트·감사 매핑 제거, 파일 28개 삭제:
      `api/union/layers.py`, `services/union_layers.py`, `models/union.py`,
      테스트 5종(`test_union_layers`, `test_union_layers_db`, `test_union_snapshot`, `test_layerbuild`, `test_libraries_license_db`),
      `scripts/{layerbuild.py,envmgr-init.sh,envmgr-use.sh,envmgr-rotate-key.sh}`,
      프론트 `routes/dashboard/library/**` · `lib/components/{library,dashboard/library}/` · `lib/types/layer.ts` · `wizard/SelectTemplate.svelte`
- [x] ORM `UnionLayer`/`UnionTemplate`/`UnionUserMount` 제거 + `database.py`의 union DDL 제거.
      **테이블은 보존** — DROP 마이그레이션 없음. 신규 배포는 만들지 않고, 기존 배포는 그대로 둔다
- [x] `main.py` 대시보드 집계가 비어 있던 `union_user_mounts` JOIN 대신 `layer_consumes`(status='active') 를 세도록 교체
- [x] `app/api/union/__init__.py` — 라우터 제거, 디렉터리는 유지(감사 매핑 `union_layer`·테이블명 정합)
- [x] `legacyVisualDebt.ts` 항목 15개 정리, `docs/api/union.md`·`api-reference.md`·`index.md`·`architecture.md`(ko/en) 안내 추가
- [x] 회귀 테스트 `test_second_generation_union_surface_stays_removed` — 라우트·감사 매핑·모듈·ORM 부재 + 3세대 표면 존속 고정
- [ ] ~~프론트 API 호출 경로를 `/api/v1/palimpsest/…`로 전환~~ → **보류(권고: 하지 않음)**
  > 계획서는 `/api/v1/admin/libraries`·`/api/v1/libraries/squashfs` 를 `/api/v1/palimpsest/…` 로 옮기고
  > dual-mount 후 제거하려 했다. 실제로 보니 **얻는 게 이름뿐이고 비용·위험이 크다** — 관리자 20개
  > 엔드포인트 + 공개 3개 + 프론트 전면 재배선이며, 대상은 현재 **유일하게 동작하는 레이어 시스템**이다.
  > 사용자 대면 명칭은 Phase 0에서 이미 Palimpsest로 통일됐고, `_AUDIT_PREFIX_MAP` 도 이미 매핑돼 있다.
  > 신규 능력(digest 검색·조상·백필·허브)만 `/api/v1/palimpsest` 에 두고 기존 경로는 그대로 둔다.
  > 경로까지 통일하길 원하면 별도 change 로 진행할 것.

### Phase 3 — 허브

- [x] `backend/migrations/059_palimpsest_hub.sql` — `palimpsest_hub_layers` / `palimpsest_hub_uploads` (멱등, manifest 등록).
      **059 를 쓴 이유**: 착수 직전 확인 시 `053~056` 에 더해 `058` 까지 병렬 chat 작업이 가져가 있었다.
      번호는 파일 생성 **직전**에 다시 확인한다
- [x] `services/palimpsest_hub_store.py` — `LocalPathBlobStore` + `get_blob_store()`(미설정 시 `HubStoreUnavailable` → 503).
      배치는 OCI image-layout(`<root>/blobs/sha256/<hex>`). digest·세션 ID 경로 traversal 이중 방어
- [x] `[palimpsest] hub_local_path` / `hub_max_blob_bytes` / `hub_upload_ttl_seconds` — `config.py` + `generate_k8s.py` + `afterglow.conf.example` **3곳 동시**
- [x] 업로드 세션 `POST/PATCH/PUT/DELETE /api/v1/palimpsest/hub/uploads[/{id}]` — 선언 digest 존재 시 단축 완료,
      완료 시 **수신 바이트 digest 재계산 + `hmac.compare_digest` 후 불일치 폐기(fail-closed)**, 크기 상한 초과 시 세션 폐기
- [x] 검색 `GET /hub/layers` (digest, digest_prefix, md5, chain_id, name, kind, parent_digest)
- [x] 상세 `GET /hub/layers/{digest}`(+`chain_complete`) + `GET /hub/layers/{digest}/ancestors`
- [x] blob 스트리밍 `GET /hub/layers/{digest}/blob` — HTTP Range(접두/접미 모두), 416 처리
- [x] 번들 export `POST /hub/bundles` — OCI image-layout tar 스트리밍. `layers[]` 는 루트→리프 순 부모 체인 전체,
      공통 조상은 한 번만. `tarfile.addfile` 을 쓰지 않고 헤더만 `TarInfo.tobuf()` 로 만들어 큰 blob 을 청크로 흘린다
      (addfile 은 blob 을 통째로 버퍼에 올려 메모리를 터뜨린다)
- [x] 번들 import `POST /hub/bundles/import` — 전 blob digest 재검증, 개별 실패는 skip 요약
- [x] `DELETE /hub/layers/{digest}` — 관리자. 자식 존재 시 409(union.md §10 GC 규칙 계승)
- [x] 인가 — 조회/다운로드는 공개 OR 사이트공용 OR 내 프로젝트, 그 외는 존재도 흘리지 않고 404. 업로드 세션 IDOR 방어
- [x] `backend/tests/test_palimpsest_hub.py` (42 케이스) — traversal 거부, digest 불일치 폐기, 중복 단축,
      md5 보조키, Range, 상한 초과 abort, prune, 번들 유효성/체인 전체 포함/중복 1회/왕복/크기 불일치 거부/
      unsafe 경로 거부/blob 누락 거부, API 422·404·403·503 계약
- [x] `test_mutation_invalidate_coverage` 면제 등록 — 허브는 자체 테이블+blob store 라 무효화할 캐시 네임스페이스가 없다
      (백필은 반대로 `afterglow:union_layer:*` 를 실제로 무효화한다)
- [ ] ~~`POST /hub/layers/{digest}/pull` — 허브 → 이 사이트 레이어~~ → **별도 작업으로 분리**
  > 로컬 레이어의 `.sqsh` 는 Manila share 에 있고 백엔드는 share 를 마운트하지 않는다. 허브 ↔ 로컬 artifact
  > 전송은 digest 백필과 같은 **임시 Builder VM 경유 전송**이 필요해 허브 본체와 관심사가 다르다.
  > 현재 허브는 "직접 만들어 업로드 / 검색 / 정보 조회 / 부모 추적 일괄 다운로드"를 모두 만족한다.

### Phase 5b — 베이스 cloud image 배포 + 로컬 빌드 CLI

> **목적 정정**: 로컬 KVM 은 "레이어드 VM 을 로컬에서 실행"하는 런타임이 아니라
> **사용자가 로컬에서 빌드해 허브에 올리는 환경**이다. 그러려면 빌드의 출발점인
> 베이스 cloud image 도 허브에서 받을 수 있어야 한다.

- [x] `backend/migrations/061_palimpsest_hub_cloud_images.sql` — `palimpsest_hub_layers` 에
      `disk_format`/`arch`/`os_variant` + kind 인덱스. manifest 등록, dev DB 적용·멱등 검증 완료
- [x] `kind='cloud-image'` 를 **같은 테이블**에 둔다 — 업로드 세션·digest 재검증·Range 스트리밍·
      삭제 로직이 레이어와 동일해, 테이블을 나누면 그 machinery 를 통째로 복제하게 된다.
      레이어 전용 컬럼(parent_digest/chain_id/python_version)은 NULL
- [x] mediaType 분리 — `…image.qcow2.v1` / `…image.raw.v1`. 받는 쪽이 qcow2 를 squashfs 로
      착각하면 마운트가 실패하므로 번들 manifest 에도 항목별 mediaType 을 싣는다
      (`BundleLayer.media_type`)
- [x] `GET /api/v1/palimpsest/hub/images` — 이미지 전용 필터(ubuntu_base/arch/os_variant/disk_format)
- [x] 레이어가 `base_image_digest` 로 "어떤 베이스 위에서 만들어졌는지" 선언 →
      `POST /hub/bundles` 의 `include_base_image` 로 **베이스 + 체인 전체**를 번들 하나로 수령
- [x] 검증 규칙 — cloud-image 는 `disk_format` 필수, 부모/자기 베이스 불가. 레이어는 `disk_format` 불가
- [x] `scripts/palimpsest.py` — 로컬 빌드·업로드 CLI(`images`/`layers`/`pull`/`pack`/`push`/`bundle`).
      **표준 라이브러리만** 사용(사용자가 별도 설치 불요), 셸 미사용, `pull` 은 digest 재검증 후
      불일치 시 파일 삭제, `pack` 은 백엔드 `recipe_blocks` 와 같은 mksquashfs 옵션
- [x] `docs/palimpsest-local-kvm-runbook.md` 재작성 — "받기 → 부팅 → overlay 로 변경분 분리 →
      패킹 → 업로드" 흐름. 플랫폼 관리 KVM 호스트는 부록으로 이동
- [x] 테스트 — `test_palimpsest_hub.py` +14(이미지 메타 검증·mediaType·필터·번들 항목별 타입),
      `test_palimpsest_cli.py` 17(표준 라이브러리만·셸 미사용·digest 스트리밍·mksquashfs 옵션 일치·CLI 표면)

### 별도 작업 (Phase 3 에서 분리)

- [ ] 로컬 artifact ↔ 허브 전송 — 임시 Builder VM 으로 Manila share ↔ 허브 blob store 복사
- [ ] Swift/S3 blob store 드라이버 (서비스 계정 자격증명 경로 필요 — `services/s3.py` 는 사용자 토큰 스코프)
- [ ] 방치된 업로드 세션 주기적 정리 (`prune_uploads` 를 부를 스케줄러 배선)

### Phase 4 — Dockerfile 빌드 확장

- [x] `backend/migrations/060_palimpsest_dockerfile_inline.sql` — `layer_import_jobs` 의 GitHub 전용 컬럼을
      nullable 로 완화 + `dockerfile_text`/`dockerfile_digest`/`parent_digest`, `layer_artifacts.step_digest`(+인덱스).
      manifest 등록. **dev DB 적용·멱등성 검증 완료**(적용 전 두 종류 `Unknown column` 500 재현 → 적용 후 정상)
- [x] `parse_dockerfile_source(..., allow_build_context)` 신규 + `parse_dockerfile_plan` 은 GitHub 경로 호환 래퍼로 유지
      (기존 테스트 3곳이 2-튜플을 언패킹하므로 시그니처를 깨지 않는다)
- [x] `POST /api/v1/palimpsest/builds/dockerfile` + `/dockerfile/plan`(미리보기) — **inline 은 `COPY`/`ADD` 거부**
- [x] `FROM` 해석 — ubuntu 4종 / `palimpsest/<name>@sha256:<64hex>`(부모에게서 base 상속) / `scratch` 거부
- [x] 빌드 캐시 — `step_digest = sha256(부모 참조 + "\n" + 정규화된 instruction)`.
      `apply_build_cache` 가 단계를 표시하고 `split_cached_prefix` 가 **선두 연속 구간만** 재사용한다
      (중간부터 건너뛰면 다른 스택이 된다). 전부 캐시면 409. 재사용분은 `planned_layers` 에서 빠지고
      `job.artifact_ids` 에 미리 채워져 빌드 루프가 이어 쌓는다 — 빌더 VM 오케스트레이션의 인덱스 정렬을 건드리지 않는 방식
- [x] 🔴 inline 경로 `require_admin` 유지 — 임의 셸 실행 표면. 일반 사용자 개방은 별도 결정
- [x] 캐시 무효화는 **요청 핸들러가 아니라** `run_dockerfile_import_job` 에 넣었다(artifact 가 실제로 생기는 지점).
      핸들러는 잡만 만들므로 요청 시점 무효화는 아무것도 바뀌기 전에 캐시를 비우는 셈이다
- [x] `backend/tests/test_palimpsest_dockerfile.py` (44 케이스) — inline COPY/ADD 거부 + GitHub 은 계속 허용,
      FROM 6종 거부 / palimpsest 참조 해석 / scratch 거부 / multi-stage 거부, 래퍼 하위호환,
      `_UNSUPPORTED` 7종·RUN 플래그 3종·heredoc 거부, step_digest 안정성·부모 민감성·대소문자 정규화,
      선두 구간만 재사용, base 불일치 거부, 부모 base 상속, 전부 캐시 시 409, 관리자 전용 403

### Phase 5 — 로컬 KVM 런타임 (CI 검증 불가)

- [x] `services/palimpsest_kvm.py` — 도메인 XML 생성 · seed ISO · 레이어 디스크 배치 · 게스트 조립 스크립트 ·
      libvirt 연결/정의/삭제. **libvirt 는 지연 import** — 미설치 배포에서 모듈 로드를 막지 않는다
- [x] `libvirt-python` 을 `[project.optional-dependencies] kvm` 으로 분리 (`uv sync --extra kvm`).
      시스템 libvirt-dev 를 요구하므로 기본 이미지에 넣지 않는다
- [x] `[palimpsest] kvm_uri` / `kvm_layer_root` / `kvm_state_dir` — 3곳 동시 갱신. `kvm_uri` 비면 기능 비활성
- [x] 호스트 레이어 경로 규약 = **허브 blob store 와 동일**(`<kvm_layer_root>/blobs/sha256/<hex>`).
      번들이 OCI image-layout 이라 펼친 배치가 곧 레이어 경로다 — 변환 단계가 없다
- [x] virtio-blk RO 부착 + 게스트 조립. **`/dev/vdX` 에 의존하지 않고 `/dev/disk/by-id/virtio-<serial>`** 사용
      (부착 순서와 게스트 이름 순서는 보장되지 않는다). serial 은 QEMU 가 20자로 자르므로 호스트에서 미리 자른다.
      udev 경합 대비 대기 루프 포함. lowerdir 는 루트→리프 입력을 뒤집어 넣는다
- [x] XML 은 **생성만** 한다(파싱 경로 없음) — XXE 표면이 없어 defusedxml 불필요. 이를 테스트로 고정
- [x] `docs/palimpsest-local-kvm-runbook.md` — 전제·번들 펼치기·도메인 정의·**검증 5단계**·흔한 실패 표·정리
- [x] `backend/tests/test_palimpsest_kvm.py` (32 케이스) — 경로 traversal 거부, 디스크 배치·serial 절단·한도,
      레이어 RO/루트 RW 고정, serial 전달, seed cdrom, spec 검증 5종, seed ISO 인자 리스트·비절대경로 거부·
      셸 미사용, 조립 스크립트의 by-id 사용·역순 lowerdir·로컬 upper/work·RO 마운트·udev 대기·쿼팅,
      libvirt 미설치/미설정 처리
- [ ] ⏳ **실환경 검증(수동, CI 불가)** — 런북 §4 의 5단계. 로컬 KVM 호스트에서 3단 스택 VM 부팅 →
      `lsblk`/by-id/squashfs/overlay 확인 → merged 에서 패키지 실행

### Phase 6 — OpenStack virtio (local implementation, live authentication blocked)

- [x] 승인된 read-only provider 설정 확인: Cinder RBDDriver/ceph_hdd와 Glance rbd가 구성돼 있다. 설정은 실제 clone/COW·quota·readonly attachment의 증거가 아니다.
- [x] `services/layer_block.py`·관리자 `layer_block_sources` — 봉인 exact-byte raw/bare Glance source, immutable owner/store/member/upload UUID, row-lock reservation와 artifact DELETE 경쟁·취소 drain. Non-RBD 요청은 fail-closed이고 기존 명시적 NFS 경로를 자동 fallback으로 바꾸지 않는다.
- [x] 실제 migration088/089와 manifest — artifact `block_source` 및 consume transport/run/resources/cleanup_state. 기존 NFS/null 계약 유지; 계획했던058과 `volume_ids` shortcut은 사용하지 않는다.
- [x] `layer_consume_resources` — 원본 SDK/project/expected owner fence, CREATE 전 commit·retry 억제·heartbeat·응답 유실 discovery·monotonic cleanup journal. 단건/bulk/dedicated 회수에서 managed Manila grant denial 및 bound FIP DELETE/404를 먼저 확인한다.
- [x] `layer_block_guest`·root renderer — whole virtio/RO/정확한20자 또는 full/compact UUID·ambiguity·sealed-prefix SHA256·직접 SquashFS RO mount. Upper boot/layer alias·전체 zero/signature gate와 Cinder+ext4 identity/중복 FSUUID reboot fence. 실제 initramfs prerequisite/dependency module packaging.
- [x] 즉시 block import는 admin 인가 후 planning 전에422, nonadmin403. Optional consumer 실패/취소와 봉인을 분리하고 completed exact `import_id`로 원래 artifact 계보를 소비한다.
- [x] 선택적 `transport` 요청 계약(`nfs` 기본)과 scoped pytest/real MariaDB lock/SDK-loopback regressions, opt-in `scripts/layer-block-smoke.py` 실제 help. 광역 consume_transport/virtio setting 또는 일반 사용자 endpoint를 추가하지 않는다.
- [x] 로컬 canonical backend/worker/frontend arm64·amd64 실행 및 selected app byte 일치, TCP API→native SDK→실제 MariaDB restart/recovery, 실제 CPU-only Linux virtio/OverlayFS/upper 장치명 변경/persistence·RW lower 거부·serial 없는 duplicate FSUUID 거부. `docs/testing.md`에 합성 입력·실제 실행·미검증 cloud 경계를 분리 기록한다.
- [ ] 원본 SDK 인증과 actual roles/service capability 선행 후 실제 cloud source membership·Cinder clone/COW·quota·readonly Nova attachment·Ubuntu cloud-init/SSH·재부팅 및 exact cleanup 검증. 같은 test-openrc 입력은 Keystone401이므로 unchanged retry, manual token, admin/service substitute 또는 cloud-resource 생성으로 우회하지 않는다.
- [ ] 운영 migration·writer-fenced paired SQL/CAS restore·정본 Hub cutover/권한/bytes/restart proof는 별도 승인된 배포 순서의 prerequisite 뒤에서 보류한다.
