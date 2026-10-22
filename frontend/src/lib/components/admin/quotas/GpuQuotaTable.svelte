<script lang="ts">
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import type { GpuQuota } from '$lib/types/quotas';
	import { t } from '$lib/i18n/ns/admin-identity';
  import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
  import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';
  import Button from '$lib/components/ui/Button.svelte';

	let {
		rows,
		defaults,
		loading,
		error,
		hasAnyAlias,
		onSetLimit,
		onClear,
	}: {
		rows: GpuQuota[];
		defaults: Record<string, number>;
		loading: boolean;
		error: string;
		hasAnyAlias: boolean;
		onSetLimit: (alias: string, limit: number) => void | Promise<void>;
		onClear: (alias: string) => void | Promise<void>;
	} = $props();

	let savingAliases = $state<Record<string, boolean>>({});
  let draftLimits = $state<Record<string, string>>({});
  $effect(() => { rows; draftLimits = {}; });

	async function changeLimit(alias: string, limit: number | null) {
		savingAliases[alias] = true;
    draftLimits[alias] = limit === null ? '' : String(limit);
		try {
			if (limit === null) await onClear(alias);
			else await onSetLimit(alias, limit);
		} finally {
			delete savingAliases[alias];
      delete draftLimits[alias];
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
    <ResponsiveTable>
      {#snippet cards()}
        {#each rows as q (q.gpu_type)}
          {@const alias = q.gpu_type}
          {@const defLimit = defaults[alias] ?? 0}
          {@const avail = q.limit === -1 ? -1 : q.limit - q.in_use}
          <CompactResourceCard>
            <strong class="break-all font-mono text-sm">{alias}</strong>
            <dl class="flex flex-wrap gap-3 text-xs"><div><dt class="text-ink-2">{t('gpuQuota.inUse')}</dt><dd>{q.in_use}</dd></div><div><dt class="text-ink-2">{t('gpuQuota.available')}</dt><dd>{q.limit === -1 ? t('gpuQuota.unlimited') : avail}</dd></div></dl>
            <label class="flex min-h-11 flex-wrap items-center justify-between gap-2 text-xs">{t('gpuQuota.projectLimit')}
              <input type="number" min="-1" value={draftLimits[alias] ?? q.limit ?? ''} placeholder={String(defLimit)} disabled={savingAliases[alias]} oninput={(event) => draftLimits[alias] = event.currentTarget.value} onchange={(event) => { const value = event.currentTarget.value; changeLimit(alias, value === '' ? null : Number(value)); }} class="min-h-11 w-24 rounded border border-line-2 bg-surface-sunken px-2 text-right text-sm text-ink-0" />
            </label>
            {#if savingAliases[alias]}<ActivityIndicator size="xs" label={t('gpuQuota.saving')} />{/if}
            {#snippet actions()}{#if q.limit != null}<Button variant="ghost" size="sm" disabled={savingAliases[alias]} title={t('gpuQuota.resetTitle')} onclick={() => changeLimit(alias, null)}>{t('gpuQuota.reset')}</Button>{/if}{/snippet}
            {#snippet details()}<dl class="text-xs"><dt class="text-ink-2">{t('gpuQuota.default')}</dt><dd>{defLimit === -1 ? t('gpuQuota.unlimited') : defLimit}</dd></dl>{/snippet}
          </CompactResourceCard>
        {/each}
      {/snippet}
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
                value={draftLimits[alias] ?? q.limit ?? ''}
								placeholder={String(defLimit)}
								disabled={savingAliases[alias]}
                oninput={(event) => draftLimits[alias] = event.currentTarget.value}
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
    </ResponsiveTable>
		<p class="text-xs text-ink-2 mt-2">{t('gpuQuota.limitHelp')}</p>

		<div class="mt-4 rounded-lg border border-[var(--color-line)] bg-[var(--color-surface-sunken)] p-3 text-xs text-[var(--color-ink-2)] leading-relaxed">
			<strong class="text-[var(--color-ink-1)] font-medium">{t('gpuQuota.scopeTitle')}</strong>
			{t('gpuQuota.scopeDescription')}
		</div>
	{/if}
</div>
