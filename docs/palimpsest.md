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

3세대 운영 상태는 기존 squashfs 경로도 포함한다. 아래 4.4의 Dockerfile 전체-root/Cinder-upper 경로는 DMSLab OpenStack에서 루트·단계 빌드, 캐시 재사용, SSH 소비 VM(`afterglow-pal-proof-20260927`, `c8b5e99e-83b5-4199-8f9f-dec2343e759d`), 재부팅 후 overlay/upper 영속성, 임시 빌더 정리까지 검증했다. Afterglow 1.29.0 백엔드·워커·프런트엔드는 Kolla에 배포되었지만, 운영자의 인증된 Dockerfile 빌드·소비 화면과 API는 아직 검증되지 않았다.

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

Dockerfile 한 편은 Glance 이미지 전체 루트(`dockerfile-root` squashfs)에서 시작하는 레이어 체인이다. FROM만 있어도 전체 루트 artifact와 profile을 만든다. 이후 지원하는 명령 하나마다 변경분(`dockerfile` squashfs) 한 개를 봉인한다. 임시 builder 자체의 `/usr`나 부팅 후 변경된 root를 FROM의 대체물로 사용하지 않는다.

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
- `FROM palimpsest/<name>@sha256:<64hex>` — 같은 Glance 이미지의 **봉인되고 digest가 준비된 전체 루트**에서 이어진 부모 체인 위에 쌓는다. `/usr` 전용 등 기존 partial-root artifact는 거부한다. Ubuntu base 및 Glance image ID를 부모에게서 상속하며, inline과 GitHub 모두 동일하게 검증한다.
- `RUN` · `ENV` · `WORKDIR` — 각각 레이어가 된다. `FROM palimpsest/<name>@sha256:…`는 부모 전체 계보의 누적 `ENV`와 `WORKDIR`를 복원하며, 자식의 상대 `WORKDIR`와 뒤따르는 `RUN`에도 반영한다. `RUN` 환경은 복합 셸 명령 전체에 전달한다.
- `COPY` · `ADD` — GitHub 소스에서만.

거부: `FROM scratch`, multi-stage `FROM … AS`, `FROM --platform=…`, heredoc,
`RUN --mount/--network/--security`, 그리고 `ARG`/`USER`/`EXPOSE`/`CMD`/`ENTRYPOINT`/`LABEL`/`SHELL` 등.

### 빌드 캐시

`step_digest = sha256("dockerfile-full-root-v2\n" + 부모 chain_id + "\n" + 정규화된 instruction)`. 실행기가 생성하는 guest 파일 형식이 바뀌어 과거 ENV 레이어를 잘못 재사용하지 않도록 v2 namespace를 사용한다. 기존 봉인 artifact의 digest/내용은 변경하지 않는다. 첫 루트는 고정 문자열이 아니라 Glance 이미지 UUID·강한 hash/checksum에 정확히 일치하는 실제 `dockerfile-root` squashfs의 blob SHA-256 및 `chain_id`로 식별한다. 실제 루트 digest가 생기기 전에는 어떠한 단계도 캐시하지 않는다. 각 명령은 직전 artifact의 `chain_id`를 부모로 삼고, GitHub `COPY`/`ADD`는 pin된 commit도 키에 포함한다.

**선두 연속 구간만 재사용한다.** 모든 단계가 캐시에 맞거나 FROM만 있는 경우에도 import job은 정상 완료되어 기존 봉인 체인을 profile에 연결한다(필요하면 SSH 소비 VM 생성). 오래된 partial-root 체인, 이미지 지문 불일치, 미봉인/미완성 digest는 캐시나 FROM 부모가 될 수 없다.


### 전체 루트 빌드와 SSH 소비

빌드는 service-project 일회용 Ubuntu builder에 **부팅하지 않은** Glance→Cinder 볼륨 복제본을 attach하고, 볼륨 serial을 확인해 read-only로 mount한다. `/dev`, `/proc`, `/sys`, cloud-init state, 머신 ID, SSH host/private key를 제외하고 전체 root squashfs를 별도 Manila NFS share에 만든다. builder는 root와 각 명령의 OverlayFS upper 변경분을 개별 share에 쓰고 byte SHA-256·MD5·size를 계산한다. 모든 단계가 성공한 뒤 첫 번째 share에 token-bound manifest를 원자적으로 저장하고 Nova console에도 보고를 시도한다. 정상 SHUTOFF를 확인한 다음 console 출력 여부와 무관하게 일회용 SSH VM에 각 share의 read-only 권한만 부여해 NFS manifest의 token·순서를 확인하고 모든 실제 squashfs 바이트의 SHA-256·MD5·size를 다시 검증한다. 실패·누락은 봉인하지 않는다. 검증 뒤 검증 VM/접근 권한, builder 접근 권한 및 임시 Nova/Cinder/Neutron 자원을 정리한 다음에만 root→명령 순서의 parent/chain digest와 profile을 한 DB 트랜잭션으로 봉인한다. 실패한 미봉인 share는 정리한다.

