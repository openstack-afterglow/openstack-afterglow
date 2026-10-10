import type { RunActivityItem } from '$lib/api/chatRunReducer';

/** Lifecycle stages stay in the journal, not in the user-facing task disclosure. */
export function visibleActivityItems(items: RunActivityItem[], active: boolean): RunActivityItem[] {
	return [...items].sort((a, b) => a.seq - b.seq).filter((item) => {
		if (item.kind === 'context') return active || item.phase === 'compacted';
		if (item.kind === 'tool' || item.kind === 'reasoning') return true;
		return item.stage === 'awaiting_input' || (item.stage === 'tool_execution' && item.toolName !== null &&
			!items.some((candidate) => candidate.kind === 'tool' && candidate.name === item.toolName && candidate.seq > item.seq));
	});
}

/** Only the latest journal stage can still be running; earlier stages are historical. */
export function activityIsRunning(item: RunActivityItem, items: RunActivityItem[], active: boolean): boolean {
	if (!active) return false;
	if (item.kind === 'tool') return item.status === 'running';
	if (item.kind === 'reasoning') return item.active;
	if (item.kind === 'context') return item.phase === 'compacting' && !items.some((next) => next.kind === 'context' && next.seq > item.seq);
	return !items.some((next) => next.seq > item.seq);
}
