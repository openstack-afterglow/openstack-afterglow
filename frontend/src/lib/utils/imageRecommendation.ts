import type { ImageInfo } from '$lib/types/compute';
import type { FlavorOption } from '$lib/types/flavor';
import { currentImagesByReference } from '$lib/stores/imageCatalog.svelte';
import { normalizeGpuAlias, parseGpuAliasSpecs } from '$lib/components/admin/flavors/flavorGpuFilters';

export type GpuVendor = 'nvidia' | 'amd' | 'intel';
export interface ImageFlavorProfile {
	gpu: boolean;
	vendor: GpuVendor | null;
	virtual: boolean;
}
export type ImageRecommendation = 'gpu' | 'general';

const NON_GPU_ALIAS = /audio|sound|nic|network|ethernet|mellanox|connectx|infiniband|bluefield|dpu/i;

function aliasVendor(alias: string): GpuVendor | null {
	const value = normalizeGpuAlias(alias);
	if (/^(nvidia|geforce|quadro|tesla|titan|rtx|gtx)/.test(value)
		|| /^(a100|a10|a30|a40|a6000|h100|h200|l4|l40|v100|p100|t4)(?:\d|ti|s|pcie|sxm|$)/.test(value)) return 'nvidia';
	if (/^(amd|radeon|instinct)/.test(value) || /^mi(?:25|50|60|100|200|210|250|300|325|350)/.test(value)) return 'amd';
	if (/^intel(?:gpu|arc|flex|max)|^arc[ab]\d/.test(value)) return 'intel';
	return null;
}

/** Only resource requests count; names and arbitrary PCI devices are not GPU evidence. */
export function imageFlavorProfile(flavor: FlavorOption | null): ImageFlavorProfile | null {
	if (!flavor) return null;
	const specs = flavor.extra_specs ?? {};
	const aliases = new Set<string>();
	for (const entry of (specs['pci_passthrough:alias'] ?? '').split(',')) {
		const separator = entry.lastIndexOf(':');
		if (separator < 0 || !/^[1-9]\d*$/.test(entry.slice(separator + 1).trim())) continue;
		// Reuse the catalog's alias splitting/normalization, but not its broad
		// assumption that every non-audio PCI device is a GPU.
		for (const alias of parseGpuAliasSpecs({ 'pci_passthrough:alias': entry })) {
			if (!NON_GPU_ALIAS.test(alias) && (aliasVendor(alias) || /gpu/i.test(alias))) aliases.add(alias);
		}
	}
	// The backend's normalized GPU demand is useful for site-specific aliases,
	// even when their vendor cannot safely be inferred.
	for (const [alias, count] of Object.entries(flavor.eligibility?.requirements.gpus ?? {})) {
		if (count > 0 && !NON_GPU_ALIAS.test(alias)) aliases.add(alias);
	}
	const resources = Object.entries(specs).filter(([key, value]) =>
		/^resources[^:]*:[VP]GPU$/.test(key) && /^[1-9]\d*$/.test(value.trim()));
	const virtual = resources.some(([key]) => key.endsWith(':VGPU'));
	const vendors = [...aliases].map(aliasVendor);
	// Independent VGPU/PGPU requests carry no vendor identity. A known PCI
	// alias cannot supply vendor evidence for a separate resource request.
	const vendor = resources.length === 0 && vendors.length > 0
		&& vendors.every(value => value !== null && value === vendors[0]) ? vendors[0] : null;
	return { gpu: aliases.size > 0 || resources.length > 0, vendor, virtual };
}

/** Missing declarations are not proof of a CPU-only guest; unknown GPU metadata is never preferred for CPU. */
export function hasGpuImageMetadata(image: ImageInfo): boolean {
	const driver = image.gpu_driver?.trim().toLowerCase();
	return Boolean(image.gpu_vendor?.trim() || (driver && driver !== 'none'));
}

function driverMatches(image: ImageInfo, profile: ImageFlavorProfile): boolean {
	if (!profile.vendor || image.gpu_vendor?.trim().toLowerCase() !== profile.vendor) return false;
	const driver = image.gpu_driver?.trim().toLowerCase();
	if (profile.vendor === 'nvidia') return driver === 'nvidia' || driver === 'nouveau';
	if (profile.vendor === 'amd') return driver === 'amdgpu';
	return driver === 'i915' || driver === 'xe';
}

/** Resolve current UUIDs before filtering status, never falling back to an obsolete active upload. */
export function imageRecommendations(images: readonly ImageInfo[], flavor: FlavorOption | null): Map<string, ImageRecommendation> {
	const profile = imageFlavorProfile(flavor);
	const result = new Map<string, ImageRecommendation>();
	if (!profile || !flavor) return result;
	for (const image of currentImagesByReference(images).values()) {
		if (image.status !== 'active') continue;
		// Image boot uses a separately sized Cinder volume, not flavor.disk.
		if ((image.min_ram ?? 0) > flavor.ram) continue;
		if (profile.gpu) {
			if (image.verification_status === 'verified' && driverMatches(image, profile)) result.set(image.id, 'gpu');
		} else if (!hasGpuImageMetadata(image)) result.set(image.id, 'general');
	}
	return result;
}
