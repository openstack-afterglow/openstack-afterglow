"""관리자 GPU 호스트 모니터링 엔드포인트."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import openstack

from fastapi import APIRouter, Depends, HTTPException, Query, Response, UploadFile
from pydantic import BaseModel, Field

from app.api.deps import CacheMode, cache_mode, get_admin_os_conn, require_admin
from app.services.cache import cached_call, ttl_normal

# FastAPI-free 인벤토리 유틸리티로 이동된 항목들 — 하위 호환을 위해 재export.
from app.services.gpu_inventory import (  # noqa: F401
    PCI_DEVICE_MAP,
    VENDOR_MAP,
    _collect_gpu_hosts,
    _device_name,
    _extract_hostname,
    _find_root_uuid,
    _is_audio_device,
    build_alias_to_device_name_map,
    get_gpu_spec_list,
)

_logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/gpu-hosts", dependencies=[Depends(require_admin)])
async def list_gpu_hosts(
    conn: openstack.connection.Connection = Depends(get_admin_os_conn), cm: CacheMode = Depends(cache_mode)
):
    """Placement API에서 각 호스트별 GPU 정보 조회."""

    def _collect():
        return _collect_gpu_hosts(conn)

    try:
        return await cached_call(
            "afterglow:admin:gpu_hosts", ttl_normal(), _collect, enabled=cm.enabled, refresh=cm.refresh
        )
    except Exception:
        raise HTTPException(status_code=500, detail="GPU 호스트 조회 실패")


@router.get("/gpu-hosts/raw", dependencies=[Depends(require_admin)])
async def list_gpu_hosts_raw(
    conn: openstack.connection.Connection = Depends(get_admin_os_conn),
):
    """호스트별 Placement CUSTOM_PCI_* 원시 인벤토리 반환 (오디오 필터 미적용).

    GPU 분류 진단 목적: 실제 device_id(예: 2503 vs 2504)와 resource_class를 그대로 노출.
    `resolved_name`은 현재 PCI_DEVICE_MAP 기준 이름, 없으면 None.
    `is_audio`로 오디오 장치를 식별할 수 있다.
    """

    def _collect_raw() -> dict:
        placement_ep = conn.placement.get_endpoint()
        rps_resp = conn.session.get(f"{placement_ep}/resource_providers")
        all_rps = rps_resp.json().get("resource_providers", [])
        rp_map: dict[str, dict] = {rp["uuid"]: rp for rp in all_rps}

        host_map: dict[str, dict] = {}
        for rp in all_rps:
            if rp.get("parent_provider_uuid") is None:
                host_map[rp["uuid"]] = {
                    "name": rp["name"],
                    "uuid": rp["uuid"],
                    "pci_resources": [],
                }

        for rp in all_rps:
            root_uuid = _find_root_uuid(rp["uuid"], rp_map)
            if root_uuid not in host_map:
                continue
            try:
                inv_resp = conn.session.get(f"{placement_ep}/resource_providers/{rp['uuid']}/inventories")
                inventories = inv_resp.json().get("inventories", {})
                pci_rcs = {k: v for k, v in inventories.items() if k.startswith("CUSTOM_PCI_")}
                if not pci_rcs:
                    continue

                usages: dict[str, int] = {}
                try:
                    usage_resp = conn.session.get(f"{placement_ep}/resource_providers/{rp['uuid']}/usages")
                    usages = usage_resp.json().get("usages", {})
                except Exception:
                    pass

                root_name = host_map[root_uuid]["name"]
                rp_name = rp["name"]
                pci_address = rp_name[len(root_name) + 1 :] if rp_name.startswith(root_name + "_") else rp_name

                for rc_name, inv_data in pci_rcs.items():
                    parts = rc_name.split("_")
                    vendor_id = parts[2] if len(parts) >= 3 else ""
                    device_id = parts[3] if len(parts) >= 4 else ""
                    resolved = _device_name(vendor_id, device_id)
                    host_map[root_uuid]["pci_resources"].append(
                        {
                            "provider_uuid": rp["uuid"],
                            "provider_name": rp_name,
                            "pci_address": pci_address,
                            "resource_class": rc_name,
                            "vendor_id": vendor_id,
                            "device_id": device_id,
                            "vendor_name": VENDOR_MAP.get(vendor_id, vendor_id),
                            "resolved_name": resolved if resolved != device_id else None,
                            "total": inv_data.get("total", 0),
                            "used": usages.get(rc_name, 0),
                            "is_audio": _is_audio_device(vendor_id, device_id),
                        }
                    )
            except Exception:
                _logger.warning("RP %s raw 인벤토리 조회 실패", rp.get("uuid"), exc_info=True)

        hosts_with_pci = sorted([h for h in host_map.values() if h["pci_resources"]], key=lambda h: h["name"])
        return {"hosts": hosts_with_pci}

    try:
        return await asyncio.to_thread(_collect_raw)
    except Exception:
        raise HTTPException(status_code=500, detail="GPU raw 인벤토리 조회 실패")


class GpuDeviceRequest(BaseModel):
    """GPU 장치 카탈로그 단건 추가/수정 요청."""

    vendor_id: str = Field(..., pattern=r"^[0-9A-Fa-f]{4}$")
    device_id: str = Field(..., pattern=r"^[0-9A-Fa-f]{4}$")
    name: str = Field(..., min_length=1, max_length=128)
    is_audio: bool = False
    aliases: list[str] = Field(default_factory=list)


def _require_db():
    from app.database import is_db_available

    if not is_db_available():
        raise HTTPException(status_code=503, detail="DB가 초기화되지 않아 GPU 카탈로그를 변경할 수 없습니다")


async def _merged_devices() -> list[dict]:
    """내장 기본값 + afterglow.conf + DB 병합 카탈로그 목록 (source 표시).

    카탈로그는 **DB를 권위 소스로** 한다: in-process PCI_DEVICE_MAP(각 pod의 lazy
    overlay)에 아직 반영되지 않은 DB 항목도 포함시킨다. 다중 replica 환경에서 업로드를
    처리한 pod와 목록을 서빙하는 pod가 달라도 카탈로그 수가 DB와 일치하도록 보장한다.
    """
    from app.database import is_db_available
    from app.services.gpu_catalog import list_db_devices
    from app.services.gpu_inventory import _DEFAULT_PCI_DEVICE_MAP

    db_entries: dict[tuple[str, str], dict] = {}
    if is_db_available():
        try:
            db_entries = {(e["vendor_id"], e["device_id"]): e for e in await list_db_devices()}
        except Exception:
            _logger.warning("GPU 카탈로그 DB 조회 실패 — builtin/config만 표시", exc_info=True)

    devices = []
    seen: set[tuple[str, str]] = set()
    for vendor_id, vendor_devices in PCI_DEVICE_MAP.items():
        for device_id, info in vendor_devices.items():
            key = (vendor_id, device_id)
            seen.add(key)
            if key in db_entries:
                source = "db"
                merged_info = db_entries[key]
            elif device_id in _DEFAULT_PCI_DEVICE_MAP.get(vendor_id, {}):
                source = "builtin"
                merged_info = info
            else:
                source = "config"
                merged_info = info
            devices.append(
                {
                    "vendor_id": vendor_id,
                    "device_id": device_id,
                    "vendor_name": VENDOR_MAP.get(vendor_id, vendor_id),
                    "name": merged_info["name"],
                    "is_audio": merged_info["is_audio"],
                    "aliases": merged_info.get("aliases", []),
                    "source": source,
                }
            )
    # DB에만 있고 이 pod의 PCI_DEVICE_MAP에 아직 overlay되지 않은 항목도 포함 (DB 권위)
    for key, e in db_entries.items():
        if key in seen:
            continue
        vendor_id, device_id = key
        devices.append(
            {
                "vendor_id": vendor_id,
                "device_id": device_id,
                "vendor_name": VENDOR_MAP.get(vendor_id, vendor_id),
                "name": e["name"],
                "is_audio": e["is_audio"],
                "aliases": e.get("aliases", []),
                "source": "db",
            }
        )
    devices.sort(key=lambda d: (d["vendor_id"], d["name"]))
    return devices


@router.get("/gpu-devices", dependencies=[Depends(require_admin)])
async def list_gpu_devices():
    """병합된 GPU 장치 카탈로그 목록 (내장 기본값 + afterglow.conf + DB overlay).

    각 항목의 source: "builtin"(코드 내장) | "config"(afterglow.conf) | "db"(관리자 추가).
    db 항목만 삭제 가능하다.
    """
    return {"devices": await _merged_devices()}


@router.get("/gpu-devices/export", dependencies=[Depends(require_admin)])
async def export_gpu_devices(format: str = Query("xlsx", pattern="^(xlsx|csv)$")):
    """현재 병합 카탈로그를 템플릿 파일로 다운로드 (값을 채워 import에 재업로드).

    컬럼: vendor_id, device_id, name, is_audio, aliases, source — import 시 source는 무시된다.
    """
    from app.services.gpu_catalog import build_export_csv, build_export_xlsx

    devices = await _merged_devices()
    if format == "csv":
        # 엑셀에서 한글이 깨지지 않도록 UTF-8 BOM 포함
        content = ("\ufeff" + build_export_csv(devices)).encode("utf-8")
        media_type = "text/csv; charset=utf-8"
        filename = "gpu_devices.csv"
    else:
        try:
            content = build_export_xlsx(devices)
        except ImportError:
            # 실행 중인 백엔드가 openpyxl 추가 이전에 시작된 경우 (재배포/재시작 필요)
            raise HTTPException(
                status_code=503,
                detail="엑셀 모듈(openpyxl)이 설치되지 않았습니다 — 백엔드 재시작 후 사용 가능합니다. 우선 CSV 템플릿을 이용하세요.",
            )
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        filename = "gpu_devices.xlsx"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/gpu-devices", dependencies=[Depends(require_admin)])
async def upsert_gpu_device(req: GpuDeviceRequest):
    """GPU 장치 카탈로그 단건 추가/수정 (DB upsert 후 PCI_DEVICE_MAP 즉시 반영)."""
    from app.services.gpu_catalog import refresh_device_map_from_db, upsert_device

    _require_db()
    try:
        result = await upsert_device(req.vendor_id, req.device_id, req.name, req.is_audio, req.aliases)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await refresh_device_map_from_db()
    return result


@router.delete("/gpu-devices/{vendor_id}/{device_id}", dependencies=[Depends(require_admin)], status_code=204)
async def delete_gpu_device(vendor_id: str, device_id: str):
    """GPU 장치 카탈로그 DB 항목 삭제. builtin/config 항목은 삭제 불가."""
    from app.services.gpu_catalog import delete_device, refresh_device_map_from_db

    _require_db()
    deleted = await delete_device(vendor_id, device_id)
    if not deleted:
        vendor_key = vendor_id.upper()
        device_key = device_id.upper()
        if device_key in PCI_DEVICE_MAP.get(vendor_key, {}):
            raise HTTPException(status_code=409, detail="내장 기본값/afterglow.conf 항목은 삭제할 수 없습니다")
        raise HTTPException(status_code=404, detail="해당 GPU 장치가 카탈로그에 없습니다")
    await refresh_device_map_from_db()


@router.post("/gpu-devices/import", dependencies=[Depends(require_admin)])
async def import_gpu_devices(
    file: UploadFile,
    mode: str = Query("replace", pattern="^(replace|upsert)$"),
):
    """CSV/엑셀(xlsx) 일괄 import. 컬럼: vendor_id,device_id,name,is_audio,aliases(세미콜론 구분).

    /gpu-devices/export로 받은 템플릿에 값을 채워 그대로 업로드하면 된다 (source 컬럼은 무시).
    mode=replace(기본): DB 항목 전체 교체. mode=upsert: 기존 항목 유지하며 병합.
    """
    from app.services.gpu_catalog import bulk_import, parse_csv, parse_xlsx, refresh_device_map_from_db

    _require_db()
    raw = await file.read()
    if len(raw) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="파일이 너무 큽니다 (최대 5MB)")
    is_xlsx = raw[:4] == b"PK\x03\x04" or (file.filename or "").lower().endswith(".xlsx")
    try:
        if is_xlsx:
            try:
                entries = parse_xlsx(raw)
            except ImportError:
                raise HTTPException(
                    status_code=503,
                    detail="엑셀 모듈(openpyxl)이 설치되지 않았습니다 — 백엔드 재시작 후 사용 가능합니다. 우선 CSV로 업로드하세요.",
                )
        else:
            try:
                content = raw.decode("utf-8-sig")
            except UnicodeDecodeError:
                raise HTTPException(status_code=400, detail="CSV는 UTF-8 인코딩이어야 합니다")
            entries = parse_csv(content)
        imported = await bulk_import(entries, mode=mode)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await refresh_device_map_from_db()
    return {"imported": imported, "mode": mode}


def build_device_name_to_alias_map() -> dict[str, str]:
    """정식 GPU 이름 → 대표 OpenStack PCI alias 매핑 반환.

    예: "RTX 3090" → "RTX3090", "GTX 1080 Ti" → "GTX1080Ti"
    aliases 리스트의 첫 번째 항목을 대표 alias로 사용.
    """
    name_map: dict[str, str] = {}
    for devices in PCI_DEVICE_MAP.values():
        for info in devices.values():
            if info.get("is_audio"):
                continue
            aliases = info.get("aliases", [])
            if aliases:
                name_map[info["name"]] = aliases[0]
    return name_map


def build_normalized_alias_map() -> dict[str, str]:
    """정규화된 alias → 대표(canonical) alias 매핑 반환.

    하이픈, 언더스코어, 공백을 제거하고 소문자로 비교하여
    같은 GPU의 다른 표기(RTX-3090, RTX3090, RTX_3090)를 대표 alias로 통일.
    """
    norm_map: dict[str, str] = {}
    for devices in PCI_DEVICE_MAP.values():
        for info in devices.values():
            if info.get("is_audio"):
                continue
            aliases = info.get("aliases", [])
            if not aliases:
                continue
            canonical = aliases[0]
            # 대표 alias 자체도 등록
            norm_map[canonical.replace("-", "").replace("_", "").replace(" ", "").lower()] = canonical
            for alias in aliases:
                norm_map[alias.replace("-", "").replace("_", "").replace(" ", "").lower()] = canonical
    return norm_map
