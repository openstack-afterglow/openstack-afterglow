<script lang="ts">
	import { t } from '$lib/i18n/ns/instance';
	import type { Instance } from '$lib/types/compute';
	import StatusChip from '$lib/components/ui/StatusChip.svelte';
	import InstanceIpCell from './InstanceIpCell.svelte';
	import InstanceRowActions from './InstanceRowActions.svelte';
	import SelectionCheckbox from '$lib/components/ui/SelectionCheckbox.svelte';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';

	const strategyKeys: Record<string, 'row.strategy.prebuilt' | 'row.strategy.dynamic'> = {
		prebuilt: 'row.strategy.prebuilt',
		dynamic: 'row.strategy.dynamic',
	};

	let {
		instance,
		isUnderutilized = false,
		selected = false,
		selectable = true,
		selectionDisabled = false,
		compact = false,
		acting = $bindable(false),
		onSelect,
		onAction,
		onToggleSelect,
	}: {
		instance: Instance;
		isUnderutilized?: boolean;
		selected?: boolean;
		selectable?: boolean;
		selectionDisabled?: boolean;
		compact?: boolean;
		acting?: boolean;
		onSelect: (id: string) => void;
		onAction: (kind: 'console' | 'shelve' | 'unshelve' | 'delete' | 'start' | 'stop', instance: Instance) => Promise<void>;
		onToggleSelect: () => void;
	} = $props();
</script>

{#if compact}
	<CompactResourceCard {selected}>
		<div class="flex min-w-0 items-start gap-2">
			<SelectionCheckbox checked={selected} disabled={!selectable || selectionDisabled} unavailable={!selectable} title={!selectable ? t('row.selectionUnavailable') : undefined} onclick={onToggleSelect} ariaLabel={t('row.select', { name: instance.name || instance.id })} />
			<button type="button" onclick={() => onSelect(instance.id)} title={instance.name || instance.id} class="min-h-11 min-w-0 flex-1 text-left font-medium text-ink-0 hover:text-warm-text-hover"><span class="line-clamp-2 break-words">{instance.name || instance.id}</span></button>
			<StatusChip status={instance.status} />
		</div>
		{#if acting}<ActivityIndicator size="xs" label={t('rowActions.processing')} />{/if}
		<div class="line-clamp-2 text-xs text-ink-2 break-words" title={instance.image_name ?? t('row.bootFromVolume')}>{instance.image_name ?? t('row.bootFromVolume')}</div>
		{#if instance.flavor_name}<div class="text-xs text-ink-2 break-words"><span class="line-clamp-2" title={instance.flavor_name}>{instance.flavor_name}</span>{#if isUnderutilized}<span class="text-warm-text">{t('row.resizeRecommended')}</span>{/if}</div>{/if}
		<p class="break-all font-mono text-xs text-ink-2">{instance.ip_addresses.find((ip) => ip.type === 'floating')?.addr ?? instance.ip_addresses[0]?.addr ?? '—'}</p>
		{#snippet actions()}<InstanceRowActions {instance} {onAction} bind:acting />{/snippet}
		{#snippet details()}
			<dl class="space-y-2 text-xs">
				<div><dt class="text-ink-2">ID</dt><dd class="break-all font-mono">{instance.id}</dd></div>
				<div><dt class="text-ink-2">IP</dt><dd class="space-y-1 break-all font-mono">{#each instance.ip_addresses as ip}<p>{ip.addr} · {ip.network_name} · {ip.type}</p>{:else}—{/each}</dd></div>
				<div><dt class="text-ink-2">{t('table.library')}</dt><dd class="break-words">{instance.union_libraries.filter(Boolean).join(', ') || '—'}</dd></div>
				<div><dt class="text-ink-2">{t('table.strategy')}</dt><dd>{instance.union_strategy ? (strategyKeys[instance.union_strategy] ? t(strategyKeys[instance.union_strategy]) : instance.union_strategy) : '—'}</dd></div>
			</dl>
		{/snippet}
	</CompactResourceCard>
{:else}
<tr class="motion-fade instance-row resource-selection-surface" data-selected={selected}>
	<td class="text-left">
		<SelectionCheckbox
			checked={selected}
			disabled={!selectable || selectionDisabled}
			unavailable={!selectable}
			title={!selectable ? t('row.selectionUnavailable') : undefined}
			onclick={onToggleSelect}
			ariaLabel={t('row.select', { name: instance.name || instance.id })}
		/>
	</td>
	<td>
		<button
			type="button"
			onclick={() => onSelect(instance.id)}
			class="flex min-w-0 items-center gap-2.5 text-left text-ink-0 transition-colors hover:text-warm-text-hover"
		>
			<span class="flex size-7 shrink-0 items-center justify-center rounded-md border border-line bg-surface-sunken">
				<svg class="size-3.5 text-ink-2" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
					<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2"/>
				</svg>
			</span>
			<span class="max-w-56 truncate font-medium">{instance.name}</span>
		</button>
	</td>
	<td>
		<StatusChip status={instance.status} class="max-w-full truncate" />
		{#if acting}<div class="mt-1"><ActivityIndicator size="xs" label={t('rowActions.processing')} /></div>{/if}
	</td>
	<td class="text-xs">
		<div class="truncate text-ink-2">{instance.image_name ?? t('row.bootFromVolume')}</div>
		{#if instance.flavor_name}
			<div class="mt-0.5 flex items-center gap-1.5 text-ink-2">
				<span class="truncate">{instance.flavor_name}</span>
				{#if isUnderutilized}
					<span class="shrink-0 rounded border border-action-warm/60 bg-surface-selected px-1.5 py-0.5 text-xs font-medium text-warm-text">{t('row.resizeRecommended')}</span>
				{/if}
			</div>
		{/if}
	</td>
	<td class="text-xs"><InstanceIpCell addresses={instance.ip_addresses} /></td>
	<td>
		<div class="flex flex-wrap gap-1">
			{#each instance.union_libraries.filter(Boolean) as lib}
				<span class="rounded bg-surface-selected px-1.5 py-0.5 text-xs text-ink-1">{lib}</span>
			{/each}
		</div>
	</td>
	<td class="text-xs text-ink-2">{instance.union_strategy ? (strategyKeys[instance.union_strategy] ? t(strategyKeys[instance.union_strategy]) : instance.union_strategy) : '—'}</td>
	<td class="text-right"><InstanceRowActions {instance} {onAction} bind:acting /></td>
</tr>
{/if}

