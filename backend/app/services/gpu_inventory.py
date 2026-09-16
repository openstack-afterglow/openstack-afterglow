"""GPU inventory helpers without FastAPI dependencies."""

from __future__ import annotations

import copy
import logging
import re
from typing import Any

from app.config import load_raw_toml
from app.services import gpu_quota

_logger = logging.getLogger(__name__)

VENDOR_MAP = {
    "10DE": "NVIDIA",
    "8086": "Intel",
    "1002": "AMD",
}

# PCI vendor:product → {name, is_audio, aliases} 기본 매핑
# aliases: OpenStack nova.conf의 pci_passthrough:alias 이름 목록 (소문자 포함)
_DEFAULT_PCI_DEVICE_MAP: dict[str, dict[str, dict]] = {
    "10DE": {
        # === Maxwell ===
        "17C2": {"name": "GTX TITAN X", "is_audio": False, "aliases": ["GTX_TITAN_X", "GTX TITAN X", "titan"]},
        "0FB0": {"name": "GM200 Audio", "is_audio": True, "aliases": []},
        # === Pascal ===
        "1B06": {"name": "GTX 1080 Ti", "is_audio": False, "aliases": ["GTX1080Ti", "GTX_1080_Ti", "1080ti"]},
        "1B80": {"name": "GTX 1080", "is_audio": False, "aliases": ["GTX1080", "GTX_1080", "1080"]},
        "1B81": {"name": "GTX 1070", "is_audio": False, "aliases": ["GTX1070", "GTX_1070", "1070"]},
        "1B00": {"name": "TITAN X", "is_audio": False, "aliases": ["TITAN_X"]},
        "1B02": {"name": "TITAN Xp", "is_audio": False, "aliases": ["TITAN_Xp", "titanxp"]},
        "10EF": {"name": "GP102 Audio", "is_audio": True, "aliases": []},
        # === Ampere Consumer ===
        "2204": {"name": "RTX 3090", "is_audio": False, "aliases": ["RTX3090", "rtx3090", "RTX_3090", "3090"]},
        "2203": {"name": "RTX 3090 Ti", "is_audio": False, "aliases": ["RTX3090Ti", "RTX_3090_Ti", "3090ti", "3090Ti"]},
        "2206": {"name": "RTX 3080 Ti", "is_audio": False, "aliases": ["RTX3080Ti", "RTX_3080_Ti", "3080ti", "3080Ti"]},
        "220A": {"name": "RTX 3080", "is_audio": False, "aliases": ["RTX3080", "RTX_3080", "3080"]},
        "2484": {"name": "RTX 3070 Ti", "is_audio": False, "aliases": ["RTX3070Ti", "RTX_3070_Ti", "3070ti", "3070Ti"]},
        "2482": {"name": "RTX 3070", "is_audio": False, "aliases": ["RTX3070", "RTX_3070", "3070"]},
        "2487": {"name": "RTX 3060", "is_audio": False, "aliases": ["RTX3060", "RTX_3060", "3060"]},
        "2504": {"name": "RTX 3060 LHR", "is_audio": False, "aliases": ["RTX3060LHR", "RTX_3060_LHR", "3060LHR"]},
        "1AEF": {"name": "GA102 Audio", "is_audio": True, "aliases": []},
        # === Ada Lovelace Consumer ===
        "2684": {"name": "RTX 4090", "is_audio": False, "aliases": ["RTX4090", "rtx4090", "RTX_4090", "4090"]},
        "2704": {"name": "RTX 4080", "is_audio": False, "aliases": ["RTX4080", "RTX_4080", "4080"]},
        "2782": {
            "name": "RTX 4070 Ti SUPER",
            "is_audio": False,
            "aliases": ["RTX4070TiSuper", "RTX_4070_Ti_SUPER", "4070tisuper"],
        },
        "2783": {"name": "RTX 4070 Ti", "is_audio": False, "aliases": ["RTX4070Ti", "RTX_4070_Ti", "4070ti", "4070Ti"]},
        "2786": {
            "name": "RTX 4070 SUPER",
            "is_audio": False,
            "aliases": ["RTX4070Super", "RTX_4070_SUPER", "4070super"],
        },
        "2882": {"name": "RTX 4060 Ti", "is_audio": False, "aliases": ["RTX4060Ti", "RTX_4060_Ti", "4060ti", "4060Ti"]},
        "22BA": {"name": "AD102 Audio", "is_audio": True, "aliases": []},
        "22BE": {"name": "AD107 Audio", "is_audio": True, "aliases": []},
        # === Blackwell Consumer ===
        "2B85": {"name": "RTX 5090", "is_audio": False, "aliases": ["RTX5090", "RTX_5090", "5090"]},
        "2B80": {"name": "RTX 5080", "is_audio": False, "aliases": ["RTX5080", "RTX_5080", "5080"]},
        # === Professional / Workstation ===
        "28B0": {
            "name": "RTX 2000 Ada",
            "is_audio": False,
            "aliases": ["RTX2000Ada", "RTX_2000_Ada", "2000Ada", "2000ada"],
        },
        "2230": {"name": "RTX A6000", "is_audio": False, "aliases": ["RTXA6000", "RTX_A6000"]},
        "2231": {"name": "RTX A5000", "is_audio": False, "aliases": ["RTXA5000", "RTX_A5000"]},
        "26B1": {"name": "L40", "is_audio": False, "aliases": ["L40", "l40"]},
        "26B9": {"name": "L40S", "is_audio": False, "aliases": ["L40S", "l40s"]},
        # === Datacenter ===
        "20B0": {"name": "A100 SXM4 40GB", "is_audio": False, "aliases": ["A100_SXM4_40GB", "A100SXM440GB"]},
        "20B2": {
            "name": "A100 SXM4 80GB",
            "is_audio": False,
            "aliases": ["A100_SXM4_80GB", "A100SXM480GB", "A100_80GB"],
        },
        "20B5": {"name": "A100 PCIe", "is_audio": False, "aliases": ["A100_PCIe", "A100PCIe"]},
        "20F1": {"name": "A100 PCIe 40GB", "is_audio": False, "aliases": ["A100_PCIe_40GB", "A100PCIe40GB"]},
        "20B8": {"name": "A10", "is_audio": False, "aliases": ["A10", "a10"]},
        "2330": {"name": "H100 SXM5", "is_audio": False, "aliases": ["H100_SXM5", "H100SXM5"]},
        "2331": {"name": "H100 PCIe", "is_audio": False, "aliases": ["H100_PCIe", "H100PCIe"]},
    },
}


