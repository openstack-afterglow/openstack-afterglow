import { onDestroy, onMount, untrack } from 'svelte';
import { get } from 'svelte/store';
import { loadUsageSchedules } from '$lib/api/usageSchedules';
import { auth } from '$lib/stores/auth';
import { authDisplayContext } from '$lib/stores/authDisplayContext';
import { scheduleUrgency, validUsageSchedule } from '$lib/utils/instanceUsage';
import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';

export function createUsageScheduleBell(options: { enabled: () => boolean }) {
	let count = $state<number | null>(null);
	let overdue = $state(0);
	let loading = $state(false);
	let failed = $state(false);
	let enabled = $state(false);
	let epoch = 0;
	let controller: AbortController | null = null;
	let owner: { key: string; project: string } | null = null;
	let disposed = false;
	let mounted = false;

	async function refresh() {
		if (!enabled || !owner || controller || disposed) return;
		const requestOwner = owner;
		const token = get(auth).token;
		if (!token) return;
		const generation = epoch;
		controller = new AbortController();
		loading = true;
		failed = false;
		try {
			const result = await loadUsageSchedules(token, requestOwner.project, controller.signal);
			if (disposed || generation !== epoch) return;
			if (!result || !Array.isArray(result.schedules) || !Array.isArray(result.errors)
				|| result.errors.some(row => !row || typeof row !== 'object' || !('instance_id' in row)
					|| typeof row.instance_id !== 'string' || !row.instance_id || !('message' in row) || typeof row.message !== 'string')) throw new Error('Invalid usage inventory');
			let due = result.errors.length;
			let expired = result.errors.length;
			for (const schedule of result.schedules) {
				if (!validUsageSchedule(schedule)) {
					due += 1;
					expired += 1;
					continue;
				}
				const urgency = scheduleUrgency(schedule);
				if (urgency) due += 1;
				if (urgency === 'expired' || urgency === 'attention') expired += 1;
			}
			count = due;
			overdue = expired;
			failed = false;
		} catch {
			if (disposed || generation !== epoch) return;
			count = null;
			overdue = 0;
			failed = true;
		} finally {
			if (!disposed && generation === epoch) { controller = null; loading = false; }
		}
	}
	function reset() {
		epoch += 1;
		controller?.abort();
		controller = null;
		count = null; overdue = 0; failed = false; loading = false;
	}
	$effect(() => {
		const allowed = options.enabled();
		untrack(() => {
			if (allowed === enabled) return;
			enabled = allowed;
			reset();
			if (mounted) void refresh();
		});
	});
	onMount(() => {
		mounted = true;
		const unsubscribe = authDisplayContext.subscribe(next => {
			if (owner?.key === next.key) return;
			reset();
			owner = next.ready ? { key: next.key, project: next.project! } : null;
			void refresh();
		});
		return unsubscribe;
	});
	createAutoRefresh(() => refresh(), { storageKey: 'announcement-unread-count', defaultInterval: 60, invokeOnMount: false });
	onDestroy(() => { disposed = true; reset(); });
	return {
		get count() { return count; }, get overdue() { return overdue; }, get failed() { return failed; }, get loading() { return loading; },
		refresh,
	};
}
