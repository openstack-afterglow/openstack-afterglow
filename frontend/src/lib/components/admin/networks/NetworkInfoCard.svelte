<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-network';
	import Card from '$lib/components/ui/Card.svelte';
	import type { AdminNetworkDetail } from '$lib/types/networks';

	let { network }: { network: AdminNetworkDetail } = $props();

	const providerTypeLower = $derived(network.provider_network_type?.toLowerCase().trim() ?? '');
	const isVlan = $derived(providerTypeLower === 'vlan');
	const isVxlan = $derived(providerTypeLower === 'vxlan');
	const isSupportedProvider = $derived(isVlan || isVxlan);

	const visibleProviderType = $derived(network.provider_network_type ? network.provider_network_type.toUpperCase() : '');
	const segmentationLabel = $derived(isVlan ? t('networkInfoCard.vlanTag') : isVxlan ? 'VXLAN VNI' : '');
	const segmentationValue = $derived(
		network.provider_segmentation_id !== null && network.provider_segmentation_id !== undefined
			? String(network.provider_segmentation_id)
			: '—'
	);
</script>

<Card padding="lg" class="mb-4">
	<h2 class="text-sm font-semibold text-[var(--color-ink-0)] uppercase tracking-wide mb-3">{t('networkInfoCard.title')}</h2>
	<dl class="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-3">
		<div>
			<dt class="text-xs text-[var(--color-ink-3)] mb-0.5">{t('networkInfoCard.networkId')}</dt>
			<dd class="text-sm text-[var(--color-ink-1)] font-mono break-all">{network.id}</dd>
		</div>
		<div>
			<dt class="text-xs text-[var(--color-ink-3)] mb-0.5">{t('networkInfoCard.subnetCount')}</dt>
			<dd class="text-sm text-[var(--color-ink-1)]">{network.subnets.length}</dd>
		</div>
		<div>
			<dt class="text-xs text-[var(--color-ink-3)] mb-0.5">{t('networkInfoCard.type')}</dt>
			<dd class="text-sm text-[var(--color-ink-1)]">
				{#if network.is_external}{t('networkInfoCard.external')}{/if}
				{#if network.is_external && network.is_shared} / {/if}
				{#if network.is_shared}{t('networkInfoCard.shared')}{/if}
				{#if !network.is_external && !network.is_shared}{t('networkInfoCard.internal')}{/if}
			</dd>
		</div>
		<div>
			<dt class="text-xs text-[var(--color-ink-3)] mb-0.5">{t('networkInfoCard.status')}</dt>
			<dd class="text-sm text-[var(--color-ink-1)]">{network.status}</dd>
		</div>

		{#if isSupportedProvider}
			<div>
				<dt class="text-xs text-[var(--color-ink-3)] mb-0.5">{t('networkInfoCard.providerType')}</dt>
				<dd class="text-sm text-[var(--color-ink-1)] font-mono">{visibleProviderType}</dd>
			</div>
			<div>
				<dt class="text-xs text-[var(--color-ink-3)] mb-0.5">{segmentationLabel}</dt>
				<dd class="text-sm text-[var(--color-ink-1)] font-mono">{segmentationValue}</dd>
			</div>
			{#if network.provider_physical_network !== null && network.provider_physical_network !== undefined}
				<div>
					<dt class="text-xs text-[var(--color-ink-3)] mb-0.5">{t('networkInfoCard.physicalNetwork')}</dt>
					<dd class="text-sm text-[var(--color-ink-1)] font-mono break-all">{network.provider_physical_network}</dd>
				</div>
			{/if}
		{/if}
	</dl>
</Card>
