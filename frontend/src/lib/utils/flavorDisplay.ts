import type { FlavorOption } from '$lib/types/flavor';
import { t } from '$lib/i18n/ns/compute-pools';
import { flavorGpuRequests } from './flavorGpu';

type FlavorSpecification = Pick<FlavorOption, 'vcpus' | 'ram'> & Partial<FlavorOption>;

/** Consumer labels describe hardware, never the native name or identity used by API calls. */
export function consumerFlavorLabel(flavor: FlavorSpecification | null | undefined): string {
	if (!flavor || !Number.isFinite(flavor.vcpus) || flavor.vcpus <= 0 || !Number.isFinite(flavor.ram) || flavor.ram <= 0) return t('unknown');
	const parts = [`${flavor.vcpus} vCPU`, `${flavor.ram / 1024} GiB RAM`];
	const gpu = flavorGpuRequests(flavor);
	if (gpu === null) parts.push(`GPU · ${t('unknown')}`);
	else if (gpu.length > 0) parts.push(...gpu.map(({ model, count }) => `${model} × ${count}`));
	else if ((flavor.gpu_count ?? flavor.composition?.gpu_count ?? 0) > 0) parts.push(`GPU × ${flavor.gpu_count ?? flavor.composition?.gpu_count}`);
	else if (flavor.is_gpu) parts.push(`GPU · ${t('unknown')}`);
	return parts.join(' · ');
}

/** Prefer verified specifications; retain historical native names without interpreting them as hardware. */
export function consumerInstanceFlavorLabel(instance: { flavor_display_name?: string | null; flavor_name?: string | null }): string {
	const match = /^(?:cpu|mem)\.([1-9]\d*)c_((?:\d+\.)?\d+)g$/.exec(instance.flavor_display_name ?? '');
	if (!match) return instance.flavor_name?.trim() || t('unknown');
	return consumerFlavorLabel({ vcpus: Number(match[1]), ram: Number(match[2]) * 1024 });
}