DMSLab Nova는 Cinder volume UUID의 하이픈을 포함한 앞 20자만 virtio serial로 노출한다. Builder와 소비 guest는 `/dev/vdX` 순서를 가정하지 않고, serial에서 하이픈을 제거한 hex 접두사(최소 17자)를 지정된 volume UUID와 대조한다. 부트 디스크·불일치·중복을 제외하며 root 복제본은 Ubuntu 파일시스템만 읽기 전용 mount하고 upper는 빈 전용 디스크만 포맷한다.

Glance 복제본은 builder 부트 이미지의 파일시스템 UUID를 그대로 가진다. `findmnt SOURCE /`가 복제본을 부트 장치로 잘못 나타내는 환경에서 builder는 실제 `/` mount의 `MAJ:MIN`과 각 block device의 `MAJ:MIN`을 비교한다. 유일한 부트 디스크를 확인하지 못하면 안전하게 거부한다.

재사용하는 각 ancestor는 읽기 전용 NFS에서 SHA-256을 검증하며 일회용 builder 로컬 디스크에 복사하고 input share를 먼저 unmount한다. SquashFS lower의 backing file은 로컬 복사본이다. 빌드 완료 시 manifest를 저장하고 lower를 해제한 뒤 `losetup -a`의 backing path가 일치하는 loop만 detach하고 output NFS share를 unmount한 후 shutdown한다. 실제 NFS-backed SquashFS loop는 `losetup -j`에서 누락되고 `losetup -a`로 detach를 시도해도 input share를 `device is busy`로 붙잡았으므로 입력 blob을 직접 loop mount하지 않는다.

Manila가 동일 share에 반환한 여러 NFS export 위치는 builder 입력/출력과 일회용 검증 VM에서 순서대로 시도한다. 각 mount 최대 15초, 전체 180초·12회전 이내이며 모든 위치가 실패하면 봉인을 거부한다. 검증 manifest 또는 byte digest가 틀리면 mount 성공과 무관하게 봉인을 거부한다. `ENV` delta는 일반 SSH의 비로그인 명령에 `sshd SetEnv`, login shell과 대화형 세션에 profile script, systemd 서비스에 `DefaultEnvironment`로 전달한다. `WORKDIR`는 이후 `RUN`과 대화형 로그인 셸의 시작 디렉터리이며 비로그인 SSH 명령에 임의 `cd`를 강제하지 않는다.

두 import API의 선택적 `consumer`는 flavor, network, server 이름과 SSH keypair 또는 public key를 받는다. SSH 공개키와 placement는 인증된 관리자 요청 중 확정하며 비밀키는 저장하지 않는다. import 응답은 `consumer_requested`, `consumer_status`, `consume_id`를 제공하고 완료 뒤 `/api/v1/admin/libraries/consumes/{id}`로 작업을 추적한다. 소비 VM은 child-first 변경분들과 전체 root를 NFS read-only·digest 검증 후 합성하고 전용 쓰기 upper를 사용한다. `/var/lib/cloud`와 머신 identity는 원래 bootstrap disk에서 유지한다. 활성화는 initramfs root overlay 부팅·재부팅 뒤 health token이 관측될 때에만 완료된다. SSH username에 `root`는 허용하지 않는다. 이미지 내용 실행과 NFS export는 관리자 권한·service project 정책에 한정한다.

전체 루트 소비자는 첫 부팅 시 각 share의 Manila NFS export 후보를 순서대로 시도하고 실제 `.sqsh` digest를 검증해 Cinder `blobs/`에 보관한 뒤 NFS를 해제한다. root fstab에 NFS 자동 마운트를 남기지 않으므로 다음 부팅은 해당 로컬 blob으로만 진행한다. 기존 `/usr` 전용 소비자의 fstab 마운트 동작은 유지한다.

Import의 `artifact_ids`와 소비 레코드는 root→delta 계보 순서로 저장한다. 소비 validation은 이 순서로 parent 연결을 확인한 뒤 guest NFS manifest에만 delta→root(child-first)로 뒤집어 제공한다. 저장된 ID를 먼저 뒤집으면 전체 루트 계보 검사에서 소비 VM 생성이 거부된다.

