<script lang="ts">
	import { t } from '$lib/i18n/ns/network-resources';
	import type { LoadBalancerDetail, LbStatusNode } from '$lib/types/loadbalancer';
	import { ResponsiveTable, CompactResourceCard, StatusChip } from '$lib/components/ui';

	let { lb, statusTree }: { lb: LoadBalancerDetail; statusTree: LbStatusNode | null } = $props();
</script>

<div class="bg-red-900/20 border border-red-800 rounded-lg p-5 mb-4">
	<h2 class="text-sm font-semibold text-red-400 mb-3 flex items-center gap-2">
		<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg>
		{t('lb.errorTree.title')}
	</h2>
	{#if statusTree}
		<ResponsiveTable>
			{#snippet cards()}
				<CompactResourceCard><strong>{t('lb.errorTree.lbStatus')}</strong><StatusChip status={statusTree.provisioning_status ?? lb.status} /><p class="text-xs text-ink-2">{statusTree.operating_status ?? lb.operating_status}</p></CompactResourceCard>
				{#each statusTree.listeners ?? [] as listener}
					<CompactResourceCard><p class="text-xs text-ink-2">{t('lb.errorTree.listener')}</p><strong class="break-all">{listener.name || listener.id?.slice(0, 12)}</strong><StatusChip status={listener.provisioning_status ?? 'unknown'} /></CompactResourceCard>
					{#each listener.pools ?? [] as pool}
						<CompactResourceCard><p class="text-xs text-ink-2">{t('lb.errorTree.listener')}: {listener.name || listener.id?.slice(0, 12)} · {t('lb.errorTree.pool')}</p><strong class="break-all">{pool.name || pool.id?.slice(0, 12)}</strong><StatusChip status={pool.provisioning_status ?? 'unknown'} /></CompactResourceCard>
						{#each pool.members ?? [] as member}
							<CompactResourceCard><p class="text-xs text-ink-2">{t('lb.errorTree.pool')}: {pool.name || pool.id?.slice(0, 12)} · {t('lb.errorTree.member')}</p><strong class="break-all">{member.name || member.id?.slice(0, 12)}</strong><StatusChip status={member.provisioning_status ?? 'unknown'} /></CompactResourceCard>
						{/each}
					{/each}
				{/each}
				{#if !statusTree.listeners?.length}{#each statusTree.pools ?? [] as pool}
					<CompactResourceCard><p class="text-xs text-ink-2">{t('lb.errorTree.pool')}</p><strong class="break-all">{pool.name || pool.id?.slice(0, 12)}</strong><StatusChip status={pool.provisioning_status ?? 'unknown'} /></CompactResourceCard>
				{/each}{/if}
			{/snippet}
		<div class="space-y-2 text-xs font-mono">
			<div class="flex items-center gap-3">
				<span class="text-ink-2 w-32 shrink-0">{t('lb.errorTree.lbStatus')}</span>
				<span class="text-red-400">{statusTree.provisioning_status ?? lb.status}</span>
				<span class="text-ink-2">{statusTree.operating_status ?? lb.operating_status}</span>
			</div>
			{#if statusTree.listeners && statusTree.listeners.length > 0}
				{#each statusTree.listeners as listener}
					<div class="ml-4 flex items-center gap-3">
						<span class="text-ink-2 w-28 shrink-0">{t('lb.errorTree.listener')}</span>
						<span class="text-ink-2">{listener.name || listener.id?.slice(0, 12)}</span>
						<span class="{listener.provisioning_status === 'ERROR' ? 'text-red-400' : 'text-ink-2'}">{listener.provisioning_status}</span>
					</div>
					{#if listener.pools}
						{#each listener.pools as pool}
							<div class="ml-8 flex items-center gap-3">
								<span class="text-ink-2 w-24 shrink-0">{t('lb.errorTree.pool')}</span>
								<span class="text-ink-2">{pool.name || pool.id?.slice(0, 12)}</span>
								<span class="{pool.provisioning_status === 'ERROR' ? 'text-red-400' : 'text-ink-2'}">{pool.provisioning_status}</span>
							</div>
							{#if pool.members}
								{#each pool.members as member}
									<div class="ml-12 flex items-center gap-3">
										<span class="text-ink-2 w-20 shrink-0">{t('lb.errorTree.member')}</span>
										<span class="text-ink-2">{member.name || member.id?.slice(0, 12)}</span>
										<span class="{member.provisioning_status === 'ERROR' ? 'text-red-400' : 'text-ink-2'}">{member.provisioning_status}</span>
									</div>
								{/each}
							{/if}
						{/each}
					{/if}
				{/each}
			{/if}
			{#if statusTree.pools && statusTree.pools.length > 0 && (!statusTree.listeners || statusTree.listeners.length === 0)}
				{#each statusTree.pools as pool}
					<div class="ml-4 flex items-center gap-3">
						<span class="text-ink-2 w-28 shrink-0">{t('lb.errorTree.pool')}</span>
						<span class="text-ink-2">{pool.name || pool.id?.slice(0, 12)}</span>
						<span class="{pool.provisioning_status === 'ERROR' ? 'text-red-400' : 'text-ink-2'}">{pool.provisioning_status}</span>
					</div>
				{/each}
			{/if}
		</div>
		</ResponsiveTable>
	{:else}
		<p class="text-xs text-red-300">{t('lb.errorTree.unavailable')}</p>
	{/if}
</div>
