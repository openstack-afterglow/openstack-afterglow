# squashfs/NFS 레이어 파이프라인

> **이 파이프라인이 Palimpsest 코어다 (2026-07-27 통합).**
> 도메인 정의·용어·digest 규칙은 **[`palimpsest.md`](palimpsest.md)** 를 먼저 읽는다.
> 이 문서는 그 코어의 **빌드/소비 흐름·DB 모델·버그 이력**을 다룬다.

afterglow의 squashfs + OverlayFS + Manila NFS 레이어 시스템.  
레이어마다 전용 Manila NFS share를 동적 생성해 `.sqsh`를 저장하고, 빌드 후 RO로 봉인(sealed)한다.  
소비 VM은 체인의 N개 share를 마운트해 OverlayFS로 합성하고 즉시 사용한다.

---

## 아키텍처 개요

### 레이어 체인 구조

```
uv (base, kind=uv)
  └── python3.11 (kind=python, parent=uv)
        └── torch (kind=packages, parent=python3.11)
        └── data-science (kind=packages, parent=python3.11)
```

- **`kind=uv`**: 루트 레이어. `uv` 바이너리만 포함. 부모 없음.
- **`kind=python`**: uv 레이어를 부모로 가짐. CPython 인터프리터 트리만 포함.
- **`kind=packages`**: python 레이어를 부모로 가짐. pip 패키지 delta만 squash.

### per-layer Manila share 구조

레이어마다 별도의 NFS share를 동적으로 생성한다.

```
afterglow-layer-uv-<token>/
  images/
    uv-20260625103011.sqsh
    uv-latest.sqsh  → uv-20260625103011.sqsh

afterglow-layer-python311-<token>/
  images/
    python311-20260625103244.sqsh
    python311-latest.sqsh
  _build_logs/
    cloud-init-output.log   ← 성공 빌드만
    error.txt               ← 실패 시 _on_error trap이 기록 (최근 200줄)
```

### Manila share 메타데이터 라벨

```json
{
  "afterglow_role": "union-layer",
  "layer_name": "python311",
  "kind": "python"
}
```

`list_file_storages(metadata_filter=...)` 로 stateless 재발견 가능.  
DB `LayerArtifact.share_id`가 운영상 1차 포인터이고, 메타데이터는 자기기술/고아정리/DB재구성 용도.

---

## 빌드 흐름

### 1. 빌드 요청 (관리자 UI / API)

```
POST /api/v1/admin/libraries/build
{
  "name": "python311",
  "kind": "python",
  "python_version": "3.11",
  "parent_layer_id": 1   ← uv 레이어 LayerArtifact.id
}
```

### 2. 오케스트레이션 (`layer_build.run_layer_build`)

```
1. parent_artifact_id → DB에서 조상 체인 역추적 (child-first 순서)
2. Manila 신규 share 생성
   - proto=NFS, share_type=설정값, metadata 라벨 포함
   - 60×5s available 폴링 (error 시 즉시 정리)
3. 신규 share에 빌드 VM IP RW access rule 부여 → export_path 획득
4. 조상 share들에 RO access rule 부여 → export 목록 수집
5. cloud-init user-data 생성 (레시피 → 셸 스크립트)
6. Nova VM 생성 + port → 부팅
7. ACTIVE 중 30s마다 콘솔 폴링 → SUCCESS/FAILURE sentinel 감지
   - sentinel 감지 즉시 500줄 console_log_excerpt DB 저장
8. SHUTOFF 대기 (최대 20분)
9. 성공:
   - RW access rule 회수 (봉인 = RO-only 상태)
   - LayerArtifact DB 기록 (share_id, parent_id, is_sealed=True, sqsh_filename)
   - Manila metadata sealed=true 갱신
10. 실패/finally 정리:
    - 빌드 VM RW access rule 회수
    - 조상 RO access rule 회수
    - server + port 삭제
    - 실패 시 신규 share 삭제 (고아 방지)
```

### 3. 레시피 종류