def _load_device_map() -> dict[str, dict[str, dict]]:
    """afterglow.conf의 [[gpu.devices]] 항목으로 기본 맵을 확장하여 반환."""
    device_map = copy.deepcopy(_DEFAULT_PCI_DEVICE_MAP)
    try:
        raw = load_raw_toml()
        for entry in raw.get("gpu", {}).get("devices", []):
            vendor = str(entry.get("vendor_id", "")).upper()
            device = str(entry.get("device_id", "")).upper()
            name = str(entry.get("name", ""))
            is_audio = bool(entry.get("is_audio", False))
            aliases = [str(a) for a in entry.get("aliases", [])]
            if vendor and device:
                device_map.setdefault(vendor, {})[device] = {
                    "name": name,
                    "is_audio": is_audio,
                    "aliases": aliases,
                }
    except Exception:
        _logger.warning("afterglow.conf gpu.devices 로드 실패 — 기본 맵 사용", exc_info=True)
    return device_map


def _normalize_alias_value(alias: str) -> str:
    return alias.replace("-", "").replace("_", "").replace(" ", "").lower()


def resolve_alias_to_device_name(alias: str, alias_map: dict[str, str] | None = None) -> str | None:
    """Resolve a Nova PCI alias to the canonical GPU device name.

    Tries the raw alias first, then a normalized fallback so Nova aliases like
    ``RTX-3060-LHR`` can still match catalog aliases such as ``RTX_3060_LHR``
    or ``3060LHR``.
    """
    if not alias:
        return None
    mapping = alias_map if alias_map is not None else build_alias_to_device_name_map()
    resolved = mapping.get(alias)
    if resolved:
        return resolved
    return mapping.get(_normalize_alias_value(alias))


PCI_DEVICE_MAP = _load_device_map()


