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

Dockerfile을 통한 체인 빌드 역시 이 squashfs/Manila 파이프라인을 사용한다. 관리자 입력의
`FROM` Glance 이미지 이름/UUID 또는 유일한 Ubuntu tag 해석, 읽기 전용 lint와 inline/GitHub
컨텍스트 차이는 [Palimpsest Dockerfile 계약](palimpsest.md#44-dockerfile-로-레이어-빌드)에 있다.

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
