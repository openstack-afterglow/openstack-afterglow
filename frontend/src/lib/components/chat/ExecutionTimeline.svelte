<script lang="ts">
	import { t } from '$lib/i18n/ns/chat-studio';
	import { untrack } from 'svelte';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import { activityIsRunning, visibleActivityItems } from './chatActivityPresentation';
	import type { RunActivityItem } from '$lib/api/chatRunReducer';
	import type { ToolActivityItem } from '$lib/api/chatToolActivity';
	import { taskLabelForContext, taskLabelForStage } from '$lib/api/chatTaskLabels';
	import ToolCategoryGroup from './ToolCategoryGroup.svelte';
	import ThinkingBlock from './ThinkingBlock.svelte';

	interface Props {
		items: RunActivityItem[];
		active?: boolean;
		animate?: boolean;
	}
	let { items, active = false, animate = active }: Props = $props();

	type TimelineEntry =
		| { kind: 'item'; item: Exclude<RunActivityItem, { kind: 'tool' }> }
		| { kind: 'tool-group'; id: string; category: string; items: Extract<RunActivityItem, { kind: 'tool' }>[] };
	let open = $state(false);
	const initialIds = untrack(() => new Set(items.map((item) => item.id)));
	const initialDone = untrack(() => new Set(items.filter((item) => !activityIsRunning(item, items, active)).map((item) => item.id)));
	$effect(() => {
		if (active) open = true;
	});

	const taskItems = $derived(visibleActivityItems(items, active));

	function stageLabel(item: Extract<RunActivityItem, { kind: 'stage' }>): string {
		return taskLabelForStage(item.stage, item.toolName) ?? t('executionTimeline.preparing');
	}

	function contextLabel(item: Extract<RunActivityItem, { kind: 'context' }>): string {
		return taskLabelForContext(item.phase, item.cause);
	}

	function isLive(item: RunActivityItem): boolean {
		return activityIsRunning(item, items, active);
	}

	function toolItem(item: Extract<RunActivityItem, { kind: 'tool' }>): ToolActivityItem {
		return {
			id: item.callId,
			name: item.name,
			args: JSON.stringify(item.arguments),
			result: item.content
				.filter((part) => part.type === 'text')
				.map((part) => part.text)
				.join('\n') || null,
			running: item.status === 'running',
			status: item.status === 'running' ? undefined : item.status,
			errorCode: item.errorCode,
			durationMs: item.durationMs,
			files: item.content.flatMap((part) =>
				part.type === 'file'
					? [{
							assetId: part.asset_id,
							name: part.name,
							mimeType: part.mime_type,
							sizeBytes: part.size_bytes
						}]
					: []
			)
		};
	}

	function timelineEntries(items: RunActivityItem[]): TimelineEntry[] {
		const entries: TimelineEntry[] = [];
		for (const item of items) {
			if (item.kind !== 'tool') {
				entries.push({ kind: 'item', item });
				continue;
			}
			const last = entries[entries.length - 1];
			if (last?.kind === 'tool-group' && last.category === item.category) {
				last.items.push(item);
				continue;
			}
			entries.push({
				kind: 'tool-group',
				id: `tool-group:${item.seq}:${item.category}`,
				category: item.category,
				items: [item]
			});
		}
		return entries;
	}

	const entries = $derived(timelineEntries(taskItems));
</script>