def apply_db_overlay(db_entries: list[dict]) -> None:
    """DB 카탈로그 항목을 base map(내장 기본값 + afterglow.conf) 위에 overlay.

    PCI_DEVICE_MAP을 in-place로 갱신하므로 이 dict를 import한 모듈
    (admin_gpu, gpu_quota, openstack_inventory, notion_worker)에 즉시 반영된다.
    """
    merged = _load_device_map()
    for entry in db_entries:
        vendor = str(entry.get("vendor_id", "")).upper()
        device = str(entry.get("device_id", "")).upper()
        if not vendor or not device:
            continue
        merged.setdefault(vendor, {})[device] = {
            "name": str(entry.get("name", "")),
            "is_audio": bool(entry.get("is_audio", False)),
            "aliases": [str(a) for a in entry.get("aliases", [])],
        }
    PCI_DEVICE_MAP.clear()
    PCI_DEVICE_MAP.update(merged)


def _extract_hostname(name: str) -> str:
    """RP 이름에서 PCI 주소 접미사를 제거하여 호스트명 반환.

    예: "dms-compute10_0000:03:00.0" → "dms-compute10"
    """
    m = re.match(r"^(.+?)_[0-9a-fA-F]{4}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.\d+$", name)
    return m.group(1) if m else name


def _is_audio_device(vendor_id: str, device_id: str) -> bool:
    """PCI 디바이스가 오디오 장치인지 확인."""
    info = PCI_DEVICE_MAP.get(vendor_id, {}).get(device_id)
    if info is not None:
        return info["is_audio"]
    return False


def _device_name(vendor_id: str, device_id: str) -> str:
    """PCI vendor:product → 디바이스 이름."""
    info = PCI_DEVICE_MAP.get(vendor_id, {}).get(device_id)
    if info:
        return info["name"]
    return ""


def _find_root_uuid(uuid: str, rp_map: dict) -> str:
    """RP 트리에서 루트(호스트) UUID를 찾음 (순환 방지 포함)."""
    visited: set[str] = set()
    current = uuid
    while current in rp_map:
        parent = rp_map[current].get("parent_provider_uuid")
        if not parent:
            break
        if parent in visited:
            break
        visited.add(current)
        current = parent
    return current


