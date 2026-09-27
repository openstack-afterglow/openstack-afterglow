# Palimpsest — 레이어드 VM

> afterglow가 제공하는 **레이어드 VM** 기능의 공식 명칭.
> 작성일: 2026-07-27 | 대상: 관리자 / 개발자

Docker 이미지처럼 패키지 환경을 레이어로 쌓되, 컨테이너가 아니라 **VM 안에서 OverlayFS로 직접 마운트**한다.
지운 글 위에 새로 쓴 층이 비쳐 보이는 양피지(palimpsest)에서 이름을 따왔다.

---

## 1. 왜 이 문서가 필요한가 — 레이어 서브시스템 3세대

afterglow에는 역사적으로 레이어 관련 코드가 **세 갈래**로 자라났다. 이 관계를 모르면 어느 코드를 고쳐야
하는지 판단할 수 없다.

| 세대 | 모델 (`backend/app/models/db.py`) | 주요 코드 | API | 상태 |
|------|-----------------------------------|-----------|-----|------|
| 1세대 "library" | `LibraryRecipe`(236) `LibraryBuild`(261) `LibraryCatalog`(694) | `services/library_builder.py`, `library_recipes.py` | `/api/v1/libraries` | VM 생성 위저드가 사용 중 |
| 2세대 "union" | `UnionLayer`(492) `UnionTemplate`(542) `UnionUserMount`(562) | `services/union_layers.py`, `scripts/layerbuild.py`, `scripts/envmgr-*.sh` | `/api/v1/union` | 코드만 존재, 인프라 미배포 |
| 3세대 "squashfs" | `LayerBuild`(296) `LayerConsume`(350) `LayerArtifact`(373) `LayerProfile`(469) | `services/layer_build.py`, `layer_builder.py`, `recipe_blocks.py`, `cloud_init_builder.py`, `dockerfile_import.py`, `builder_vm.py`, `manila.py` | `/api/v1/admin/libraries`, `/api/v1/libraries/squashfs` | **실제 배포·운영 중** |

### Palimpsest의 처리 방침

| 대상 | 처리 |
|------|------|
| 3세대 squashfs 파이프라인 | **흡수** — Palimpsest 코어다. 코드 경로와 스토리지 전략을 유지한 채 확장한다 |
| 2세대 union | **폐기** — `/api/v1/union` 표면과 `union_layers.py`·`layerbuild.py`·`envmgr-*.sh`를 제거한다. 다만 `union.md`의 설계 원칙(content-addressable, single-parent, 3-lock, GC 규칙)과 결정적 해시 개념은 Palimpsest로 이식한다. `union_*` 테이블은 데이터 보존을 위해 남긴다 |
| 1세대 library | **보존, 범위 밖** — VM 생성 위저드가 쓰는 카탈로그다. 건드리지 않는다 |

> **읽는 순서**: 이 문서 → `docs/squashfs-layer-pipeline.md`(운영 중인 파이프라인의 상세) → `union.md`
> (설계 원칙의 출처, 단 구현 현황 서술은 낡았음).

---

## 2. 용어

| 용어 | 의미 |
|------|------|
| **레이어(layer)** | 불변(read-only) 파일 트리 하나. squashfs `.sqsh` 파일로 봉인되어 레이어 전용 Manila NFS share에 저장된다 |
| **digest** | 레이어의 정체성. `.sqsh` blob 바이트의 sha256 → `sha256:<64hex>` |
| **chain_id** | 스택 전체의 정체성. `chain_id(root)=blob_digest(root)`, `chain_id(n)=sha256(chain_id(n-1) + " " + blob_digest(n))` |
| **부모(parent)** | 이 레이어가 그 위에 쌓인 직계 상위 레이어. 단일 상속(0개 또는 1개) |
| **봉인(seal)** | 빌드 완료 후 share의 RW access rule을 회수해 RO 전용으로 만드는 것 |
| **프로파일(profile)** | 함께 마운트할 레이어 집합에 이름을 붙인 것 (`LayerProfile`) |
| **소비(consume)** | 프로파일을 마운트한 VM을 만드는 것 (`LayerConsume`) |
| **허브(hub)** | 레이어를 digest로 저장·검색·배포하는 저장소 |
| **번들(bundle)** | 부모 체인 전체를 담은 OCI image-layout 디렉터리/tar |

