"""Conservative CPU-only labels; native flavor identity and scheduling stay untouched."""

from __future__ import annotations

import re

_CPU_HW_KEYS = frozenset(
    {
        "hw:cpu_policy",
        "hw:cpu_thread_policy",
        "hw:cpu_threads",
        "hw:cpu_cores",
        "hw:cpu_sockets",
        "hw:cpu_max_threads",
        "hw:cpu_max_cores",
        "hw:cpu_max_sockets",
        "hw:cpu_realtime",
        "hw:cpu_realtime_mask",
        "hw:cpu_dedicated_mask",
        "hw:cpu_model",
        "hw:cpu_features",
        "hw:emulator_threads_policy",
        "hw:numa_nodes",
        "hw:mem_page_size",
        "hw:locked_memory",
        "hw:watchdog_action",
        "hw:machine_type",
        "hw:firmware_type",
        "hw:boot_menu",
        "hw:serial_port_count",
        "hw:hide_hypervisor_id",
        "hw:pmu",
    }
)
_CPU_ANNOTATION_KEYS = frozenset(
    {
        "afterglow:managed_by",
        "afterglow:access_mode",
        "afterglow:frontend_visible",
        "afterglow:usage_schedule_required",
        "afterglow:cpu_control_token",
    }
)
_CPU_RESOURCES = frozenset({"VCPU", "PCPU", "MEMORY_MB", "DISK_GB"})
_ACCELERATOR_NAME = re.compile(r"(?:^|[.\s_-])(?:v?gpu|pci|fpga|accelerator)(?:$|[.\s_-]|\d)", re.IGNORECASE)
_NUMA_KEY = re.compile(r"hw:numa_(?:cpus|mem)\.\d+\Z")


def canonical_cpu_display_name(native_name: str, vcpus: int, ram_mb: int, extra_specs: dict | None) -> str | None:
    """Label only an explicit, known CPU-only native hardware snapshot.

    An absent SDK extra-spec descriptor is not an empty native map: callers must
    first obtain the actual native envelope. Unknown scheduling keys remain
    unclassified, including arbitrary capabilities, custom traits and resources.
    CPU-only includes memory-optimized hardware; the family uses its RAM ratio.
    This function never normalizes or alters the supplied native fields/specs.
    """
    if (
        not isinstance(native_name, str)
        or not native_name.strip()
        or _ACCELERATOR_NAME.search(native_name)
        or type(vcpus) is not int
        or vcpus <= 0
        or type(ram_mb) is not int
        or ram_mb <= 0
        or not isinstance(extra_specs, dict)
    ):
        return None
    for key, value in extra_specs.items():
        if not isinstance(key, str) or not isinstance(value, str):
            return None
        if key in {"afterglow:frontend_visible", "afterglow:usage_schedule_required"}:
            # These application annotations cannot request accelerator hardware.
            continue
        if not value.strip():
            return None
        if key in _CPU_ANNOTATION_KEYS:
            if key == "afterglow:managed_by" and value != "domain-compute-v1":
                return None
            if key == "afterglow:access_mode" and value != "domain_quota":
                return None
            continue
        if key in _CPU_HW_KEYS or _NUMA_KEY.fullmatch(key):
            if key == "hw:cpu_policy" and value not in {"shared", "dedicated", "mixed"}:
                return None
            if key == "hw:cpu_thread_policy" and value not in {"prefer", "require", "isolate"}:
                return None
            if key == "hw:emulator_threads_policy" and value not in {"share", "isolate"}:
                return None
            continue
        if key.startswith("resources:"):
            if key.removeprefix("resources:") not in _CPU_RESOURCES or not value.isascii() or not value.isdigit():
                return None
            continue
        if key.startswith("trait:HW_CPU_") and value in {"required", "forbidden"}:
            continue
        # Unknown extensions may request an accelerator even without a GPU name.
        return None
    whole_gib, remainder_mb = divmod(ram_mb, 1024)
    fraction = f"{remainder_mb * 9765625:010d}".rstrip("0")
    ram_gib = f"{whole_gib}.{fraction}" if fraction else str(whole_gib)
    family = "mem" if ram_mb >= 4096 * vcpus else "cpu"
    return f"{family}.{vcpus}c_{ram_gib}g"
