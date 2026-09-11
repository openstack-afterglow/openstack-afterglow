<script lang="ts">
	import type { DashboardRecentInstance } from '$lib/types/compute';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import StatusChip from '$lib/components/ui/StatusChip.svelte';

	let {
		instances,
		pending,
		error,
	}: {
		instances: DashboardRecentInstance[];
		pending: boolean;
		error: string | null;
	} = $props();

	function getFirstIp(instance: DashboardRecentInstance): string {
		return instance.ip_addresses?.[0]?.addr ?? '—';
	}
</script>

<Card padding="lg">
	<div class="flex items-center mb-3.5">
		<div class="text-[var(--color-ink-0)] text-[15px] font-semibold">최근 인스턴스</div>
		<a href="/dashboard/compute/instances" class="ml-auto text-[13px] text-[var(--color-ink-2)] hover:text-[var(--color-ink-0)] transition-colors">모두 보기 →</a>
	</div>

	{#if error && instances.length > 0}
		<Alert tone="danger" class="mb-3">
			<span>최근 인스턴스를 불러오지 못했습니다</span>
		</Alert>
	{/if}

	{#if pending && instances.length === 0}
		<div class="space-y-2">
			{#each Array(4) as _}
				<div class="h-10 bg-[var(--color-surface-sunken)] rounded animate-pulse"></div>
			{/each}
		</div>
	{:else if error && instances.length === 0}
		<Alert tone="danger">
			<span>최근 인스턴스를 불러오지 못했습니다</span>
		</Alert>
	{:else if instances.length === 0}
		<div class="text-[var(--color-ink-2)] text-sm py-6 text-center">인스턴스가 없습니다</div>
	{:else}
		<div class="overflow-x-auto">
			<div class="min-w-[620px]">
				<div class="grid grid-cols-[minmax(180px,1.7fr)_160px_130px_120px] rounded-t-lg border border-b-0 border-[var(--color-line)] bg-[var(--color-surface-sunken)] px-3.5 py-2 text-xs font-medium tracking-tight text-[var(--color-ink-2)]">
					<div>NAME</div>
					<div>STATUS</div>
					<div>IP</div>
					<div>FLAVOR</div>
				</div>
				<div class="recent-instance-list overflow-hidden rounded-b-lg border border-[var(--color-line)]">
					{#each instances as instance, i}
						<a href="/dashboard/compute/instances"
							class="recent-instance-row grid grid-cols-[minmax(180px,1.7fr)_160px_130px_120px] px-3.5 py-2.5 text-[13px] items-center hover:bg-[var(--color-surface-sunken)] transition-colors {i < instances.length - 1 ? 'border-b border-[var(--color-line)]' : ''}">
							<div class="text-[var(--color-ink-0)] font-medium truncate">{instance.name}</div>
							<div><StatusChip status={instance.status} /></div>
							<div class="text-[var(--color-ink-1)] font-mono text-xs">{getFirstIp(instance)}</div>
							<div class="text-[var(--color-ink-2)] text-xs">{instance.flavor_name ?? '—'}</div>
						</a>
					{/each}
				</div>
			</div>
		</div>
	{/if}
</Card>

<style>
	.recent-instance-row:nth-child(n + 6) {
		display: none;
	}

	@media (min-height: 840px) {
		.recent-instance-row:nth-child(n) {
			display: grid;
		}

		.recent-instance-row:nth-child(n + 9) {
			display: none;
		}
	}

	@media (min-height: 980px) {
		.recent-instance-row:nth-child(n) {
			display: grid;
		}

		.recent-instance-row:nth-child(n + 11) {
			display: none;
		}
	}

	@media (min-height: 1180px) {
		.recent-instance-row:nth-child(n) {
			display: grid;
		}
	}
</style>