---

## 3. digest 규칙

**digest = `.sqsh` blob 바이트 자체의 sha256.**

`union.md` §3.3이 제안한 "결정적 tar 해시"(같은 recipe → 같은 해시)를 채택하지 않는다. `union.md` §6.4가
스스로 결론냈듯 같은 recipe를 재실행해도 해시는 보통 달라지기 때문이다. blob digest는 대신 이 셋을 준다:

1. 이미 share에 존재하는 산출물에 그대로 적용 가능 → **백필 가능**
2. 다운로드 후 재계산만으로 **검증 가능**
3. OCI blob digest와 의미론이 같아 허브 번들이 **OCI image-layout에 그대로 매핑**

파생 값:

- `config_digest` — 레이어 메타 JSON(name/kind/ubuntu_base/packages/parent digest…)을 `sort_keys` 정규화한 sha256.
- `chain_id` — 위 표 참조. "이 스택 전체가 동일한가"를 O(1)로 비교하므로 Dockerfile 빌드 캐시와
  프로파일 중복 제거의 근거가 된다.

`blob_md5`는 외부 도구 호환을 위한 **보조 검색 키**다. 식별과 무결성의 권위는 언제나 sha256이며,
md5를 보안 목적으로 쓰지 않는다.

정책은 union.md를 계승한다 — **"재현 = 기존 레이어 재사용", "재빌드 = 새 digest로 새 레이어 추가."**
기존 레이어를 덮어쓰지 않는다.

---

## 4. 저장과 마운트

### OpenStack (운영 경로)

레이어마다 전용 Manila **NFS** share를 만들고 `.sqsh`를 넣는다. 소비 VM은 cloud-init으로 각 share를
RO 마운트 → `.sqsh` loop-mount → OverlayFS 합성한다. 상세는 `docs/squashfs-layer-pipeline.md`.

```
afterglow-layer-<name>-<token>/
  images/<name>-<ts>.sqsh
         <name>-latest.sqsh
  _build_logs/…
```

### 로컬 KVM

허브 번들을 호스트에 그대로 펼친 뒤 **virtio-blk 읽기 전용 디스크**로 붙인다. 번들이 OCI
image-layout 이므로 펼친 배치가 곧 레이어 경로다 — 변환 단계가 없다.

```
<kvm_layer_root>/blobs/sha256/<hex>     # 허브 blob store 와 같은 배치
```

게스트는 `/dev/vdX` 가 아니라 **`/dev/disk/by-id/virtio-<serial>`** 로 디스크를 찾는다. 부착 순서와
게스트 디바이스 이름 순서는 보장되지 않기 때문이다. serial 은 digest 앞 20자다(QEMU 가 20자로 자른다).

레이어 수 상한은 25개(`vdb`~`vdz`). 그 이상은 레이어를 병합하거나 EROFS 다중 blob 병합을 검토한다.

설정은 `[palimpsest] kvm_uri` / `kvm_layer_root` / `kvm_state_dir`. `kvm_uri` 가 비면 기능 비활성.
`libvirt-python` 은 별도 extra 다 — `uv sync --extra kvm`.

수동 검증 절차는 **[로컬 KVM 런북](palimpsest-local-kvm-runbook.md)** 참조. 이 경로는 CI 로 검증할 수 없다.

### virtio-blk / virtio-scsi (OpenStack) — 미구현

**Cinder는 read-only 멀티어태치를 지원하지 않는다**(2차 이후 attach는 RW, read-only 정책은 future work,
암호화 볼륨 multiattach 불가). 따라서 레이어 볼륨 1개를 여러 소비 VM에 RO로 공유할 수 없고, virtio는
NFS의 마운트 옵션 교체가 아니라 **다른 스토리지 토폴로지**(VM당 볼륨)다.

