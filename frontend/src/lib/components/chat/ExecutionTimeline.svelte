<script lang="ts">
	import type { RunActivityItem } from '$lib/api/chatRunReducer';
	import type { ToolActivityItem } from '$lib/api/chatToolActivity';
	import { taskLabelForContext, taskLabelForStage } from '$lib/api/chatTaskLabels';
	import ToolCategoryGroup from './ToolCategoryGroup.svelte';
	import ThinkingBlock from './ThinkingBlock.svelte';

	interface Props {
		items: RunActivityItem[];
		active?: boolean;
	}
	let { items, active = false }: Props = $props();

	type TimelineEntry =
		| { kind: 'item'; item: Exclude<RunActivityItem, { kind: 'tool' }> }
		| { kind: 'tool-group'; id: string; category: string; items: Extract<RunActivityItem, { kind: 'tool' }>[] };
	let open = $state(false);
	$effect(() => {
		if (active) open = true;
	});

	const orderedItems = $derived([...items].sort((left, right) => left.seq - right.seq));
	const taskItems = $derived(
		orderedItems.filter((item) => {
			if (item.kind === 'context') return active || item.phase === 'compacted';
			if (item.kind === 'tool' || item.kind === 'reasoning') return true;
			if (item.kind !== 'stage') return false;
			if (item.stage === 'awaiting_input') return true;
			return (
				item.stage === 'tool_execution' &&
				item.toolName !== null &&
				!orderedItems.some(
					(candidate) =>
						candidate.kind === 'tool' &&
						candidate.name === item.toolName &&
						candidate.seq > item.seq
				)
			);
		})
	);

	function stageLabel(item: Extract<RunActivityItem, { kind: 'stage' }>): string {
		return taskLabelForStage(item.stage, item.toolName) ?? '작업을 준비하는 중';
	}

	function contextLabel(item: Extract<RunActivityItem, { kind: 'context' }>): string {
		return taskLabelForContext(item.phase, item.cause);
	}

	function isLive(item: RunActivityItem): boolean {
		if (!active) return false;
		return item.kind === 'stage' || (item.kind === 'context' && item.phase === 'compacting') || (item.kind === 'tool' && item.status === 'running');
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
		<summary aria-label="작업 내역 열기">
			<span class="summary-mark" aria-hidden="true"></span>
			<span class="summary-title">실행 기록</span>
			<span class="summary-count">{taskItems.length}개 단계</span>
			<svg class="summary-chevron" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
				<path d="M6 9l6 6 6-6" stroke-linecap="round" stroke-linejoin="round" />
			</svg>
		</summary>
		<ol aria-label="실행 기록">
			{#each entries as entry (entry.kind === 'tool-group' ? entry.id : entry.item.id)}
				<li class:live={entry.kind === 'tool-group' ? entry.items.some((item) => isLive(item)) : isLive(entry.item)}>
					<span class="timeline-dot" aria-hidden="true"></span>
					<div class="timeline-entry">
						{#if entry.kind === 'tool-group'}
							<ToolCategoryGroup
								category={entry.category}
								items={entry.items.map(toolItem)}
								active={active && entry.items.some((item) => item.status === 'running')}
							/>
						{:else if entry.item.kind === 'context'}
							<p class="stage-label">{contextLabel(entry.item)}</p>
						{:else if entry.item.kind === 'stage'}
							<p class="stage-label">{stageLabel(entry.item)}</p>
						{:else}
							<ThinkingBlock text={entry.item.text} active={entry.item.active} />
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
		transition: transform 0.15s ease;
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
		position: absolute;
		left: -0.26rem;
		top: 0.47rem;
		width: 0.44rem;
		height: 0.44rem;
		border: 2px solid var(--color-surface-sunken);
	}
	li.live .timeline-dot {
		background: var(--color-warm);
		box-shadow: 0 0 0 3px color-mix(in oklab, var(--color-warm) 20%, transparent);
	}
	.stage-label {
		margin: 0.27rem 0;
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