| 종류 | 함수 | 동작 |
|------|------|------|
| `kind=uv` | `squashfs_uv_layer` | uv 바이너리 → staging → mksquashfs |
| `kind=python` | `squashfs_python_layer` | uv python install → CPython 트리 → mksquashfs |
| `kind=packages` (stacked) | `squashfs_stacked_layer` | 부모 NFS RO 마운트 → OverlayFS → 패키지 설치 → upper만 mksquashfs |

### Stacked 빌드 상세 (packages 레이어)

```bash
# 조상 체인 NFS RO 마운트
mount -t nfs4 -o ro <parent0_export> /mnt/parent/0
mount -t squashfs -o ro /mnt/parent/0/images/<sqsh> /mnt/lower/0
...

# OverlayFS 합성 (index 0 = 직계 부모 = 스택 최상위)
mount -t overlay overlay \
  -o lowerdir=/mnt/lower/0:/mnt/lower/1:...,upperdir=/mnt/upper,workdir=/mnt/work \
  /mnt/merged

# 부모의 python으로 패키지 설치 → copy-up으로 /mnt/upper에만 기록
$UV_BIN pip install --python "$PYBIN" --system --no-cache torch

# delta(upper)만 squash → 새 레이어 share에 저장
mksquashfs /mnt/upper /mnt/share/images/<name>-<ts>.sqsh -comp zstd -Xcompression-level 3
```

---

## 소비 흐름

### 소비 VM cloud-init

각 레이어 share를 NFS RO로 마운트 후 loop-mount + OverlayFS 합성:

```bash
# 레이어별 NFS 마운트
mount -t nfs4 -o ro <layer0_export> /mnt/nfs-layers/0
mount -t nfs4 -o ro <layer1_export> /mnt/nfs-layers/1

# layer-activate.sh: loop-mount → OverlayFS
mount -o ro,loop /mnt/nfs-layers/0/images/uv-latest.sqsh /mnt/lower/0
mount -o ro,loop /mnt/nfs-layers/1/images/python311-latest.sqsh /mnt/lower/1
mount -t overlay overlay -o lowerdir=/mnt/lower/0:/mnt/lower/1,... /opt/layers/merged
```

---

## cloud-init 오류 진단

### 빌드 실패 시 로그 수집 흐름

```
빌드 스크립트 실패
  └── _on_error trap 실행
        └── tail -n 200 /var/log/cloud-init-output.log > /mnt/share/_build_logs/error.txt
  └── runcmd 실패 경로:
        echo "---AFTERGLOW-ERROR-LOG-BEGIN---"
        cat /mnt/share/_build_logs/error.txt   ← 오류 직전 200줄 콘솔에 출력
        echo "---AFTERGLOW-ERROR-LOG-END---"
        umount /mnt/share
        echo "::AFTERGLOW::FAILURE::<token>::rc=N"
```

### 오케스트레이터 콘솔 폴링

- ACTIVE 상태 30s마다 500줄 콘솔 캡처
- SUCCESS/FAILURE sentinel 감지 즉시 최대 4000자 DB 저장
- SHUTOFF 후 None → 500 → 200줄 순서로 폴백 시도
- 이미 저장된 excerpt는 빈 값으로 덮지 않음 (`if excerpt:` guard)

---

## DB 모델

### `LayerArtifact` (per-layer share 방식)

```python
class LayerArtifact(Base):
    id: int (PK)
    name: str              # 레이어 이름 (예: "python311")
    kind: str              # "uv" | "python" | "packages"
    python_version: str    # "3.11" 등 (python/packages 레이어)
    sqsh_filename: str     # "python311-latest.sqsh"
    share_id: str          # Manila share UUID (레이어 전용)
    parent_id: int | None  # 직계 부모 LayerArtifact.id
    is_sealed: bool        # True = RO 봉인 완료, 소비 가능
    build_id: int | None   # LayerBuild FK
```

