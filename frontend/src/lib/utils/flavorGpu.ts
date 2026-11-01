import type { FlavorOption } from '$lib/types/flavor';

export interface FlavorGpuRequest {
	model: string;
	count: number;
}

/** Managed groups use approved primary aliases; null means their roles are unverified. */
export function flavorGpuRequests(flavor: Pick<FlavorOption, 'extra_specs' | 'gpu_primary_aliases'> & { name?: string }): FlavorGpuRequest[] | null {
	if (flavor.extra_specs?.['afterglow:managed_by'] === 'domain-compute-v1') {
		if (flavor.gpu_primary_aliases == null) {
			return flavor.extra_specs?.['afterglow:access_mode'] === 'gpu_quota' || flavor.name?.startsWith('gpu.') ? null : [];
		}
		const counts = new Map<string, number>();
		for (const alias of flavor.gpu_primary_aliases) counts.set(alias.profile_name, (counts.get(alias.profile_name) ?? 0) + alias.count);
		return [...counts].map(([model, count]) => ({ model, count }));
	}
	return (flavor.extra_specs?.['pci_passthrough:alias'] ?? '')
		.split(',')
		.map(entry => entry.trim())
		.filter(entry => entry.includes(':') && !entry.toLowerCase().includes('audio'))
		.map(entry => {
			const separator = entry.lastIndexOf(':');
			return { model: entry.slice(0, separator).trim(), count: parseInt(entry.slice(separator + 1)) || 1 };
		});
}
