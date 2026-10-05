<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-identity';

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
		onChange: (alias: string, limit: number) => void;
	} = $props();
</script>

<div class="bg-surface-base border border-line rounded-xl p-6 mb-6">
	<h2 class="text-sm font-semibold text-ink-2 uppercase tracking-wide mb-1">{t('gpuQuota.defaults.title')}</h2>
	<p class="text-xs text-ink-2 mb-4">{t('gpuQuota.defaults.description')}</p>
	{#if error}<div class="text-red-400 text-xs mb-3">{error}</div>{/if}
	{#if success}<div class="text-green-400 text-xs mb-3">{success}</div>{/if}
	{#if loading}
		<div class="text-ink-2 text-sm">{t('gpuQuota.loading')}</div>
	{:else if allGpuTypes.length === 0}
		<div class="text-ink-2 text-sm">{t('gpuQuota.defaults.noAliases')}</div>
	{:else}
		<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
			{#each allGpuTypes as alias}
				{@const currentLimit = defaults[alias] ?? 0}
				<div class="flex items-center gap-2 bg-surface-sunken/60 rounded-lg px-3 py-2">
					<span class="text-sm text-ink-0 font-mono flex-1">{alias}</span>
					<input
						type="number"
						min="-1"
						value={currentLimit}
						onchange={(e) => onChange(alias, Number((e.target as HTMLInputElement).value))}
						class="w-20 bg-surface-selected border border-line-2 rounded px-2 py-1 text-sm text-ink-0 text-right focus:outline-none focus:border-action-warm"
					/>
				</div>
			{/each}
		</div>
		<p class="text-xs text-ink-2 mt-2">{t('gpuQuota.defaults.limitHelp')}</p>
	{/if}
</div>