def _collect_gpu_hosts(conn) -> dict:
    """Placement API로 호스트별 GPU 정보를 수집한다 (동기 함수).

    반환값: {hosts, aggregated_hosts, summary, gpu_types}
    aggregated_hosts 각 항목: {name, gpus, gpu_groups, gpu_total, gpu_used}
    gpu_groups 각 항목: {device_name, vendor_name, total, used}
    """
    placement_ep = conn.placement.get_endpoint()

    # 1) 모든 리소스 프로바이더 조회
    rps_resp = conn.session.get(f"{placement_ep}/resource_providers")
    all_rps = rps_resp.json().get("resource_providers", [])

    # RP UUID → RP 전체 데이터 맵
    rp_map: dict[str, dict] = {rp["uuid"]: rp for rp in all_rps}

    # 루트 RP (parent_provider_uuid가 None) → 호스트 맵
    host_map: dict[str, dict] = {}
    for rp in all_rps:
        if rp.get("parent_provider_uuid") is None:
            host_map[rp["uuid"]] = {
                "name": rp["name"],
                "uuid": rp["uuid"],
                "gpus": [],
                "gpu_total": 0,
                "gpu_used": 0,
            }

    # 2) 루트가 아닌 모든 RP의 인벤토리에서 CUSTOM_PCI_* 스캔
    for rp in all_rps:
        if rp.get("parent_provider_uuid") is None:
            continue  # 루트는 별도 처리

        # 루트 호스트 UUID 탐색
        root_uuid = _find_root_uuid(rp["uuid"], rp_map)
        if root_uuid not in host_map:
            continue

        try:
            inv_resp = conn.session.get(f"{placement_ep}/resource_providers/{rp['uuid']}/inventories")
            inventories = inv_resp.json().get("inventories", {})

            # usages 별도 조회 (inventory에는 used 필드가 없음)
            usages: dict[str, int] = {}
            has_pci = any(rc.startswith("CUSTOM_PCI_") for rc in inventories)
            if has_pci:
                try:
                    usage_resp = conn.session.get(f"{placement_ep}/resource_providers/{rp['uuid']}/usages")
                    usages = usage_resp.json().get("usages", {})
                except Exception:
                    pass

            for rc_name, inv_data in inventories.items():
                if not rc_name.startswith("CUSTOM_PCI_"):
                    continue

                parts = rc_name.split("_")  # ["CUSTOM", "PCI", "10DE", "10EF"]
                vendor_id = parts[2] if len(parts) >= 3 else ""
                device_id = parts[3] if len(parts) >= 4 else ""

                if _is_audio_device(vendor_id, device_id):
                    continue

                # PCI 주소: rp 이름에서 루트 호스트 이름 제거
                root_name = host_map[root_uuid]["name"]
                rp_name = rp["name"]
                pci_address = rp_name
                if rp_name.startswith(root_name + "_"):
                    pci_address = rp_name[len(root_name) + 1 :]

                used = usages.get(rc_name, 0)
                gpu_info = {
                    "provider_name": rp_name,
                    "provider_uuid": rp["uuid"],
                    "pci_address": pci_address,
                    "resource_class": rc_name,
                    "vendor_id": vendor_id,
                    "vendor_name": VENDOR_MAP.get(vendor_id, vendor_id),
                    "device_id": device_id,
                    "device_name": _device_name(vendor_id, device_id),
                    "total": inv_data.get("total", 0),
                    "used": used,
                    "allocation_ratio": inv_data.get("allocation_ratio", 1.0),
                    "reserved": inv_data.get("reserved", 0),
                }

                host_map[root_uuid]["gpus"].append(gpu_info)
                host_map[root_uuid]["gpu_total"] += gpu_info["total"]
                host_map[root_uuid]["gpu_used"] += gpu_info["used"]
        except Exception:
            _logger.warning("RP %s 인벤토리 조회 실패", rp.get("uuid"), exc_info=True)

    # 3) 자식 RP에서 GPU를 찾지 못한 호스트: 루트 RP 인벤토리도 확인
    for host_uuid, host_info in host_map.items():
        if host_info["gpu_total"] > 0:
            continue
        try:
            inv_resp = conn.session.get(f"{placement_ep}/resource_providers/{host_uuid}/inventories")
            inventories = inv_resp.json().get("inventories", {})

            usages2: dict[str, int] = {}
            has_pci = any(rc.startswith("CUSTOM_PCI_") for rc in inventories)
            if has_pci:
                try:
                    usage_resp = conn.session.get(f"{placement_ep}/resource_providers/{host_uuid}/usages")
                    usages2 = usage_resp.json().get("usages", {})
                except Exception:
                    pass

            for rc_name, inv_data in inventories.items():
                if not rc_name.startswith("CUSTOM_PCI_"):
                    continue
                parts = rc_name.split("_")
                vendor_id = parts[2] if len(parts) >= 3 else ""
                device_id = parts[3] if len(parts) >= 4 else ""
                if _is_audio_device(vendor_id, device_id):
                    continue
                used = usages2.get(rc_name, 0)
                gpu_info = {
                    "provider_name": host_info["name"],
                    "provider_uuid": host_uuid,
                    "pci_address": "host-level",
                    "resource_class": rc_name,
                    "vendor_id": vendor_id,
                    "vendor_name": VENDOR_MAP.get(vendor_id, vendor_id),
                    "device_id": device_id,
                    "device_name": _device_name(vendor_id, device_id),
                    "total": inv_data.get("total", 0),
                    "used": used,
                    "allocation_ratio": inv_data.get("allocation_ratio", 1.0),
                    "reserved": inv_data.get("reserved", 0),
                }
                host_info["gpus"].append(gpu_info)
                host_info["gpu_total"] += gpu_info["total"]
                host_info["gpu_used"] += gpu_info["used"]
        except Exception:
            _logger.warning("루트 RP %s 인벤토리 조회 실패", host_uuid, exc_info=True)

    # GPU가 있는 호스트만 필터링하여 정렬
    gpu_hosts = sorted(
        [h for h in host_map.values() if h["gpu_total"] > 0],
        key=lambda h: h["name"],
    )

    total_gpus = sum(h["gpu_total"] for h in gpu_hosts)
    used_gpus = sum(h["gpu_used"] for h in gpu_hosts)

    # GPU 종류별 집계
    type_map: dict[str, dict] = {}
    for h in gpu_hosts:
        for gpu in h["gpus"]:
            key = f"{gpu['vendor_id']}_{gpu['device_id']}"
            if key not in type_map:
                type_map[key] = {
                    "device_name": gpu["device_name"] or gpu["device_id"],
                    "vendor": gpu["vendor_name"],
                    "total": 0,
                    "used": 0,
                }
            type_map[key]["total"] += gpu["total"]
            type_map[key]["used"] += gpu["used"]

    # SHELVED/SHELVED_OFFLOADED 인스턴스의 GPU 할당이 Placement에 잔존하면 used가 total을 초과해
    # 재고가 음수가 될 수 있다. Nova 서버 목록에서 해당 인스턴스의 GPU 수를 차감해 보정한다.
    try:
        # alias → "VENDOR_DEVICE" 키 역매핑
        alias_to_key: dict[str, str] = {}
        for _vid, _devices in PCI_DEVICE_MAP.items():
            for _did, _info in _devices.items():
                if _info.get("is_audio"):
                    continue
                for _alias in _info.get("aliases", []):
                    if _alias:
                        alias_to_key[_alias.lower()] = f"{_vid}_{_did}"

        # flavor id → extra_specs 매핑 (list_flavors는 동기 호출)
        from app.services import nova as _nova_svc

        flavors_by_id: dict[str, object] = {f.id: f for f in _nova_svc.list_flavors(conn)}

        shelved_used: dict[str, int] = {}
        for _s in conn.compute.servers(all_projects=True, details=True):
            if _s.status not in ("SHELVED", "SHELVED_OFFLOADED"):
                continue
            _flavor = _s.flavor if hasattr(_s, "flavor") else {}
            _fid = (_flavor.get("id") if isinstance(_flavor, dict) else getattr(_s, "flavor_id", "")) or ""
            _fl = flavors_by_id.get(_fid)
            if not _fl:
                continue
            _alias_str = (_fl.extra_specs or {}).get("pci_passthrough:alias", "")
            for _entry in _alias_str.split(","):
                _entry = _entry.strip()
                if not _entry or ":" not in _entry or "audio" in _entry.lower():
                    continue
                _alias, _, _num = _entry.rpartition(":")
                _dkey = alias_to_key.get(_alias.strip().lower())
                if not _dkey:
                    continue
                try:
                    shelved_used[_dkey] = shelved_used.get(_dkey, 0) + int(_num)
                except ValueError:
                    shelved_used[_dkey] = shelved_used.get(_dkey, 0) + 1

        if shelved_used:
            _logger.info("SHELVED/SHELVED_OFFLOADED GPU Placement 보정: %s", shelved_used)
            for _dkey, _cnt in shelved_used.items():
                if _dkey in type_map:
                    type_map[_dkey]["used"] = max(0, type_map[_dkey]["used"] - _cnt)
            # 보정된 type_map 기준으로 used_gpus 재계산
            used_gpus = sum(v["used"] for v in type_map.values())
    except Exception:
        _logger.warning("SHELVED GPU Placement 보정 실패 — 원본 Placement 값 사용", exc_info=True)

    gpu_types = sorted(type_map.values(), key=lambda x: x["total"], reverse=True)

    # 호스트명 기반 집계 (PCI 주소 접미사 제거 후 그룹핑)
    agg: dict[str, dict] = {}
    for h in gpu_hosts:
        hostname = _extract_hostname(h["name"])
        if hostname not in agg:
            agg[hostname] = {
                "name": hostname,
                "gpus": [],
                "gpu_groups": [],
                "gpu_total": 0,
                "gpu_used": 0,
            }
        agg[hostname]["gpus"].extend(h["gpus"])
        agg[hostname]["gpu_total"] += h["gpu_total"]
        agg[hostname]["gpu_used"] += h["gpu_used"]

    for host_data in agg.values():
        groups: dict[str, dict] = {}
        for gpu in host_data["gpus"]:
            key = f"{gpu['vendor_id']}_{gpu['device_id']}"
            if key not in groups:
                groups[key] = {
                    "device_name": gpu["device_name"] or gpu["device_id"],
                    "vendor_name": gpu["vendor_name"],
                    "total": 0,
                    "used": 0,
                }
            groups[key]["total"] += gpu["total"]
            groups[key]["used"] += gpu["used"]
        host_data["gpu_groups"] = sorted(groups.values(), key=lambda x: x["device_name"])

    aggregated_hosts = sorted(agg.values(), key=lambda h: h["name"])

    return {
        "hosts": gpu_hosts,
        "aggregated_hosts": aggregated_hosts,
        "summary": {
            "total_hosts": len(aggregated_hosts),
            "total_gpus": total_gpus,
            "used_gpus": used_gpus,
            "available_gpus": total_gpus - used_gpus,
        },
        "gpu_types": gpu_types,
    }