착수 게이트는 **Cinder 백엔드가 Ceph RBD인가**이다. RBD면 COW clone으로 저렴하지만, 아니면 VM당 전체 복사가
되어 비현실적이다. 구현 계획은 `openspec/changes/palimpsest-layered-vm/` Phase 6 참조.

---

## 4.4. Dockerfile 로 레이어 빌드

Dockerfile 한 편이 곧 레이어 체인이 된다. 명령 하나가 레이어 하나다(Docker 와 같은 모델).

| 소스 | 엔드포인트 | 빌드 컨텍스트 |
|---|---|---|
| GitHub (commit 고정) | `POST /api/v1/admin/libraries/imports/dockerfile` | 커밋 archive — `COPY`/`ADD` 사용 가능 |
| 업로드(inline) | `POST /api/v1/palimpsest/builds/dockerfile` | **없음 — `COPY`/`ADD` 거부** |

`POST /api/v1/palimpsest/builds/dockerfile/plan`은 캐시를 포함한 빌드 계획을 미리 본다.
`POST /api/v1/palimpsest/builds/dockerfile/lint`는 관리자 전용 읽기 검사다.
`{"dockerfile":"FROM ubuntu:24.04\nRUN true", "layer_prefix":"demo"}`를 받아
`valid`, `diagnostics` (`line`, `message`), `warnings` (`line`, `message`), `from`
(`line`, `ref`, `kind`, `image`, `parent`, `error`, `note`, `completions`) 및 `layers`
(`new`, `inherited`, `total`, `limit`, `by_instruction`)를 반환한다. 문법 오류가 여러 줄이면
한 번에 모두 보고, 해석 가능한 FROM은 문법 오류와 무관하게 미리 확인한다. `from.image`는
활성 Ubuntu Glance 이미지 목록의 항목이며 부모 참조는 `from.parent`에 계보 깊이까지 포함한다.
tag가 모호하면 `completions[].ref`를 FROM에 복사할 수 있다. 로컬 KVM 디스크 상한 25개를
넘으면 `warnings`로 알리되 OpenStack 빌드 제출을 막지는 않는다. 린트는 잡·빌드 캐시·VM을
생성하지 않고 실제 `/plan`과 빌드는 독립적으로 다시 검사한다. 인라인과 URL/파일 입력에는
빌드 컨텍스트가 없으므로 `COPY`/`ADD`를 오류로 보고한다.
`FROM` 행이 유효하지 않아도 뒤따르는 정상 지시어의 예상 레이어 수는 계속 계산한다.
부모 레이어에 Glance base image ID가 없으면 lint와 plan/build 모두 snapshot 백필 오류를 반환한다.
Glance 조회 장애는 인라인 plan/build에서 내부 오류나 자격 증명 원문을 노출하지 않고 안전한 오류로 반환한다.

### 지원하는 문법

- `FROM ubuntu:18.04|20.04|22.04|24.04` — 새 체인을 시작한다. 그 버전에 해당하는
  active Glance 이미지가 정확히 하나일 때 자동 선택한다. 같은 이름의 정확한 Glance 이미지가
  있으면 이름 조회가 먼저 적용된다. 후보가 둘 이상이면 lint가 제시한 개별 이미지 이름/UUID를
  FROM에 넣어 지정한다. 다른 Ubuntu release tag는 거부한다.
- `FROM <Glance image name:tag>` (또는 image UUID) — 현재 관리자의 Glance catalog에서 정확히
  일치하는 이름을 우선, 이어 UUID를 찾는다. 같은 이름이 여러 개면 `created_at` 최신 이미지
  (동일 시각이면 ID 순서)가 선택되며 lint에 안내한다. 선택된 이미지는 active이고 지원하는
  Ubuntu 이미지여야 한다. Dockerfile 요청에는 별도 `base_image_id` 선택 필드가 없다.
- `FROM palimpsest/<name>@sha256:<64hex>` — **기존 레이어 위에 쌓는다**. Ubuntu base 및
  Glance image ID는 부모에게서 상속한다(다른 base 위에 쌓으면 ABI가 어긋난다 — union.md §4.2).
  GitHub import에서는 이 부모 형식을 지원하지 않는다.