완료된 Dockerfile 작업 기록에서 새 VM을 실행할 때는 관리자 `POST /api/v1/admin/libraries/consume`에 `import_id`와 VM 설정을 보내며, `profile_name`을 함께 보내지 않는다. 서버는 작업에 기록된 정확한 `artifact_ids`가 모두 봉인된 연속 root→delta 계보인지 다시 확인하고 같은 IDs를 소비 레코드에 고정한다. 프로필이 나중에 다른 artifact를 가리켜도 과거 작업의 VM 내용은 바뀌지 않는다. 별도 `profile_name` 선택자는 기존 관리 API 호환용으로 유지한다.

Nova console이 없는 설치에서는 root 소비 VM의 guest health unit이 overlay `/`와 SSH 활성화를 확인한 다음 `/run/afterglow-layer-ready`에 일회용 token을 기록한다. Backend는 VM 생성 시 생성한 임시 Ed25519 공개키만 guest의 사용자 계정에 넣고, private key로 SSH에서 token·`findmnt / = overlay`·SSH active를 확인한다. SSH만으로 상태를 증명한 경우 임시 공개키 회수까지 성공해야 `active`가 된다. Console로 상태를 증명한 경우 회수는 시도하고 실패를 경고로 남긴다. 모든 경우 local private key 파일은 삭제한다. 연결·token·root 상태를 확인할 수 없으면 VM을 `active`로 기록하지 않으며 진단 가능한 VM을 보존한다. Backend에서 소비 VM의 provider IP:22에 도달할 수 있어야 console 없는 환경의 readiness proof가 가능하다.

소비 생성은 별도의 빈 Cinder volume(`upper_volume_size_gb`)을 먼저 준비하고 Nova server의 비부팅 block-device mapping(`boot_index=-1`, `delete_on_termination=true`)으로 붙인다. 첫 부팅 guest는 volume UUID의 serial과 부팅 디스크가 아닌 빈 장치를 검증한 뒤 **그 volume만** ext4로 포맷한다. NFS의 모든 `.sqsh`는 SHA-256 검증 후 같은 volume의 `blobs/`에 복사하며 upper/work도 그곳에 둔다. `layer-identity-merge.py`는 부팅하지 않은 Glance 루트에 아직 없는 첫 부팅 cloud-init SSH 계정(`ubuntu` 등)을 실제 소비자 `/`의 `/etc/{passwd,shadow,group,gshadow}`에서 `$ROOT_UPPER/etc`로 병합하고 `/home/<user>` 및 `.ssh` 소유권을 맞춘다. `$ROOT_UPPER/etc/fstab`에는 `/boot`·`/boot/efi`만 남기고 `multi-user.target.wants/layer-{activate,health}.service`와 `initramfs-tools` hook(`prereqs` 인자 처리 포함)을 보존한다. initramfs는 저장된 파일시스템 UUID로 volume을 mount해 네트워크 없이 child-first root stack을 구성한다. Nova 생성 전 실패하면 Cinder volume·port·access rule을 정리하고, 생성 후 health 실패는 VM과 진단 가능한 attached volume을 보존한다. 기존 `/usr` profile은 이 부팅 경로와 volume allocation을 사용하지 않는다.

Image-backed 부트와 별도 upper를 함께 요청할 때는 Nova BDM에 Glance 이미지와 일치하는 `image→local, boot_index=0` 항목, 그리고 `volume→volume, boot_index=-1` upper 항목을 모두 보낸다. 비부팅 볼륨만 BDM으로 전달하면 실제 Nova가 부트 순서를 거부한다.

### 🔴 보안

**inline Dockerfile 의 `RUN` 은 임의 셸 명령이다.** 실행은 격리된 임시 Builder VM 안에서만 일어나고
모든 보간이 `shlex.quote` 되지만, 그럼에도 이 경로는 **관리자 전용**이다. 일반 사용자 개방은
격리 강도·쿼터·네트워크 정책이 선행되어야 하는 별도 결정이다.

GitHub context는 커밋 SHA를 고정하고 archive path traversal·link·special entry를 거부한다. 압축 archive 50MiB, 압축 해제 일반 파일 총량 512MiB, entry 5000개가 상한이다. 이 경로는 임의의 GitHub 저장소/스크립트를 관리자 권한의 일회용 builder에서 실행하므로 신뢰할 수 있는 소스만 선택한다.

## 4.5. 허브 (레이어 레지스트리)