{#if entries.length}
	<details class="execution-timeline" bind:open>
		<summary aria-label={t('executionTimeline.openHistory')}>
			{#if active && !open && taskItems.some((item) => isLive(item))}
				<ActivityIndicator variant="orbit" size="xs" label={t('executionTimeline.inProgress')} />
			{:else}
				<span class="summary-mark" aria-hidden="true"></span>
			{/if}
			<span class="summary-title">{t('executionTimeline.history')}</span>
			<span class="summary-count">{t('executionTimeline.steps', { count: taskItems.length })}</span>
			<svg class="summary-chevron" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
				<path d="M6 9l6 6 6-6" stroke-linecap="round" stroke-linejoin="round" />
			</svg>
		</summary>
		<ol aria-label={t('executionTimeline.history')}>
			{#each entries as entry (entry.kind === 'tool-group' ? entry.id : entry.item.id)}
				<li class:motion-enter={animate && active && !(entry.kind === 'tool-group' ? initialIds.has(entry.items[0].id) : initialIds.has(entry.item.id))} class:live={entry.kind === 'tool-group' ? entry.items.some((item) => isLive(item)) : isLive(entry.item)}>
					{#if entry.kind === 'item' && !isLive(entry.item) && (entry.item.kind === 'context' || entry.item.kind === 'stage')}
						<svg class="timeline-check" class:motion-pop={animate && active && !initialDone.has(entry.item.id)} viewBox="0 0 16 16" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="m3 8 3 3 7-7" /></svg>
					{:else}
						<span class="timeline-dot" aria-hidden="true"></span>
					{/if}
					<div class="timeline-entry">
						{#if entry.kind === 'tool-group'}
							<ToolCategoryGroup
								category={entry.category}
								items={entry.items.map(toolItem)}
								active={active && entry.items.some((item) => item.status === 'running')}
								{animate}
							/>
						{:else if entry.item.kind === 'context'}
							<p class="stage-label">{#if isLive(entry.item)}<ActivityIndicator variant="orbit" size="xs" /> {/if}{contextLabel(entry.item)}</p>
						{:else if entry.item.kind === 'stage'}
							<p class="stage-label">{#if isLive(entry.item)}<ActivityIndicator size="xs" /> {/if}{stageLabel(entry.item)}</p>
						{:else}
							<ThinkingBlock text={entry.item.text} active={active && entry.item.active} {animate} />
						{/if}
					</div>
				</li>
			{/each}
		</ol>
	</details>
{/if}

<style>
	.execution-timeline {
		margin: 0 0 0.75rem;
		border: 1px solid var(--color-line);
		border-radius: 0.65rem;
		background: color-mix(in oklab, var(--color-surface-sunken) 76%, transparent);
	}
	summary {
		display: flex;
		align-items: center;
		gap: 0.45rem;
		padding: 0.55rem 0.65rem;
		cursor: pointer;
		list-style: none;
		color: var(--color-ink-2);
		font-size: 0.75rem;
	}
	summary::-webkit-details-marker {
		display: none;
	}
	.summary-mark,
	.timeline-dot {
		flex: 0 0 auto;
		width: 0.45rem;
		height: 0.45rem;
		border-radius: 50%;
		background: var(--color-state-info);
	}
	.summary-title {
		font-weight: 650;
		color: var(--color-ink-1);
	}
	.summary-count {
		color: var(--color-ink-2);
	}
	.summary-chevron {
		margin-left: auto;
		color: var(--color-ink-2);
		transition: transform var(--motion-duration-fast) var(--motion-ease-standard);
	}
	details[open] .summary-chevron {
		transform: rotate(180deg);
	}
	ol {
		margin: 0;
		padding: 0 0.65rem 0.65rem 1.35rem;
		list-style: none;
	}
	li {
		position: relative;
		min-height: 1.8rem;
		padding: 0.12rem 0 0.42rem 0.7rem;
		border-left: 1px solid var(--color-line);
	}
	li:last-child {
		padding-bottom: 0;
	}
	.timeline-dot {
		/* Mark position is layout-owned; only the check glyph pops in place. */
		position: absolute;
		left: -0.26rem;
		top: 0.47rem;
		width: 0.44rem;
		height: 0.44rem;
		border: 2px solid var(--color-surface-sunken);
	}
	.timeline-check {
		position: absolute;
		left: -0.4rem;
		top: 0.4rem;
		color: var(--color-state-success);
		background: var(--color-surface-sunken);
	}
	li.live .timeline-dot {
		background: var(--color-accent);
		box-shadow: 0 0 0 3px color-mix(in oklab, var(--color-accent) 20%, transparent);
	}
	.stage-label {
		margin: 0.27rem 0;
		display: flex;
		align-items: center;
		gap: 0.35rem;
		color: var(--color-ink-2);
		font-size: 0.76rem;
	}
	.timeline-entry :global(.thinking-block),
	.timeline-entry :global(.tool-card) {
		margin: 0;
	}
	@media (prefers-reduced-motion: reduce) {
		.summary-chevron {
			transition: none;
		}
	}
</style>
