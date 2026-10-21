<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-identity';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
  import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
  import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';

	let {
		defaults,
		allGpuTypes,
		loading,
		error,
		success,
		onChange,
	}: {
		defaults: Record<string, number>;
		allGpuTypes: string[];
		loading: boolean;
		error: string;
		success: string;
		onChange: (alias: string, limit: number) => void | Promise<void>;
	} = $props();

	let savingAliases = $state<Record<string, boolean>>({});
  let draftLimits = $state<Record<string, string>>({});
  $effect(() => { defaults; draftLimits = {}; });

	async function changeLimit(alias: string, limit: number) {
		savingAliases[alias] = true;
    draftLimits[alias] = String(limit);
		try {
			await onChange(alias, limit);
		} finally {
			delete savingAliases[alias];
      delete draftLimits[alias];
		}
	}
</script>

<div class="bg-surface-base border border-line rounded-xl p-6 mb-6">
	<h2 class="text-sm font-semibold text-ink-2 uppercase tracking-wide mb-1">{t('gpuQuota.defaults.title')}</h2>
	<p class="text-xs text-ink-2 mb-4">{t('gpuQuota.defaults.description')}</p>
	{#if error}<div class="text-red-400 text-xs mb-3">{error}</div>{/if}
	{#if success}<div class="text-green-400 text-xs mb-3">{success}</div>{/if}
	{#if loading}
		<ActivityIndicator size="sm" label={t('gpuQuota.loading')} />
	{:else if allGpuTypes.length === 0}
		<div class="text-ink-2 text-sm">{t('gpuQuota.defaults.noAliases')}</div>
	{:else}
    <ResponsiveTable>
      {#snippet cards()}
        {#each allGpuTypes as alias (alias)}
          <CompactResourceCard>
            <strong class="break-all font-mono text-sm">{alias}</strong>
            <label class="flex min-h-11 flex-wrap items-center justify-between gap-2 text-xs">{t('gpuQuota.default')}<input type="number" min="-1" value={draftLimits[alias] ?? defaults[alias] ?? 0} disabled={savingAliases[alias]} oninput={(event) => draftLimits[alias] = event.currentTarget.value} onchange={(event) => changeLimit(alias, Number(event.currentTarget.value))} class="min-h-11 w-24 rounded border border-line-2 bg-surface-sunken px-2 text-right text-sm text-ink-0" /></label>
            {#if (defaults[alias] ?? 0) === -1}<span class="text-xs text-ink-2">{t('gpuQuota.unlimited')}</span>{/if}
            {#if savingAliases[alias]}<ActivityIndicator size="xs" label={t('state.saving')} />{/if}
          </CompactResourceCard>
        {/each}
      {/snippet}
		<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
			{#each allGpuTypes as alias}
				{@const currentLimit = defaults[alias] ?? 0}
				<div class="flex flex-wrap items-center gap-2 bg-surface-sunken/60 rounded-lg px-3 py-2">
					<span class="text-sm text-ink-0 font-mono flex-1">{alias}</span>
					<input
						type="number"
						min="-1"
            value={draftLimits[alias] ?? currentLimit}
						disabled={savingAliases[alias]}
            oninput={(event) => draftLimits[alias] = event.currentTarget.value}
						onchange={(e) => changeLimit(alias, Number((e.target as HTMLInputElement).value))}
						class="w-20 bg-surface-selected border border-line-2 rounded px-2 py-1 text-sm text-ink-0 text-right focus:outline-none focus:border-action-warm"
					/>
					{#if savingAliases[alias]}
						<ActivityIndicator size="xs" label={t('state.saving')} class="basis-full" />
					{/if}
				</div>
			{/each}
		</div>
    </ResponsiveTable>
		<p class="text-xs text-ink-2 mt-2">{t('gpuQuota.defaults.limitHelp')}</p>
	{/if}
</div>
