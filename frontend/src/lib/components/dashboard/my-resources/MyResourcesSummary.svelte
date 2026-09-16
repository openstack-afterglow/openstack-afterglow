<script lang="ts">
	import StatTile from '$lib/components/ui/StatTile.svelte';
	import type { UserDashboardSummary } from '$lib/types/userDashboard';

	interface Props {
		totals: UserDashboardSummary['totals'];
	}

	let { totals }: Props = $props();

	function formatRam(mb: number): { value: number; unit: string } {
		if (mb >= 1024) return { value: +(mb / 1024).toFixed(1), unit: 'GB' };
		return { value: mb, unit: 'MB' };
	}

	const ram = $derived(formatRam(totals.ram_mb));
</script>

<div class="mb-5 grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-line bg-line sm:grid-cols-3 xl:grid-cols-6">
	<StatTile label="인스턴스" value={totals.instances} unit="개" accent="blue" flat>
		{#snippet icon()}
			<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2"/></svg>
		{/snippet}
	</StatTile>
	<StatTile label="볼륨" value={totals.volumes} unit="개" accent="cyan" flat>
		{#snippet icon()}
			<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4"/></svg>
		{/snippet}
	</StatTile>
	<StatTile label="스토리지" value={totals.storage_gb} unit="GB" accent="violet" flat>
		{#snippet icon()}
			<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4"/></svg>
		{/snippet}
	</StatTile>
	<StatTile label="vCPU" value={totals.vcpus} unit="코어" accent="emerald" flat>
		{#snippet icon()}
			<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 3H5a2 2 0 00-2 2v4m6-6h10a2 2 0 012 2v4M9 3v18m0 0h10a2 2 0 002-2V9M9 21H5a2 2 0 01-2-2V9m0 0h18"/></svg>
		{/snippet}
	</StatTile>
	<StatTile label="RAM" value={ram.value} unit={ram.unit} accent="amber" flat>
		{#snippet icon()}
			<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 17V7m0 10a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2h2a2 2 0 012 2m0 10a2 2 0 002 2h2a2 2 0 002-2M9 7a2 2 0 012-2h2a2 2 0 012 2m0 10V7m0 10a2 2 0 002 2h2a2 2 0 002-2V7a2 2 0 00-2-2h-2a2 2 0 00-2 2"/></svg>
		{/snippet}
	</StatTile>
	<StatTile label="Floating IP" value={totals.floating_ips} unit="개" accent="rose" flat>
		{#snippet icon()}
			<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9"/></svg>
		{/snippet}
	</StatTile>
</div>
