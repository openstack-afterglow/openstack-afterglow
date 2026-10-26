<script lang="ts">
	import { t } from '$lib/i18n/ns/topology';
	import type { CanvasDomainGroup, Rect } from './types';
	let { groups, rects, query, domainGroupLabel, panX, panY, k, world = false }: {
		groups: readonly CanvasDomainGroup[];
		rects: ReadonlyMap<string, Rect>;
		query: string;
		domainGroupLabel: (group: CanvasDomainGroup) => string;
		panX: number;
		panY: number;
		k: number;
		world?: boolean;
	} = $props();
</script>

{#each groups as group (group.id)}
	{@const rect = rects.get(group.id)}
	{#if rect}
		{#if world}
			<div class="domain-box" data-domain-box={group.id} style:left="{rect.x}px" style:top="{rect.y}px" style:width="{rect.w}px" style:height="{rect.h}px" aria-hidden="true"></div>
		{:else}
			<div class="domain-label" data-domain-label={group.id} style:left="{rect.x * k + panX + 10}px" style:top="{rect.y * k + panY + 4}px" style:width="{Math.max(1, rect.w * k - 20)}px" title="{domainGroupLabel(group)} — {t('domain.ownershipOnly')}" data-search-match={query.trim() && domainGroupLabel(group).toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()) ? 'true' : undefined}>
				{domainGroupLabel(group)}
			</div>
		{/if}
	{/if}
{/each}

<style>
	.domain-box { position: absolute; pointer-events: none; border: 1px solid var(--color-line-2); border-radius: var(--radius-lg); background: color-mix(in oklab, var(--color-topology-internal) var(--topology-zone-fill-alpha), transparent); }
	.domain-label { position: absolute; pointer-events: auto; font-size: 0.75rem; line-height: 1.5rem; font-weight: 600; color: var(--color-ink-1); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
	.domain-label[data-search-match] { color: var(--color-topology-internal); }
</style>