> **마이그레이션 노트**: `parent_id`, `is_sealed` 컬럼은 SQLAlchemy `create_all`로 자동 생성되지 않는다.
> 기존 테이블이 있을 경우 `backend/migrations/017_layer_artifacts_stacked.sql` 적용 필요.

### `LayerBuild` (빌드 작업 추적)

```python
class LayerBuild(Base):
    id: int (PK)
    layer_name: str
    status: str            # "queued" | "running" | "complete" | "error" | "cancelled"
    progress_pct: int      # 0~100
    cloud_init_status: str
    console_log_excerpt: str  # 빌드 완료/실패 후 캡처된 로그
    share_id: str          # 이 빌드에서 사용한 Manila share
    vm_id: str
    vm_ip: str
```

---

Dockerfile import는 기존 `/usr` 전용 `uv`/`python`/`packages` 체인을 재사용하지 않는다. 서비스 프로젝트의 임시 builder는 active Ubuntu Glance 이미지에서 생성한 **부팅하지 않은** Cinder 볼륨을 volume serial로 식별하고 read-only mount한다. `/var/lib/cloud`, `/etc/machine-id`, host/private SSH key 등 VM별 비밀과 런타임 mount를 제외한 파일시스템 전체를 `kind=dockerfile-root` squashfs로 보관한다. FROM만 있는 계획도 이 root artifact와 profile을 봉인한다. GitHub는 commit pin archive를 받고 inline 파일은 빌드 컨텍스트가 없으므로 COPY/ADD를 허용하지 않는다.

DMSLab Nova는 Cinder volume UUID를 하이픈이 포함된 20자 virtio serial로 잘라 노출한다. Guest는 `/dev/vdX` 순서를 가정하지 않고 serial의 하이픈을 제거한 최소 17자 hex 접두사를 해당 volume UUID와 대조한다. 부트 디스크·다중 일치 항목은 거부하고, Glance 복제본은 Ubuntu root partition만 read-only mount한다. 소비 upper는 같은 방법으로 식별한 **빈 전용 디스크**만 포맷한다.

Glance→Cinder 복제본은 builder 부트 이미지와 root 파일시스템 UUID가 중복되므로 `findmnt SOURCE /`로 부트 디스크를 식별하지 않는다. Builder는 실제 mount의 `MAJ:MIN`을 `lsblk` 파티션의 kernel 장치 번호와 대조하고 확인되지 않거나 여러 개인 경우 실패한다.

Builder는 각 cached ancestor를 NFS에서 SHA-256을 계산하며 로컬 일회용 디스크로 복사·검증하고 입력 share를 즉시 해제한 다음 로컬 blob을 squashfs lower로 mount한다. Manifest 기록 후 cached·new lower를 해제하고 `losetup -a`의 정확한 backing path로 해당 loop만 detach한 뒤 출력 NFS를 unmount하고 shutdown한다. NFS에서 `losetup -j`가 loop를 놓치고 명시적인 `losetup -d` 뒤에도 NFS-backed loop가 input share를 `device is busy`로 붙잡는 사례가 있어 입력 blob을 직접 loop mount하지 않는다.

각 RUN/COPY/ADD/ENV/WORKDIR는 이미 완성된 child-first squashfs stack 위의 OverlayFS upper만 자신의 Manila share에 squashfs로 기록한다(`kind=dockerfile`). 삭제는 upper의 overlay whiteout·opaque metadata에 남으므로 root+모든 변경분을 child-first로 다시 합성할 때 삭제된 root 파일이 되살아나면 안 된다. Builder는 마지막 단계 뒤 첫 share에 빌드 token과 모든 새 레이어의 byte SHA-256/MD5/size가 있는 manifest를 원자적으로 기록하고 console 출력도 시도한다. 정상 SHUTOFF 이후 Nova console 내용에 관계없이 read-only 일회용 검증 VM으로 manifest token·계획 순서와 **실제 각 blob 바이트**의 digest/size를 확인해야 한다. 누락·불일치·접근 오류는 실패로 처리하고 검증 VM/임시 access rule을 제거한다. 그 뒤에만 writable share 권한을 거두고 임시 VM·volume·port를 정리한 뒤 한 트랜잭션으로 `blob_digest`, `chain_id`, `digest_state=ready`, parent link, profile을 기록한다. 기존 sealed full-root 계보만 캐시와 FROM 부모가 된다. 같은 Glance UUID라도 강한 hash/checksum이 바뀌면 root snapshot을 다시 생성한다.

