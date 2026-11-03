import type { RunActivityItem } from '$lib/api/chatRunReducer';

/** Retain factual model lifecycle steps as well as tool/reasoning activity. */
export function visibleActivityItems(items: RunActivityItem[], _active: boolean): RunActivityItem[] {
	return [...items].sort((a, b) => a.seq - b.seq).filter((item) =>
		item.kind !== 'stage' || item.stage !== 'tool_execution' || item.toolName === null ||
		!items.some((candidate) => candidate.kind === 'tool' && candidate.name === item.toolName && candidate.seq > item.seq)
	);
}

/** Only the latest journal stage can still be running; earlier stages are historical. */
export function activityIsRunning(item: RunActivityItem, items: RunActivityItem[], active: boolean): boolean {
	if (!active) return false;
	// Child creation reports admission only, not its current execution phase.
	if (item.kind === 'child') return false;
	if (item.kind === 'approval') return item.decision === null && !items.some((next) => next.kind === 'terminal');
	if (item.kind === 'terminal') return false;
	if (item.kind === 'tool') return item.status === 'running';
	if (item.kind === 'reasoning') return item.active;
	if (item.kind === 'context') return item.phase === 'compacting' && !items.some((next) => next.kind === 'context' && next.seq > item.seq);
	return !items.some((next) => next.seq > item.seq);
}
