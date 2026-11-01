<script lang="ts">
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import { t } from '$lib/i18n/ns/dashboard-home';
	import { t as tc } from '$lib/i18n/ns/common';
	import type { Snippet } from 'svelte';
	import type { DashboardRecentInstance } from '$lib/types/compute';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import StatusChip from '$lib/components/ui/StatusChip.svelte';
	import { CompactResourceCard, ResponsiveTable, TableShell } from '$lib/components/ui';
	import { consumerInstanceFlavorLabel } from '$lib/utils/flavorDisplay';

	let {
		instances,
		pending,
		error,
		loaded = false,
		emptyContent,
	}: {
		instances: DashboardRecentInstance[];
		pending: boolean;
		error: string | null;
		loaded?: boolean;
		emptyContent?: Snippet;
	} = $props();

	function getFirstIp(instance: DashboardRecentInstance): string {
		return instance.ip_addresses?.[0]?.addr ?? '—';
	}
</script>

<Card padding="lg">
	<div class="flex items-center mb-3.5">
		<div class="text-[var(--color-ink-0)] text-[15px] font-semibold">{t('recentInstances.title')}</div>
		<a href="/dashboard/compute/instances" class="ml-auto text-[13px] text-[var(--color-ink-2)] hover:text-[var(--color-ink-0)] transition-colors">{t('recentInstances.viewAll')}</a>
	</div>

	{#if error && (loaded || instances.length > 0)}
		<Alert tone="danger" class="mb-3">
			<span>{t('recentInstances.loadFailed')}</span>
		</Alert>
	{/if}

	{#if pending && !loaded && instances.length === 0}
		<LoadingState variant="section" label={tc('state.loadingNamed', { name: t('recentInstances.title') })} />
	{:else if error && !loaded && instances.length === 0}
		<Alert tone="danger"><span>{t('recentInstances.loadFailed')}</span></Alert>
	{:else if instances.length === 0}
		{#if emptyContent}{@render emptyContent()}{:else}<p class="py-2 text-sm text-ink-2">{t('recentInstances.empty')}</p>{/if}
	{:else}
		<ResponsiveTable>
			{#snippet cards()}
				{#each instances as instance (instance.id)}
					<CompactResourceCard>
						<a class="font-medium text-ink-0 hover:underline" href="/dashboard/instances/{encodeURIComponent(instance.id)}">{instance.name}</a>
						<StatusChip status={instance.status} kind="server" />
						<dl class="flex flex-wrap gap-x-5 gap-y-1 text-sm text-ink-2"><div><dt>IP</dt><dd class="tabular-nums">{getFirstIp(instance)}</dd></div><div><dt>{t('recentInstances.flavor')}</dt><dd>{consumerInstanceFlavorLabel(instance)}</dd></div></dl>
					</CompactResourceCard>
				{/each}
			{/snippet}
			<TableShell><table>
				<thead><tr><th>{t('recentInstances.name')}</th><th>{t('recentInstances.status')}</th><th>IP</th><th>{t('recentInstances.flavor')}</th></tr></thead>
				<tbody>{#each instances as instance (instance.id)}<tr><td><a class="font-medium text-ink-0 hover:underline" href="/dashboard/instances/{encodeURIComponent(instance.id)}">{instance.name}</a></td><td><StatusChip status={instance.status} kind="server" /></td><td class="tabular-nums">{getFirstIp(instance)}</td><td>{consumerInstanceFlavorLabel(instance)}</td></tr>{/each}</tbody>
			</table></TableShell>
		</ResponsiveTable>
	{/if}
</Card>