def get_gpu_spec_list() -> list[dict]:
    """PCI_DEVICE_MAP을 flat list로 변환하여 반환 (Notion GPU spec 동기화용)."""
    result = []
    for vendor_id, devices in PCI_DEVICE_MAP.items():
        for device_id, info in devices.items():
            result.append(
                {
                    "vendor_id": vendor_id,
                    "device_id": device_id,
                    "name": info["name"],
                    "is_audio": info["is_audio"],
                    "vendor_name": VENDOR_MAP.get(vendor_id, vendor_id),
                    "aliases": info.get("aliases", []),
                }
            )
    return result


def build_alias_to_device_name_map() -> dict[str, str]:
    """OpenStack PCI alias → 정식 GPU 이름 매핑 반환.

    예: "RTX3090" → "RTX 3090", "A100_80GB" → "A100 SXM4 80GB"
    GPU flavor의 pci_passthrough:alias 값을 GPU Spec Notion 페이지 이름으로 변환할 때 사용한다.

    대소문자·구분자(-, _, 공백) 무관 매칭을 위해 원본 alias 외에 정규화 키도 등록한다.
    예: "RTX3060LHR" 등록 시 "rtx3060lhr"도 함께 등록 → flavor name fallback("3060lhr") 허용.
    """
    alias_map: dict[str, str] = {}
    for devices in PCI_DEVICE_MAP.values():
        for info in devices.values():
            if info.get("is_audio"):
                continue
            name = info["name"]
            for alias in info.get("aliases", []):
                if alias:
                    alias_map[alias] = name
                    # 정규화 키도 등록 (소문자, 구분자 제거) — exact match 우선 보장을 위해 setdefault
                    alias_map.setdefault(_normalize_alias_value(alias), name)
    return alias_map