레이어를 digest로 저장·검색·배포하는 기존 Hub와 4.6의 프로젝트 package registry는 다른 모델이다.
현행 Afterglow는 독립 Hub의 BFF이며 `service_palimpsest_enabled`로 기능을 제한한다.
일반 legacy JWT Hub 경로는 설정 URL 또는 caller catalog를 사용하지만, browser package BFF와 native key gateway는
신뢰된 `SERVICE_PALIMPSEST_INTERNAL_URL` / `[services] palimpsest_internal_url`이 필수이고 없거나 비면 503이다.
이전 Afterglow 로컬 설정 `[palimpsest] hub_local_path`는 현행 Hub 활성화 조건이 아니다.

### 저장 배치

blob store 는 **OCI image-layout 그대로**다. 덕분에 번들이 곧 디렉터리이고, 로컬 KVM 호스트에
펼치면 바로 레이어 경로가 된다.

```
<Hub blob store>/blobs/sha256/<hex>     # 레이어 blob · config · manifest (전부 콘텐츠 주소)
<Hub blob store>/uploads/<session_id>   # 진행 중인 업로드 (완료 시 blobs/ 로 승격)
```

소비 VM이 마운트하는 Manila share와는 **다른 저장소**다. 독립 Hub가 blob 저장·read/write를 소유하고,
Afterglow는 인증된 BFF로 바이트를 스트리밍한다. Afterglow 백엔드가 Hub filesystem을 소유하거나 직접 마운트하지 않는다.

### 엔드포인트

아래 `/hub/...`는 Afterglow `/api/v1/palimpsest` 아래의 legacy JWT Hub 경로다.
프로젝트 패키지의 browser API와 native key allowlist는 별도이며 이 레이어 API 전체를 key에 개방하지 않는다.


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

## 4.6. 프로젝트 패키지와 내 접근 키 (`/palimpsest/packages`)

사용자 Palimpsest 메뉴의 **프로젝트 패키지**는 선택한 프로젝트의 **비공개 Hub inventory**다.
OCI 이미지와 런타임 번들을 조회하며, CLI로 게시한 패키지는 별도 승인 없이 나타난다.
관리자 `/admin/libraries`의 Dockerfile 빌드·artifact/profile·VM 소비 파이프라인이나 기존 VM 위저드의
library 카탈로그를 대체하지 않는다. 관리자 화면의 **프로젝트 패키지 / 접근 키** 링크도 이 페이지로 연결된다.

- **목록**: `xl` 이상은 **패키지 / 유형**, **태그 / digest**, **플랫폼**,
  **검증된 크기 / 최근 게시**, **작업**의 다섯 열 표이고, 그 아래는 카드다.
  표의 태그·최근 digest는 앞 19자(`sha256:` + 앞 12자리 hex) 뒤에 `…`를 붙여 줄인다.
  title·카드·상세·복사 값은 전체 digest를 유지한다. 크기는 최신 버전의 검증된 descriptor graph 크기다.
- **상세 / 이력**: 버전 이력과 태그 해석, 전체 root digest·플랫폼·게시자/시각·미디어 유형,
  graph/다운로드 크기, 클라이언트 출처 정보와 검증된 descriptor graph를 보여 준다.
  이 root digest는 패키지 버전 식별자이며 위의 단일 `.sqsh` blob digest와 구별한다.
  다운로드는 브라우저 access JWT와 선택 프로젝트로 `/api/v1/palimpsest/packages`의 버전 다운로드를
  요청하는 인증된 tar 다운로드다. BFF는 현재 namespace와 버전 metadata의 project/package/digest를 먼저 대조한다.
- **불변 참조 복사**: `<package_authority>/<namespace>/<package>@sha256:<64hex>` 형식이며,
  Hub context가 반환한 신뢰된 `package_authority`만 사용한다. 근거는 Hub 운영자가 설정한 HTTPS
  `palimpsest_hub_package_public_origin`의 authority(host[:port])다. 브라우저 origin·요청 Host·Afterglow/Hub
  internal URL로 추측하거나 대체하지 않는다. authority가 `null`이면 복사만 비활성이고 조회·인증된 다운로드는 유지된다.
- **namespace 등록**: 자동 등록하지 않는다. 미등록 상태에서 `capabilities.packages_write`가 있을 때만
  사용자가 명시적으로 등록한다(`PUT /api/v1/palimpsest/packages/namespace`). 읽기 쉬운 namespace는 Hub 운영자의
  `palimpsest_hub_package_namespace_bindings`에 namespace → 정확한 프로젝트 UUID/ID 바인딩이 필요하며,
  프로젝트 표시 이름에서 유도하지 않는다. 기본 namespace도 프로젝트 ID에서 생성한다. project/user ID는
  UUID로만 한정하지 않는 opaque 식별자이며 정규화·소문자 변환·하이픈 제거 없이 정확히 비교한다.
