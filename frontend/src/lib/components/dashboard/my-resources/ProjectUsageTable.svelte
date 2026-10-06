<script lang="ts">
	import { t } from '$lib/i18n/ns/dashboard-home';
	import type { ProjectData } from '$lib/types/userDashboard';
	import AnimatedNumber from '$lib/components/ui/AnimatedNumber.svelte';

	interface Props {
		projects: ProjectData[];
	}

	let { projects }: Props = $props();

	function formatRam(mb: number): string {
		if (mb >= 1024) return `${(mb / 1024).toFixed(1)} GB`;
		return `${mb} MB`;
	}
</script>

{#if projects.length > 0}
	<div class="motion-enter hidden sm:block bg-surface-base border border-line rounded-lg p-5 mb-5">
		<div class="text-ink-0 text-[15px] font-semibold mb-3.5">{t('projectUsage.title')}</div>
		<div class="bg-[#0B1220] border border-line rounded-lg overflow-hidden">
			<div class="grid grid-cols-[1.5fr_80px_80px_90px_80px_90px] px-4 py-2.5 border-b border-line text-xs uppercase tracking-wider text-ink-2 font-medium">
				<div>{t('projectUsage.project')}</div>
				<div class="text-right">{t('projectUsage.instances')}</div>
				<div class="text-right">{t('projectUsage.volumes')}</div>
				<div class="text-right">{t('projectUsage.storage')}</div>
				<div class="text-right">vCPU</div>
				<div class="text-right">RAM</div>
			</div>
			{#each projects as p (p.project_id)}
				<div class="grid grid-cols-[1.5fr_80px_80px_90px_80px_90px] px-4 py-3 text-[13px] items-center border-b border-line last:border-b-0 hover:bg-surface-sunken/20 transition-colors">
					<div class="min-w-0">
						<div class="text-ink-0 font-medium truncate">{p.project_name}</div>
						{#if p.error}
							<span class="text-xs text-red-400">{t('projectUsage.loadFailed')}</span>
						{/if}
					</div>
					<div class="text-right">
						{#if p.instance_count > 0}
							<span class="text-ink-0 font-mono text-xs font-medium"><AnimatedNumber value={p.instance_count} /></span>
						{:else}
							<span class="text-ink-2 text-xs">—</span>
						{/if}
					</div>
					<div class="text-right">
						{#if p.volume_count > 0}
							<span class="text-ink-0 font-mono text-xs font-medium"><AnimatedNumber value={p.volume_count} /></span>
						{:else}
							<span class="text-ink-2 text-xs">—</span>
						{/if}
					</div>
					<div class="text-right">
						{#if p.storage_gb > 0}
							<span class="text-ink-0 font-mono text-xs"><AnimatedNumber value={p.storage_gb} /> GB</span>
						{:else}
							<span class="text-ink-2 text-xs">—</span>
						{/if}
					</div>
					<div class="text-right">
						{#if p.vcpus > 0}
							<span class="text-ink-0 font-mono text-xs"><AnimatedNumber value={p.vcpus} /></span>
						{:else}
							<span class="text-ink-2 text-xs">—</span>
						{/if}
					</div>
					<div class="text-right">
						{#if p.ram_mb > 0}
							<span class="text-ink-0 font-mono text-xs"><AnimatedNumber value={p.ram_mb} format={(mb) => p.ram_mb >= 1024 ? `${(mb / 1024).toFixed(1)} GB` : `${Math.round(mb)} MB`} /></span>
						{:else}
							<span class="text-ink-2 text-xs">—</span>
						{/if}
					</div>
				</div>
			{/each}
		</div>
	</div>
{/if}
