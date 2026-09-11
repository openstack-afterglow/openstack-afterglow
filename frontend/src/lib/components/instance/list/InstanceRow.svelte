<script lang="ts">
	import type { Instance } from '$lib/types/compute';
	import StatusChip from '$lib/components/ui/StatusChip.svelte';
	import InstanceIpCell from './InstanceIpCell.svelte';
	import InstanceRowActions from './InstanceRowActions.svelte';
	import SelectionCheckbox from '$lib/components/ui/SelectionCheckbox.svelte';

	const strategyLabel: Record<string, string> = { prebuilt: '사전 빌드', dynamic: '동적 생성' };

	let {
		instance,
		isUnderutilized = false,
		selected = false,
		selectable = true,
		selectionDisabled = false,
		onSelect,
		onAction,
		onToggleSelect,
	}: {
		instance: Instance;
		isUnderutilized?: boolean;
		selected?: boolean;
		selectable?: boolean;
		selectionDisabled?: boolean;
		onSelect: (id: string) => void;
		onAction: (kind: 'console' | 'shelve' | 'unshelve' | 'delete', instance: Instance) => Promise<void>;
		onToggleSelect: () => void;
	} = $props();
</script>

<tr class="instance-row resource-selection-surface" data-selected={selected}>
	<td class="text-left">
		<SelectionCheckbox
			checked={selected}
			disabled={!selectable || selectionDisabled}
			unavailable={!selectable}
			title={!selectable ? '현재 상태에서는 선택할 수 없습니다.' : undefined}
			onclick={onToggleSelect}
			ariaLabel={`${instance.name || instance.id} 선택`}
		/>
	</td>
	<td>
		<button
			type="button"
			onclick={() => onSelect(instance.id)}
			class="flex min-w-0 items-center gap-2.5 text-left text-ink-0 transition-colors hover:text-action-warm-hover"
		>
			<span class="flex size-7 shrink-0 items-center justify-center rounded-md border border-line bg-surface-sunken">
				<svg class="size-3.5 text-ink-2" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
					<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2"/>
				</svg>
			</span>
			<span class="max-w-56 truncate font-medium">{instance.name}</span>
		</button>
	</td>
	<td><StatusChip status={instance.status} class="max-w-full truncate" /></td>
	<td class="text-xs">
		<div class="truncate text-ink-2">{instance.image_name ?? '볼륨에서 부팅'}</div>
		{#if instance.flavor_name}
			<div class="mt-0.5 flex items-center gap-1.5 text-ink-3">
				<span class="truncate">{instance.flavor_name}</span>
				{#if isUnderutilized}
					<span class="shrink-0 rounded border border-action-warm/60 bg-surface-selected px-1.5 py-0.5 text-[10px] font-medium text-action-warm">리사이즈 권장</span>
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
	<td class="text-xs text-ink-3">{instance.union_strategy ? strategyLabel[instance.union_strategy] ?? instance.union_strategy : '—'}</td>
	<InstanceRowActions {instance} {onAction} />
</tr>

