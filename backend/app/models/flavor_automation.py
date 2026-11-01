"""Strict administrator approval and retained hardware policy schemas."""

import re
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.compute_pools import MAX_AMOUNT, Revision

RC_PATTERN = re.compile(r"^CUSTOM_PCI_[0-9A-F]{4}_[0-9A-F]{4}$")
ALIAS_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
RESOURCE_SPEC_PATTERN = re.compile(r"^resources(?:[A-Za-z0-9_-]{1,64})?:([A-Z][A-Z0-9_]{0,254})$")
Positive = Annotated[int, Field(strict=True, ge=1, le=MAX_AMOUNT)]


class StrictBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


def alias_counts(specs):
    raw = specs.get("pci_passthrough:alias")
    if raw is None:
        return {}
    result = {}
    for item in raw.split(","):
        parts = item.rsplit(":", 1)
        if (
            len(parts) != 2
            or not ALIAS_PATTERN.fullmatch(parts[0])
            or not re.fullmatch(r"[1-9][0-9]{0,8}", parts[1])
            or parts[0] in result
        ):
            raise ValueError("Malformed or duplicate PCI alias")
        result[parts[0]] = int(parts[1])
    if not result or sum(result.values()) > 16:
        raise ValueError("PCI alias request exceeds supported bound")
    return result


class GpuProfile(StrictBody):
    name: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    display_name: str = Field(min_length=1, max_length=128)
    enabled: bool
    resource_class: str = Field(pattern=RC_PATTERN.pattern)
    resource_requirements: dict[str, Positive] = Field(min_length=1, max_length=16)
    extra_specs: dict[str, str] = Field(min_length=1, max_length=128)
    # Multiple aliases with equal quantities cannot be mapped from counts or labels.
    # This optional exact map makes their administrator authority explicit.
    alias_resource_classes: dict[str, str] = Field(default_factory=dict, max_length=16)

    @model_validator(mode="after")
    def scheduling_contract(self):
        if (
            not self.display_name.strip()
            or self.display_name != self.display_name.strip()
            or any(ord(char) < 32 for char in self.display_name)
        ):
            raise ValueError("Display name must not be blank, padded or contain controls")
        if any(not RC_PATTERN.fullmatch(key) for key in self.resource_requirements):
            raise ValueError("Only exact physical PCI resource classes are supported")
        if self.resource_requirements.get(self.resource_class) != 1:
            raise ValueError("Primary resource requirement must be exactly one per GPU")
        cpu_policy = self.extra_specs.get("hw:cpu_policy", "shared")
        if cpu_policy not in {"shared", "dedicated"} or self.extra_specs.get("hw:emulator_threads_policy") == "isolate":
            raise ValueError("CPU policy cannot be represented by retained supported inventory")
        explicit = {}
        for key, value in self.extra_specs.items():
            if (
                not key
                or len(key) > 255
                or not value
                or len(value) > 4096
                or key.lower().startswith("afterglow:")
                or key in {"is_public", "description", "name", "id"}
                or any(ord(char) < 32 for char in key + value)
            ):
                raise ValueError("Protected or malformed extra spec")
            if key.startswith("resources"):
                match = RESOURCE_SPEC_PATTERN.fullmatch(key)
                if not match or not re.fullmatch(r"[1-9][0-9]{0,8}", value):
                    raise ValueError("Malformed per-GPU resource quantity")
                resource = match[1]
                if resource not in self.resource_requirements:
                    raise ValueError("Resource spec must name an approved per-GPU requirement")
                explicit[resource] = explicit.get(resource, 0) + int(value)
        aliases = alias_counts(self.extra_specs)
        mapping = self.alias_resource_classes
        if aliases and not mapping and len(aliases) == len(self.resource_requirements) == 1:
            mapping = {next(iter(aliases)): self.resource_class}
            self.alias_resource_classes = mapping
        if set(mapping) != set(aliases) or any(
            resource not in self.resource_requirements for resource in mapping.values()
        ):
            raise ValueError("Ambiguous PCI alias resource classes require an exact mapping")
        alias_resources = {}
        for name, count in aliases.items():
            resource = mapping[name]
            alias_resources[resource] = alias_resources.get(resource, 0) + count
        # Nova's PCI aliases create independent Placement request groups; an
        # explicit request of the same RC is additional demand, never deduped.
        if alias_resources.keys() & explicit.keys():
            raise ValueError("PCI alias and explicit resource requests overlap")
        # Placement quantities reserve capacity but do not attach PCI devices.
        # Every physical function must therefore be represented by Nova aliases.
        if alias_resources != self.resource_requirements:
            raise ValueError("Every physical GPU and companion requires an exact PCI attachment alias")
        return self


def validate_profiles(values):
    profiles = [GpuProfile.model_validate(value).model_dump() for value in values]
    names, primaries, aliases, kinds = set(), set(), {}, {}
    for profile in profiles:
        if profile["name"] in names or profile["resource_class"] in primaries:
            raise ValueError("Duplicate GPU profile identity")
        names.add(profile["name"])
        primaries.add(profile["resource_class"])
        for alias, resource in profile["alias_resource_classes"].items():
            if alias in aliases and aliases[alias] != resource:
                raise ValueError("Ambiguous PCI alias identity")
            aliases[alias] = resource
        for resource in profile["resource_requirements"]:
            kind = "gpu" if resource == profile["resource_class"] else "companion"
            if resource in kinds and kinds[resource] != kind:
                raise ValueError("Ambiguous GPU and companion classification")
            kinds[resource] = kind
    return profiles


class PolicyUpdate(StrictBody):
    revision: Revision
    gpu_profiles: list[GpuProfile] = Field(max_length=128)

    @model_validator(mode="after")
    def unique_profiles(self):
        validate_profiles([value.model_dump() for value in self.gpu_profiles])
        return self


class HostUpdate(StrictBody):
    revision: Revision
    removed: bool