- **내 접근 키**: `/api/v1/palimpsest/package-keys`로 현재 프로젝트에서 **인증된 본인이 소유한 키만**
  발급·목록·폐기한다(프로젝트 소유자/관리자라는 이유로 다른 사용자의 키를 관리하지 않는다).
  발급은 `keys_issue`로 제한하며 정확한 패키지 이름 또는 명시적 전체 프로젝트 범위, 패키지/캐시별 읽기·쓰기,
  1–90일 만료를 선택한다. 쓰기 위임에는 `packages_write`가 필요하다. secret은 발급 응답에서 한 번만 표시하고
  브라우저 메모리에만 보관하며, 명시적 닫기·탭/페이지 이동·pagehide·프로젝트 전환·로그아웃에서 화면 상태를 폐기한다.
  이는 키 자체의 폐기(revoke)와 별개이며, 사용자가 복사한 클립보드/외부 저장소 값까지 지우는 것은 아니다.
- **늦은 응답 차단**: `ProjectSelector.svelte`는 rescope 요청 전에 `auth.ts`의 `projectSwitching`을 설정한다.
  패키지 controller는 이전 목록·상세·키·secret을 즉시 비우고 요청을 abort한다. project/user identity,
  generation과 요청 lane 소유권을 대조하며, 별도 secret generation으로 닫힌 화면에 늦은 발급 응답이 secret을
  다시 표시하지 못하게 한다. 같은 project/user의 JWT 갱신 자체는 identity 전환으로 취급하지 않는다.
  공유 전환 상태는 selector의 unmount/remount에도 유지하여 동시 rescope를 막습니다. 전환 중 로그아웃·identity 변경이 있었다면 같은 사용자·프로젝트로 재로그인해도 이전 전환 응답을 적용하지 않고, 동일 identity의 JWT refresh는 허용합니다.

브라우저 package 경로는 단일 Bearer access JWT만 받고 `ppk_v1_` 키와 `X-Auth-Token` 입력은 거부한다.
BFF는 JWT·세션·선택 프로젝트의 정확한 project/user ID를 대조하고 원본 세션 Keystone subject token을 Hub에
전달한다. 이 경로는 token exchange·admin override·project rescope·세션 token/scope 재작성을 하지 않는다.
일반 ProjectSelector의 프로젝트 전환은 별도 인증 동작이며, 패키지 요청이 scope를 바꾸는 것과 구별한다.
namespace 등록·키 소유권/위임 권한의 최종 인가는 Hub가 수행하고, Afterglow는 성공 응답의 소유권을 대조한다.

일반 JWT의 `/api/v1/palimpsest/hub/...` catch-all은 기존 root/health·layers·images·image-exports·uploads·bundles·builds만 허용합니다. Native projects·keys·cache control과 `/auth/me`는 token exchange·rescope·upstream 호출 전에 403으로 거부합니다. Native browser 작업은 위 dedicated BFF를 사용하고, 기존 unauthenticated export-ticket 다운로드는 유지합니다.

Native CLI key gateway는 단일 `Bearer ppk_v1_…`와 method/path allowlist를 사용합니다. 단일 `X-Project-Id`는 Hub로 그대로 전달해 key의 실제 scope와 대조하며, 같은 값의 중복 헤더도 401로 거부합니다. Browser JWT·Keystone 자격을 이 경로와 혼용하지 않습니다. 두 package transport는 명시적으로 설정된 trusted internal Hub URL만 사용하고 redirect 없이 `private, no-store`로 응답합니다. HTTPS는 `os_cacert` 또는 시스템 CA로 항상 검증하며 `os_insecure`로 비활성화하지 않습니다. CA/client 초기화나 transport 오류는 자격·내부 예외를 노출하지 않고 503으로 반환합니다.

사용자 tutorial에는 native package fixture가 없으므로 해당 메뉴를 노출하지 않습니다. 일반 로그인 사용자의 프로젝트 패키지 탐색은 유지합니다.

구현 근거: `frontend/src/routes/palimpsest/packages/+page.svelte`,
`frontend/src/lib/stores/palimpsestPackagesController.svelte.ts`, `frontend/src/lib/api/palimpsestPackages.ts`,
`backend/app/api/palimpsest/{packages,package_keys}.py`와 독립 Hub의 package registry/config.
이 절은 현재 소스 계약을 설명하며 운영 환경의 실시간 검증 결과를 주장하지 않는다.

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
