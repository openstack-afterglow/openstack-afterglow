<script lang="ts">
	import { t } from '$lib/i18n/ns/vm-wizard';
	import { closeWizard } from '$lib/stores/wizard';
	import { useVmCreate } from '$lib/stores/vmCreateStore.svelte';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import { Alert, Button } from '$lib/components/ui';

	const s = useVmCreate();
</script>

<div class="flex items-start justify-between mb-6">
	<div>
		<h1 class="text-xl font-bold text-ink-0">{t('adminProject.title')} <span class="text-sm font-normal text-warm-text ml-1">{t('adminProject.admin')}</span></h1>
		<p class="text-sm text-ink-2 mt-0.5">{t('adminProject.subtitle')}</p>
	</div>
	<!-- 닫기는 SlidePanel(`[data-slide-panel-close]`)과 하단 취소 버튼이 담당한다. -->
</div>

<p class="text-sm text-ink-2 mb-4">{t('adminProject.hint')}</p>

{#if s.adminProjectsLoading}
	<LoadingState variant="section" label={t('adminProject.loading')} />
{:else if s.adminProjectsError}
	<Alert tone="danger" title={t('adminProject.loadFailed')}>
		<p class="break-words">{s.adminProjectsError}</p>
		{#snippet actions()}<Button variant="secondary" size="sm" onclick={() => { void s.loadAdminProjects(); }}>{t('panel.retry')}</Button>{/snippet}
	</Alert>
{:else if s.adminProjects.length === 0}
	<div class="py-10 text-center text-sm text-ink-2">{t('adminProject.catalogEmpty')}</div>
{:else}
	<div class="relative mb-3">
		<svg class="w-4 h-4 text-ink-2 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" fill="none" stroke="currentColor" viewBox="0 0 24 24">
			<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-4.35-4.35M10 18a8 8 0 100-16 8 8 0 000 16z"/>
		</svg>
		<input
			type="text"
			aria-label={t('adminProject.search')}
			bind:value={s.adminProjectSearch}
			placeholder={t('adminProject.search')}
			class="w-full min-h-11 md:min-h-9 rounded-lg border border-line bg-surface-base pl-9 pr-12 py-2 text-sm text-ink-1 placeholder-ink-2 focus-visible:outline-none focus-visible:shadow-[var(--focus-ring)]"
		/>
		{#if s.adminProjectSearch}
			<button
				onclick={() => (s.adminProjectSearch = '')}
				class="absolute right-1 top-1/2 flex min-h-11 min-w-11 -translate-y-1/2 items-center justify-center text-ink-2 hover:text-ink-0"
				aria-label={t('adminProject.clearSearch')}
			><svg class="h-4 w-4" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-width="1.5" d="m6 6 12 12M18 6 6 18" /></svg></button>
		{/if}
	</div>

	{#if s.filteredAdminProjects.length === 0}
		<div class="py-10 text-center text-sm text-ink-2"><p>{t('adminProject.empty')}</p><Button variant="secondary" size="sm" class="mt-3" onclick={() => (s.adminProjectSearch = '')}>{t('adminProject.clearSearch')}</Button></div>
	{:else}
		<div class="max-h-[60vh] divide-y divide-line overflow-y-auto bg-surface-base">
			{#each s.filteredAdminProjects as proj}
				{@const q = s.adminProjectQuotas.get(proj.id)}
				<button
					onclick={() => s.selectAdminProject(proj.id, proj.name)}
					title={`${proj.name} · ${proj.domain_name ?? t('adminProject.domainUnknown')} · ${proj.domain_id ?? ''} · ${proj.id}`}
					class="w-full min-h-11 px-4 py-3 text-left transition-colors hover:bg-surface-selected focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ink-2"
				>
					<div class="flex min-w-0 flex-col items-start justify-between gap-3 @lg/panel:flex-row">
						<div class="min-w-0 flex-1">
							<div class="break-words text-sm font-medium text-ink-0">{proj.name}</div>
							<div class="mt-1 flex flex-wrap items-baseline gap-x-3 gap-y-1 text-[0.8125rem] text-ink-2">
								<span class="break-all" title={proj.domain_id ?? undefined}>{t('adminProject.domain', { name: proj.domain_name ?? proj.domain_id ?? t('adminProject.domainUnknown') })}</span>
								<span class="font-mono" title={proj.id}>{proj.id.slice(0, 8)}</span>
							</div>
						</div>
						{#if s.adminProjectQuotasLoading}
							<LoadingState variant="inline" label={t('adminProject.quotaLoading')} />
						{:else if q}
							<div class="flex min-w-0 flex-wrap items-center gap-1.5 @lg/panel:max-w-[55%] @lg/panel:justify-end">
								<span class="rounded border border-line bg-surface-base px-1.5 py-0.5 text-xs tabular-nums {s.isExhausted(q.instances) ? 'text-state-danger-text' : 'text-ink-2'}" title={t('adminProject.instancesQuota', { used: q.instances?.used ?? 0, quota: q.instances?.quota < 0 ? '∞' : q.instances?.quota ?? '' })}>
									VM {s.fmtRemaining(q.instances)}
								</span>
								<span class="rounded border border-line bg-surface-base px-1.5 py-0.5 text-xs tabular-nums {s.isExhausted(q.cpu) ? 'text-state-danger-text' : 'text-ink-2'}" title={t('adminProject.cpuQuota', { used: q.cpu?.used ?? 0, quota: q.cpu?.quota < 0 ? '∞' : q.cpu?.quota ?? '' })}>
									CPU {s.fmtRemaining(q.cpu)}
								</span>
								<span class="rounded border border-line bg-surface-base px-1.5 py-0.5 text-xs tabular-nums {s.isExhausted(q.ram_mb) ? 'text-state-danger-text' : 'text-ink-2'}" title={t('adminProject.ramQuota', { used: q.ram_mb?.used ?? 0, quota: q.ram_mb?.quota < 0 ? '∞' : q.ram_mb?.quota ?? '' })}>
									RAM {q.ram_mb && q.ram_mb.quota >= 0 ? Math.max(0, Math.floor((q.ram_mb.quota - q.ram_mb.used) / 1024)) + 'GB' : '∞'}
								</span>
								<span class="rounded border border-line bg-surface-base px-1.5 py-0.5 text-xs tabular-nums {s.isExhausted(q.disk_gb) ? 'text-state-danger-text' : 'text-ink-2'}" title={t('adminProject.diskQuota', { used: q.disk_gb?.used ?? 0, quota: q.disk_gb?.quota < 0 ? '∞' : q.disk_gb?.quota ?? '' })}>
									{t('adminProject.diskRemaining', { amount: s.fmtRemaining(q.disk_gb), unit: q.disk_gb && q.disk_gb.quota >= 0 ? 'GB' : '' })}
								</span>
							</div>
						{:else}
							<div class="text-ink-2 text-xs flex-shrink-0">{t('adminProject.noQuota')}</div>
						{/if}
					</div>
				</button>
			{/each}
		</div>
	{/if}
{/if}

<div class="flex justify-start mt-6 pt-4 border-t border-line">
	<button
		onclick={closeWizard}
		class="px-4 py-2 text-sm text-ink-2 hover:text-ink-0 border border-line-2 rounded-lg hover:border-line-2 transition-colors"
	>{t('adminProject.cancel')}</button>
</div>
