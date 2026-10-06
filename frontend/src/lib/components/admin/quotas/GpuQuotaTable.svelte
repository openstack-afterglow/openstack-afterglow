<script lang="ts">
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import type { GpuQuota } from '$lib/types/quotas';
	import type { FlavorReconcileResponse } from '$lib/stores/adminQuotasController.svelte';
	import { t } from '$lib/i18n/ns/admin-identity';

	let {
		rows,
		defaults,
		loading,
		error,
		hasAnyAlias,
		onSetLimit,
		onClear,
		reconcilePreview,
	}: {
		rows: GpuQuota[];
		defaults: Record<string, number>;
		loading: boolean;
		error: string;
		hasAnyAlias: boolean;
		onSetLimit: (alias: string, limit: number) => void | Promise<void>;
		onClear: (alias: string) => void | Promise<void>;
		reconcilePreview?: FlavorReconcileResponse | null;
	} = $props();

	let savingAliases = $state<Record<string, boolean>>({});

	async function changeLimit(alias: string, limit: number | null) {
		savingAliases[alias] = true;
		try {
			if (limit === null) await onClear(alias);
			else await onSetLimit(alias, limit);
		} finally {
			delete savingAliases[alias];
		}
	}
</script>

<div class="bg-surface-base border border-line rounded-xl p-6 mb-6">
	<h2 class="text-sm font-semibold text-ink-2 uppercase tracking-wide mb-1">{t('gpuQuota.title')}</h2>
	<p class="text-xs text-ink-2 mb-4">{t('gpuQuota.description')}</p>
	{#if error}<div class="text-red-400 text-xs mb-3">{error}</div>{/if}
	{#if loading}
		<ActivityIndicator size="sm" label={t('gpuQuota.loading')} />
	{:else if rows.length === 0 && !hasAnyAlias}
		<div class="text-ink-2 text-sm">{t('gpuQuota.noAliases')}</div>
	{:else}
		<table class="w-full text-sm">
			<thead>
				<tr class="text-ink-2 text-xs border-b border-line">
					<th class="text-left pb-2">{t('gpuQuota.type')}</th>
					<th class="text-right pb-2">{t('gpuQuota.default')}</th>
					<th class="text-right pb-2">{t('gpuQuota.projectLimit')}</th>
					<th class="text-right pb-2">{t('gpuQuota.inUse')}</th>
					<th class="text-right pb-2">{t('gpuQuota.available')}</th>
					<th class="text-right pb-2"></th>
				</tr>
			</thead>
			<tbody>
				{#each rows as q}
					{@const alias = q.gpu_type}
					{@const defLimit = defaults[alias] ?? 0}
					{@const effectiveLimit = q.limit}
					{@const inUse = q.in_use}
					{@const avail = effectiveLimit === -1 ? -1 : effectiveLimit - inUse}
					<tr class="border-b border-line/50 last:border-0">
						<td class="py-2 text-ink-0 font-mono">{alias}</td>
						<td class="py-2 text-right text-ink-2">{defLimit === -1 ? t('gpuQuota.unlimited') : defLimit}</td>
						<td class="py-2 text-right">
							<input
								type="number"
								min="-1"
								value={q?.limit ?? ''}
								placeholder={String(defLimit)}
								disabled={savingAliases[alias]}
								onchange={(e) => {
									const v = (e.target as HTMLInputElement).value;
									if (v === '') {
										changeLimit(alias, null);
									} else {
										changeLimit(alias, Number(v));
									}
								}}
								class="w-20 bg-surface-selected border border-line-2 rounded px-2 py-1 text-sm text-ink-0 text-right focus:outline-none focus:border-action-warm"
							/>
							{#if savingAliases[alias]}
								<ActivityIndicator size="xs" label={t('gpuQuota.saving')} class="mt-1" />
							{/if}
						</td>
						<td class="py-2 text-right text-ink-2">{inUse}</td>
						<td class="py-2 text-right {avail > 0 ? 'text-green-400' : avail === -1 ? 'text-ink-2' : 'text-red-400'}">
							{effectiveLimit === -1 ? t('gpuQuota.unlimited') : avail}
						</td>
						<td class="py-2 text-right">
							{#if q?.limit != null}
								<button
									onclick={() => changeLimit(alias, null)}
									disabled={savingAliases[alias]}
									class="text-xs text-ink-2 hover:text-ink-2 transition-colors"
									title={t('gpuQuota.resetTitle')}
								>{t('gpuQuota.reset')}</button>
							{/if}
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
		<p class="text-xs text-ink-2 mt-2">{t('gpuQuota.limitHelp')}</p>

		{#if reconcilePreview && reconcilePreview.operations.length > 0}
			<div class="mt-6 border-t border-[var(--color-line)] pt-4">
				<h3 class="text-xs font-semibold text-[var(--color-ink-1)] uppercase tracking-wide mb-1">
					{t('gpuQuota.reconcileTitle')}
				</h3>
				<p class="text-xs text-[var(--color-ink-2)] mb-3">
					{t('gpuQuota.reconcileDescription')}
				</p>
				<div class="space-y-1.5">
					{#each reconcilePreview.operations as op}
						<div class="flex items-center justify-between rounded-lg bg-[var(--color-surface-sunken)] px-3 py-2 text-xs">
							<div class="flex items-center gap-2">
								<span class="font-mono text-[var(--color-ink-0)]">{op.flavor_name}</span>
								{#if op.action === 'add'}
									<span class="rounded bg-[var(--color-surface-base)] text-[var(--color-state-success-text)] border border-[var(--color-state-success)]/40 px-1.5 py-0.5 text-xs">{t('gpuQuota.accessAdd')}</span>
								{:else if op.action === 'remove'}
									<span class="rounded bg-[var(--color-surface-base)] text-[var(--color-state-danger-text)] border border-[var(--color-state-danger)]/40 px-1.5 py-0.5 text-xs">{t('gpuQuota.accessRemove')}</span>
								{:else}
									<span class="rounded bg-[var(--color-surface-base)] text-[var(--color-ink-2)] px-1.5 py-0.5 text-xs">{t('gpuQuota.accessKeep')}</span>
								{/if}
							</div>
							<span class="text-[var(--color-ink-2)] font-mono">
								{Object.entries(op.gpu_demand).map(([k, v]) => `${k} ×${v}`).join(', ')}
							</span>
						</div>
					{/each}
				</div>
			</div>
		{/if}

		<div class="mt-4 rounded-lg border border-[var(--color-line)] bg-[var(--color-surface-sunken)] p-3 text-xs text-[var(--color-ink-2)] leading-relaxed">
			<strong class="text-[var(--color-ink-1)] font-medium">{t('gpuQuota.scopeTitle')}</strong>
			{t('gpuQuota.scopeDescription')}
		</div>
	{/if}
</div>