- `RUN` · `ENV` · `WORKDIR` — 각각 레이어가 된다. `ENV`/`WORKDIR` 는 뒤따르는 `RUN` 에 반영된다.
- `COPY` · `ADD` — GitHub 소스에서만.

거부: `FROM scratch`, multi-stage `FROM … AS`, `FROM --platform=…`, heredoc,
`RUN --mount/--network/--security`, 그리고 `ARG`/`USER`/`EXPOSE`/`CMD`/`ENTRYPOINT`/`LABEL`/`SHELL` 등.

### 빌드 캐시

`step_digest = sha256(부모 참조 + "\n" + 정규화된 instruction)`. 같은 부모 위에 같은 명령이 이미
sealed artifact 로 있으면 그 단계를 다시 빌드하지 않는다. 새 루트 단계의 부모 참조는
`glance:<image-id>`로 이미지 UUID를 포함한다(같은 Ubuntu 버전의 서로 다른 이미지 캐시 충돌 방지).
이후 단계는 부모의 `chain_id`로 스택 전체를 대표한다.

**선두 연속 구간만 재사용한다.** 중간부터 건너뛰면 다른 스택이 되기 때문이다. 모든 단계가 캐시에
맞으면 만들 게 없다는 뜻이므로 409 를 준다(기존 프로파일을 그대로 쓰면 된다).

### 🔴 보안

**inline Dockerfile 의 `RUN` 은 임의 셸 명령이다.** 실행은 격리된 임시 Builder VM 안에서만 일어나고
모든 보간이 `shlex.quote` 되지만, 그럼에도 이 경로는 **관리자 전용**이다. 일반 사용자 개방은
격리 강도·쿼터·네트워크 정책이 선행되어야 하는 별도 결정이다.

## 4.5. 허브 (레이어 레지스트리)

레이어를 digest 로 저장·검색·배포한다. `[palimpsest] hub_local_path` 를 설정해야 활성화되며,
미설정 배포에서는 허브 엔드포인트가 503 을 준다.

### 저장 배치

blob store 는 **OCI image-layout 그대로**다. 덕분에 번들이 곧 디렉터리이고, 로컬 KVM 호스트에
펼치면 바로 레이어 경로가 된다.

```
<hub_local_path>/blobs/sha256/<hex>     # 레이어 blob · config · manifest (전부 콘텐츠 주소)
<hub_local_path>/uploads/<session_id>   # 진행 중인 업로드 (완료 시 blobs/ 로 승격)
```

소비 VM 이 마운트하는 Manila share 와는 **다른 저장소**다. 허브는 백엔드가 바이트를 직접
스트리밍 read/write 해야 성립하고, share 는 VM 이 마운트하는 용도이기 때문이다.

### 엔드포인트

| 메서드·경로 | 하는 일 |
|---|---|
| `GET /api/v1/palimpsest/hub/layers` | 검색 — `digest` · `digest_prefix` · `md5` · `chain_id` · `name` · `kind` · `parent_digest` |
| `GET /hub/images` | **베이스 cloud image 목록** — `ubuntu_base` · `arch` · `os_variant` · `disk_format` |
| `GET /hub/layers/{digest}` | 상세 + 조상 요약 + `chain_complete` |
| `GET /hub/layers/{digest}/ancestors` | 루트→리프 순서 부모 체인 |
| `GET /hub/layers/{digest}/blob` | blob 스트리밍 (HTTP Range 지원) |
| `POST /hub/uploads` | 업로드 세션 시작. 선언 digest 가 이미 있으면 즉시 완료로 단축 |
| `PATCH /hub/uploads/{id}` | 청크 이어붙이기 |
| `PUT /hub/uploads/{id}` | 완료 — **수신 바이트로 digest 재계산 후 불일치면 폐기** |
| `DELETE /hub/uploads/{id}` | 세션 취소 |
| `POST /hub/bundles` | `{refs:[digest…]}` → 부모 체인 전체를 OCI image-layout tar 로 스트리밍 |
| `POST /hub/bundles/import` | 번들 업로드 → 전 blob digest 재검증 후 등록 |
| `DELETE /hub/layers/{digest}` | 관리자. **자식이 있으면 거부**(union.md §10 GC 규칙 계승) |