부모 FROM은 root-first 계보 전체를 새 작업의 cached ancestor로 전달하고 각 ancestor의 누적 `ENV`·`WORKDIR` 메타데이터에서 실행 상태를 복구한다. 새 단계의 `RUN`은 해당 환경과 현재 작업 디렉터리를 실제 chroot 프로세스에 적용한다. `ENV` 단계는 비로그인 SSH/로그인 셸/systemd 서비스별 환경 파일을 생성하고 `WORKDIR`는 대화형 로그인 셸의 시작 경로를 기록한다. Manila가 반환한 NFS export 위치가 여러 개면 builder 입력·출력과 일회용 검증 VM은 첫 위치의 mount 실패 시 나머지 위치를 시도한다. 최대 12회전·180초, 각 mount 최대 15초로 제한하고 모든 위치가 실패하거나 manifest/digest가 틀리면 artifact를 봉인하지 않는다.

선택적 SSH 소비는 `layer_import_jobs.consumer_spec`(공개키와 검증된 placement, private key 없음)과 `consume_id`로 import에 연결된다. `layer_consumes`는 **별도 Cinder upper volume**(Nova 비부팅 BDM, VM 삭제 시 삭제)에 검증된 sqsh·OverlayFS upper/work를 저장한다. 첫 부팅에 실제 부착 volume serial/빈 장치를 확인한 후 ext4를 생성한다. 전체 루트 소비는 각 share의 모든 검증된 Manila NFS export를 순차·유한하게 시도하고, 읽어 온 바이트의 digest를 대조한 뒤 NFS를 해제한다. root에는 NFS fstab 자동 mount를 남기지 않으며 initramfs는 파일시스템 UUID로 Cinder volume을 찾아 재부팅 시 NFS에 의존하지 않고 child-first root stack을 구성한다. health token은 새 root에서만 나타나야 active가 된다. boot 디스크의 cloud-init state와 머신 고유 값은 합성 root에 덮이지 않는다. Nova 생성 전 오류는 전용 volume·port·share 접근을 철회하고, 생성 후 오류는 진단 가능한 VM을 남긴다. 기존 `/usr` 전용 profile의 fstab/소비/빌드 경로는 별도로 유지한다. 관리자 입력·엔드포인트는 [Palimpsest Dockerfile 계약](palimpsest.md#44-dockerfile-로-레이어-빌드)에 있다.

Nova의 image-backed root 소비 BDM은 `image_id`와 동일 UUID의 `image→local, boot_index=0` 부트 entry를 명시하고, upper Cinder 볼륨은 `volume→volume, boot_index=-1`로 별도 지정한다. 비부팅 upper만 명시하면 Nova가 부팅 디스크를 찾지 못해 400을 반환한다.

`layer_import_jobs.artifact_ids`와 `layer_consumes.artifact_ids`는 root→delta 순서다. 소비 서비스는 이 순서에서 root·parent 연결을 검증하고 guest manifest를 만들 때만 역순(delta→root)으로 mount와 digest를 내보낸다.

Nova serial console이 404/공백인 경우 root 소비 VM은 `layer-health.service`가 post-reboot overlay `/` 및 SSH 상태를 확인한 뒤 `/run/afterglow-layer-ready`에 쓴 token을 일회용 backend SSH 키로 읽어 비교한다. 비교는 SSH로 보낸 명령에 token을 포함하지 않고 backend에서 수행하며 `findmnt /`의 `overlay`와 SSH `active`도 검사한다. Backend가 VM의 fixed IP SSH에 도달하지 못하거나 파일/값이 틀리면 성공으로 간주하지 않는다. SSH 증명 경로에서는 VM authorized_keys의 일회용 항목 회수 실패도 성공으로 처리하지 않는다. Console만으로 증명한 경우 회수를 시도하고 실패를 경고하며, local private key는 모든 경로에서 삭제한다. 기존 `/usr` 소비는 console 완료 계약을 유지한다.

## API 엔드포인트

모든 엔드포인트: `Depends(require_admin)` 필수. 경로 prefix: `/api/v1/admin/libraries`

| 메서드 | 경로 | 동작 |
|--------|------|------|
| `POST` | `/build` | 레이어 빌드 시작 |
| `GET` | `/builds` | 빌드 목록 |
| `GET` | `/builds/{id}` | 빌드 상세 + 콘솔 로그 |
| `POST` | `/builds/{id}/cancel` | 빌드 취소 |
| `GET` | `/artifacts` | 봉인된 레이어 artifact 목록 |
| `POST` | `/consume` | 소비 인스턴스 생성 |
| `GET` | `/consumes` | 소비 인스턴스 목록 |

---

## 설정 (`afterglow.conf`)

```toml
[builder]
layer_share_size_gb = 20        # 레이어별 Manila share 용량 (기본 20GB)

[union]
# 레거시 — per-layer share 방식에서는 필수 아님 (미설정 허용)
# layer_store_rw_share_id = ""
# layer_store_ro_share_id = ""
```

---

## 소스 파일

| 파일 | 역할 |
|------|------|
| `backend/app/models/db.py` | `LayerArtifact`, `LayerBuild`, `LayerProfile`, `LayerConsume` |
| `backend/app/services/recipe_blocks.py` | `squashfs_uv_layer`, `squashfs_python_layer`, `squashfs_stacked_layer`, `python_layer`, `pip_layer`, `apt_capture_layer` |
| `backend/app/services/cloud_init_builder.py` | cloud-config YAML 렌더러 (runcmd, sentinel, NFS/CephFS mount) |
| `backend/app/services/layer_build.py` | `run_layer_build`, `run_layer_consume`, `_wait_for_shutoff`, 콘솔 폴링 |
| `backend/app/services/layer_builder.py` | asyncio 백그라운드 태스크 관리, 취소 처리 |
| `backend/app/services/manila.py` | `ensure_nfs_access_rule`, `create_file_storage`, `delete_file_storage` |
| `backend/app/api/union/layer_ops.py` | FastAPI 라우터 |
| `frontend/src/routes/admin/libraries/+page.svelte` | 관리자 UI |
| `backend/tests/test_layer_ops.py` | pytest 검증 |
| `backend/migrations/017_layer_artifacts_stacked.sql` | `parent_id`, `is_sealed` ALTER TABLE |

---

## 발견된 버그 및 수정 이력

### Bug 1: `KeyError: 'access_id'` — 빌드 시작 직후 8% 실패

**원인**: `manila.ensure_nfs_access_rule`이 기존 rule이 없어 `create_access_rule`을 호출할 때,
반환값의 키가 `"id"`인데 caller(`layer_build.py`)는 `"access_id"` 키를 기대했다.

```python
# create_access_rule 반환값 구조
{"id": "...", "access_type": "ip", "access_level": "rw", ...}
#  ^^ "access_id" 아님

# ensure_nfs_access_rule 기존 rule 경로 반환 구조
{"access_id": "...", "access_key": "...", ...}
#  ^^ 이게 맞는 키
```

**수정** (`manila.py`): 신규 rule 생성 후 반환 시 `"id"` → `"access_id"` 정규화.

---

### Bug 2: `Unknown column 'layer_artifacts.parent_id'` — `/admin/libraries/artifacts` 500 오류

**원인**: `parent_id`, `is_sealed` 컬럼이 SQLAlchemy 모델에는 추가됐지만,
`create_all()`은 기존 테이블을 ALTER하지 않아 실제 MySQL 테이블에 컬럼이 없었다.

**수정**: `backend/migrations/017_layer_artifacts_stacked.sql` 작성 및 라이브 DB 적용.

```sql
ALTER TABLE layer_artifacts
    ADD COLUMN parent_id INT NULL AFTER build_id,
    ADD COLUMN is_sealed TINYINT(1) NOT NULL DEFAULT 0 AFTER parent_id,
    ADD CONSTRAINT fk_layer_artifacts_parent
        FOREIGN KEY (parent_id) REFERENCES layer_artifacts(id) ON DELETE SET NULL;
```

---

### Bug 3: cloud-init FAILURE sentinel 감지 — 콘솔 로그 공백

**원인 1 (진단 gap)**: 이 하이퍼바이저는 VM이 SHUTOFF 상태가 되면 시리얼 콘솔 버퍼를 초기화한다.
`nova.get_console_output(None)` 호출이 빈 문자열을 반환해 UI 콘솔 로그 패널이 비었다.

**원인 2 (진단 gap)**: ACTIVE 상태에서 early FAILURE 감지 시 `console_log_excerpt`를 DB에 저장하지 않았다.
SHUTOFF 후 읽기를 시도했을 때 이미 버퍼가 비어있어 아무것도 남지 않았다.

**수정** (`layer_build.py`):
- early 감지 즉시 DB 저장 (500줄, 4000자)
- SHUTOFF 후 `None → 500 → 200줄` 폴백 순서
- 이미 저장된 excerpt를 빈 값으로 덮지 않음

**수정** (`cloud_init_builder.py`):
- `_on_error` trap: 100줄 → 200줄
- failure 경로에서 `error.txt` 내용을 sentinel **앞에** 콘솔 출력

---

### Bug 4: `os-list-access` 400 오류 로그 (비치명적)

**원인**: `list_access_rules`가 modern API(`share-access-rules GET`) 실패 시
legacy fallback `os-list-access POST`를 시도하는데, Manila 서버가 이 action을 지원하지 않아 400 반환.
`except Exception`으로 포착되어 `[]` 반환 — 빌드 진행에 영향 없음.

**상태**: 비치명적. legacy 경로 제거 또는 로그 레벨 `WARNING → DEBUG` 다운그레이드로 노이즈 감소 가능.

---

## 미해결 이슈

### python311 빌드 90% 실패 — 원인 미확정

**증상**: 빌드 8분32초 소요 후 90%에서 FAILURE sentinel 감지. UI 콘솔 로그에 실제 오류 없음(위 Bug 3).

**확인된 사실**:
- squashfs-tools `1:4.6.1-1build1` 설치됨 → zstd 지원 **정상**. `-comp zstd` 는 문제 아님.
- Ubuntu 24.04.4 LTS 기반 빌더 이미지 사용.
- 패키지 설치(nfs-common, squashfs-tools) 성공 확인.

**미확인 원인 후보**:
1. `uv python install cpython-3.11` 실패 (네트워크 오류 또는 설치 경로 문제)
2. `cp -a "$PYDIR/." "$STAGING_LOCAL/"` 용량 부족 (CPython 트리 크기 vs VM 루트 디스크)
3. `mksquashfs` 시 메모리/디스크 부족

**다음 액션**: Bug 3 수정이 반영된 상태에서 빌드 재시도 → UI 콘솔 로그 패널 `---AFTERGLOW-ERROR-LOG-BEGIN---` 구간 확인.

---

## 보안 고려 사항

- `layer_name`, `python_version`, `pip_packages` — Pydantic 화이트리스트 정규식 검증
- Manila export 경로 — `_NFS_EXPORT_RE` 검증 + `shlex.quote` (외부 API 반환값도 신뢰하지 않음)
- cloud-init 개행 주입 차단 — export_path 개행 문자 → 422
- `_on_error` trap 기록 파일 경로 — 하드코딩 (`/mnt/share/_build_logs/error.txt`)
- 모든 엔드포인트 `Depends(require_admin)` 필수
- RW access rule은 빌드 완료/실패 시 모두 회수 (finally 블록)