def normalize_gpu_alias(alias: str) -> str:
    """GPU alias를 대표(canonical) 이름으로 정규화."""
    if not alias:
        return ""
    if "audio" in alias.lower():
        return ""
    import re

    return re.sub(r"[^a-zA-Z0-9]", "", alias).upper()


async def get_all_gpu_aliases() -> list[str]:
    """클러스터의 모든 GPU PCI alias 반환 (flavor extra_specs + Placement API 통합)."""
    import asyncio

    from app.database import is_db_available

    if is_db_available():
        try:
            from app.services import gpu_catalog

            await gpu_catalog.refresh_device_map_from_db()
        except Exception:
            _logger.warning("GPU 카탈로그 DB overlay 갱신 실패 — 기존 alias map으로 계속 진행", exc_info=True)

    from app.config import get_settings
    from app.services import nova

    def _collect():
        import openstack

        s = get_settings()
        admin_conn = openstack.connect(
            load_envvars=False,
            load_yaml_config=False,
            auth_url=s.os_auth_url,
            auth_type="password",
            username=s.os_username,
            password=s.os_password,
            project_name=s.os_project_name,
            user_domain_name=s.os_user_domain_name,
            project_domain_name=s.os_project_domain_name,
            region_name=s.os_region_name,
            api_timeout=30,
            verify=s.ssl_verify,
        )
        try:
            from app.api.identity.admin_gpu import build_device_name_to_alias_map

            aliases: set[str] = set()

            all_flavors = nova.list_flavors(admin_conn)
            for f in all_flavors:
                alias_str = (f.extra_specs or {}).get("pci_passthrough:alias", "")
                if alias_str:
                    for entry in alias_str.split(","):
                        entry = entry.strip()
                        if ":" in entry:
                            alias = entry.rpartition(":")[0].strip()
                            norm = normalize_gpu_alias(alias)
                            if norm:
                                aliases.add(norm)

            device_to_alias = build_device_name_to_alias_map()
            gpu_data = _collect_gpu_hosts(admin_conn)
            for gpu_type in gpu_data.get("gpu_types", []):
                device_name = gpu_type["device_name"]
                alias = device_to_alias.get(device_name)
                if alias:
                    norm = normalize_gpu_alias(alias)
                    if norm:
                        aliases.add(norm)

            return sorted(aliases)
        finally:
            admin_conn.close()

    return await asyncio.to_thread(_collect)