업로드는 OCI Distribution 의 blob upload(POST/PATCH/PUT)를 `/v2/` 없이 차용한다 — 재개 가능하고
구현자에게 익숙하다. **선언된 digest 를 신뢰하지 않는다**: 완료 시 재계산해 다르면 받지 않는다.

### 번들 = 부모 추적 일괄 다운로드

manifest 의 `layers[]` 가 **루트→리프 순서의 부모 체인 전체**이므로, "부모 레이어를 추적해 한 번에
다운로드"가 manifest 하나를 받는 것과 같아진다. 공통 조상은 콘텐츠 주소라 자동으로 한 번만 실린다.

mediaType 은 프로젝트 고유값을 쓴다 — 표준 도구가 squashfs 를 tar 레이어로 오해하지 않게:

- config: `application/vnd.afterglow.palimpsest.layer.config.v1+json`
- layer: `application/vnd.afterglow.palimpsest.layer.squashfs.v1`

### 가시성

조회·다운로드는 **공개(`is_published`) 이거나 사이트 공용(`project_id IS NULL`) 이거나 내 프로젝트**
것만 보인다. 그 외는 존재 여부도 흘리지 않고 404. 업로드 세션도 타 프로젝트가 건드릴 수 없다.

### 베이스 cloud image

허브는 레이어뿐 아니라 **빌드의 출발점인 cloud image(qcow2/raw)도 보관·배포**한다. 로컬 빌드
환경이 여기서 이미지를 받아 VM 을 띄우고 그 위에 레이어를 만들기 때문이다.

`kind='cloud-image'` 로 구분하며 저장·업로드·다운로드 machinery 는 레이어와 완전히 같다
(별도 테이블을 두면 그걸 통째로 복제하게 된다). 레이어 전용 필드는 NULL 이고, 대신
`disk_format`(qcow2|raw) · `arch` · `os_variant` 를 갖는다. mediaType 도 다르다 —
받는 쪽이 qcow2 를 squashfs 로 착각하면 마운트가 실패한다.

레이어는 `base_image_digest` 로 "어떤 베이스 위에서 만들어졌는지"를 선언한다. 그러면
`POST /hub/bundles` 에 `include_base_image: true` 를 주어 **베이스 이미지 + 레이어 체인 전체**를
번들 하나로 받을 수 있다.

### 아직 없는 것

- **OpenStack 에서 빌드한 artifact 를 허브로 올리기**. 그 레이어의 `.sqsh` 는 Manila share 에 있고
  백엔드가 마운트하지 않으므로, digest 백필과 같은 임시 Builder VM 경유 전송이 필요하다. 별도 작업.
  (로컬에서 빌드해 올리는 경로는 `scripts/palimpsest.py` 로 이미 가능하다.)
- Swift/S3 드라이버, 레이어 서명(cosign 등), `/v2/` OCI Distribution 호환 레지스트리.

## 5. OverlayFS 제약 (변하지 않는 규칙)

- **`upperdir`/`workdir`은 반드시 VM 로컬 디스크(ext4/xfs).** CephFS/NFS에 두면 조용히 깨진다 —
  overlayfs는 upperdir에 xattr, 원자적 rename, whiteout char device를 요구한다.
- `lowerdir`는 RO 네트워크 파일시스템 가능. 커널 **6.1 LTS 이상** 권장.
- `lowerdir=A:B:C`에서 **왼쪽이 최상위**다. 조상 체인(루트→리프)을 넘길 때 역순이 된다.
- 삭제는 char device 0:0(whiteout)으로 표현되므로 tar 패킹 시 `--xattrs` 필수.

---

## 6. 관련 문서

- `docs/squashfs-layer-pipeline.md` — 운영 중인 파이프라인의 빌드/소비 흐름, DB 모델, 버그 이력
- `union.md` — 설계 원칙의 출처(content-addressable, single-parent, 3-lock, GC). 구현 현황 서술은 낡음
- `openspec/changes/palimpsest-layered-vm/` — 통합 작업의 proposal과 Phase별 tasks
