<script lang="ts">
	import { createUsageScheduleBell } from '../usageScheduleBell.svelte';
	import AnnouncementBellButton from '$lib/components/notifications/AnnouncementBellButton.svelte';
	let { enabled = true }: { enabled?: boolean } = $props();
	const usage = createUsageScheduleBell({ enabled: () => enabled });
	let open = $state(false);
</script>
<AnnouncementBellButton count={0} {open} usageCount={usage.count} usageOverdue={usage.overdue} usageUnavailable={usage.failed} usageLoading={usage.loading} onclick={() => { open = !open; void usage.refresh(); }} />
<output data-testid="count">{usage.count === null ? 'unknown' : usage.count}</output>
<output data-testid="overdue">{usage.overdue}</output>
<output data-testid="failed">{usage.failed}</output>
<output data-testid="loading">{usage.loading}</output>
<button data-testid="refresh" onclick={() => void usage.refresh()}>Refresh</button>