_NON_GPU_PCI_ALIAS_TOKENS = frozenset(
    {"audio", "crypto", "fpga", "infiniband", "network", "nic", "nvme", "qat", "rdma", "sriov"}
)


def is_gpu_flavor(flavor: Any = None, extra_specs: dict | None = None) -> bool:
    """Return whether a flavor requests a GPU-class PCI device."""
    if flavor is None and not extra_specs:
        return False

    name = ""
    specs = extra_specs or {}
    explicit_gpu: bool | None = None
    if isinstance(flavor, str):
        name = flavor
    elif isinstance(flavor, dict):
        name = flavor.get("original_name") or flavor.get("name") or flavor.get("id") or ""
        specs = flavor.get("extra_specs") or specs
        if isinstance(flavor.get("is_gpu"), bool):
            explicit_gpu = flavor["is_gpu"]
    elif flavor is not None:
        name = getattr(flavor, "name", "") or ""
        specs = getattr(flavor, "extra_specs", None) or specs
        stored_is_gpu = getattr(flavor, "__dict__", {}).get("is_gpu")
        if isinstance(stored_is_gpu, bool):
            explicit_gpu = stored_is_gpu
        elif not isinstance(getattr(type(flavor), "is_gpu", None), property) and isinstance(
            getattr(flavor, "is_gpu", None), bool
        ):
            explicit_gpu = flavor.is_gpu
    for entry in str(specs.get("pci_passthrough:alias", "")).split(","):
        entry = entry.strip()
        if not entry:
            continue
        alias_name = entry.rpartition(":")[0].strip() if ":" in entry else entry
        alias_lower = alias_name.lower()
        alias_tokens = {token for token in re.split(r"[^a-z0-9]+", alias_lower) if token}
        if alias_name and "audio" not in alias_lower and alias_tokens.isdisjoint(_NON_GPU_PCI_ALIAS_TOKENS):
            return True

    category = specs.get(":category", "")
    if category and "gpu" in str(category).lower():
        return True
    if explicit_gpu is not None:
        return explicit_gpu
    return isinstance(name, str) and name.lower().startswith(("gpu.", "gpu_", "g1."))


GpuQuotaDenied = gpu_quota.GpuQuotaDenied
GpuQuotaUnavailable = gpu_quota.GpuQuotaUnavailable


async def require_gpu_quota(conn: Any, flavor: Any) -> bool:
    """Require an affirmative GPU quota decision before mutation."""
    if not is_gpu_flavor(flavor):
        return False

    project_id = getattr(conn, "_afterglow_project_id", None) or getattr(conn, "current_project_id", None)

    flavor_extra_specs = (
        flavor.get("extra_specs") if isinstance(flavor, dict) else getattr(flavor, "extra_specs", None)
    ) or {}
    alias_str = flavor_extra_specs.get("pci_passthrough:alias", "")
    requested_gpus: dict[str, int] = {}
    if alias_str:
        for entry in str(alias_str).split(","):
            entry = entry.strip()
            if not entry or "audio" in entry.lower():
                continue
            if not is_gpu_flavor(extra_specs={"pci_passthrough:alias": entry}):
                continue
            if ":" in entry:
                alias_name, _, count_str = entry.rpartition(":")
                alias_name = alias_name.strip()
                try:
                    count = int(count_str.strip())
                    if count <= 0:
                        count = 1
                except ValueError:
                    count = 1
            else:
                alias_name = entry
                count = 1
            norm = normalize_gpu_alias(alias_name)
            if norm:
                requested_gpus[norm] = requested_gpus.get(norm, 0) + count

    if not requested_gpus:
        requested_gpus = {"GPU": 1}

    await gpu_quota.check_gpu_quota(conn, project_id, requested_gpus)
    return True
