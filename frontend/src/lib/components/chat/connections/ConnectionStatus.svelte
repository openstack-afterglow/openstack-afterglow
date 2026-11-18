<script module lang="ts">
	export type ConnectionState = 'active' | 'inactive' | 'needsAuth' | 'stale' | 'error';
</script>
<script lang="ts">
	let { state, label }: { state: ConnectionState; label: string } = $props();
</script>

<span class="status" data-connection-status={state}>
	<svg aria-hidden="true" viewBox="0 0 20 20" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
		{#if state === 'active'}<circle cx="10" cy="10" r="7.5"/><path d="m6.5 10 2.3 2.3 4.7-4.6"/>
		{:else if state === 'inactive'}<circle cx="10" cy="10" r="7.5"/><path d="M7 10h6"/>
		{:else if state === 'needsAuth'}<rect x="4.5" y="9" width="11" height="8" rx="2"/><path d="M7 9V6a3 3 0 1 1 6 0v3m-3 3v2"/>
		{:else if state === 'stale'}<path d="M17.5 10a7.5 7.5 0 1 1-2.1-5.2l2.1 2.2m0-4v4h-4M10 6.5V10l2.5 1.5"/>
		{:else}<path d="M9 3.8a1.1 1.1 0 0 1 2 0l6.5 11a1.2 1.2 0 0 1-1 1.7h-13a1.2 1.2 0 0 1-1-1.7Z M10 8v3m0 2.5h.01"/>{/if}
	</svg>
	{label}
</span>

<style>
	.status { display: inline-flex; align-items: center; gap: 0.375rem; font-size: var(--type-support); color: var(--color-ink-2); }
	svg { flex: none; }
	[data-connection-status='active'] svg { color: var(--color-state-success); }
	[data-connection-status='needsAuth'] svg, [data-connection-status='stale'] svg { color: var(--color-state-warning); }
	[data-connection-status='error'] svg { color: var(--color-state-danger); }
</style>
