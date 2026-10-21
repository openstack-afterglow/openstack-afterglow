<script lang="ts">
	import { t } from '$lib/i18n/ns/images-keys';
	import RichText from '$lib/i18n/RichText.svelte';
	import { useImageDetailController, isReservedKey } from '$lib/stores/imageDetailController.svelte';
	import { ActivityIndicator, Alert, AnimatedNumber, CompactResourceCard, ResponsiveTable } from '$lib/components/ui';

	const s = useImageDetailController();
	const setupLocked = $derived(s.windowsEditing || s.windowsSaving);
	const controlsLocked = $derived(!s.canEditMetadata || s.savingProps || setupLocked || s.savingVisibility);
</script>

{#snippet countSnippet(text: string)}
	{@const count = Object.keys(s.image!.properties).length}
	<span class="normal-case font-normal text-ink-2"><AnimatedNumber value={count} format={(value) => String(Math.round(value))} /></span>
{/snippet}

<div class="min-w-0 bg-surface-base border border-line rounded-lg p-4 md:p-5" data-testid="image-properties-section">
	<div class="flex flex-wrap items-center justify-between gap-2 mb-3">
		<h3 class="text-xs font-semibold text-ink-2 uppercase tracking-wide">
			<RichText segments={t.rich('propertiesSection.title', { count: Object.keys(s.image!.properties).length })} tags={{ count: countSnippet }} />
		</h3>
		{#if s.canEditMetadata && !s.editingProps}
			<button onclick={() => { if (!controlsLocked) s.startEditProps(); }} disabled={controlsLocked}
				data-testid="properties-edit" class="min-h-11 lg:min-h-0 text-xs text-warm-text hover:text-warm-text-hover disabled:opacity-50 disabled:cursor-not-allowed">{t('propertiesSection.edit')}</button>
		{/if}
	</div>

	{#if setupLocked}
		<div class="mb-3 break-words" data-testid="properties-setup-lock">
			<Alert tone="neutral">{t('propertiesSection.setupLock')}</Alert>
		</div>
	{/if}
	{#if !s.canEditMetadata}
		<p class="text-xs text-ink-2 mb-3">{t('propertiesSection.readonly')}</p>
	{/if}

	{#if !s.editingProps}
		{#if Object.keys(s.image!.properties).length === 0}
			<p class="text-xs text-ink-2">{t('propertiesSection.empty')}</p>
		{:else}
			<ResponsiveTable>
				{#snippet cards()}
					{#each Object.entries(s.image!.properties) as [k, v] (k)}
						<CompactResourceCard>
							<h4 class="text-xs font-medium font-mono text-ink-1 break-all line-clamp-2" title={k}>{k}</h4>
							<p class="text-xs font-mono text-ink-2 break-all line-clamp-2" title={v}>{v}</p>
							{#snippet details()}<p class="text-xs font-mono text-ink-1 break-all whitespace-pre-wrap">{v}</p>{/snippet}
						</CompactResourceCard>
					{/each}
				{/snippet}
			<table class="w-full table-fixed text-xs">
				<tbody>
					{#each Object.entries(s.image!.properties) as [k, v]}
						<tr class="border-b border-line/50">
							<td class="py-1.5 pr-4 text-ink-2 font-mono w-2/5 break-all align-top">{k}</td>
							<td class="py-1.5 text-ink-2 font-mono break-all">{v}</td>
						</tr>
					{/each}
				</tbody>
			</table>
			</ResponsiveTable>
		{/if}
	{:else}
		<ResponsiveTable class="max-lg:mb-3">
			{#snippet cards()}
				{#each Object.entries(s.propsDraft) as [k, v] (k)}
					<CompactResourceCard>
						<h4 class="text-xs font-medium font-mono text-ink-1 break-all line-clamp-2" title={k}>
							{k}{#if isReservedKey(k)} <span class="text-ink-2">{t('propertiesSection.reserved')}</span>{/if}
						</h4>
						{#if isReservedKey(k)}
							<p class="text-xs font-mono text-ink-2 break-all line-clamp-2" title={v}>{v}</p>
						{:else}
							<input bind:value={s.propsDraft[k]} disabled={controlsLocked} aria-label={`${t('propertiesSection.valuePlaceholder')}: ${k}`}
								class="w-full min-w-0 min-h-11 bg-surface-sunken border border-line-2 rounded px-2 py-1 text-ink-0 font-mono text-xs focus:outline-none focus:border-action-warm disabled:opacity-50" />
						{/if}
						{#snippet details()}<p class="text-xs font-mono text-ink-1 break-all whitespace-pre-wrap">{v}</p>{/snippet}
						{#snippet actions()}
							{#if !isReservedKey(k)}
								<button onclick={() => { if (!controlsLocked) s.removeProperty(k); }} disabled={controlsLocked}
									aria-label={`${t('propertiesSection.delete')}: ${k}`} class="min-h-11 text-state-danger-text text-xs disabled:opacity-50 disabled:cursor-not-allowed">{t('propertiesSection.delete')}</button>
							{/if}
						{/snippet}
					</CompactResourceCard>
				{/each}
			{/snippet}
		<table class="motion-fade w-full table-fixed text-xs mb-3">
			<tbody>
				{#each Object.entries(s.propsDraft) as [k, v]}
					<tr class="border-b border-line/50">
						<td class="py-1.5 pr-2 font-mono w-2/5 text-ink-2 break-all align-top">
							{k}{#if isReservedKey(k)}&nbsp;<span class="text-xs text-ink-2">{t('propertiesSection.reserved')}</span>{/if}
						</td>
						<td class="py-1.5 pr-2">
							{#if isReservedKey(k)}
								<span class="text-ink-2 font-mono break-all">{v}</span>
							{:else}
								<input bind:value={s.propsDraft[k]} disabled={controlsLocked} aria-label={`${t('propertiesSection.valuePlaceholder')}: ${k}`}
									class="w-full min-w-0 bg-surface-sunken border border-line-2 rounded px-2 py-1 text-ink-0 font-mono text-xs focus:outline-none focus:border-action-warm disabled:opacity-50" />
							{/if}
						</td>
						<td class="py-1.5 text-right w-10">
							{#if !isReservedKey(k)}
								<button onclick={() => { if (!controlsLocked) s.removeProperty(k); }} disabled={controlsLocked}
									aria-label={`${t('propertiesSection.delete')}: ${k}`} class="min-h-11 md:min-h-0 text-state-danger-text text-xs disabled:opacity-50 disabled:cursor-not-allowed">{t('propertiesSection.delete')}</button>
							{/if}
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
		</ResponsiveTable>

		<div class="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] gap-2 mb-3">
			<input bind:value={s.newPropKey} placeholder={t('propertiesSection.keyPlaceholder')} aria-label={t('propertiesSection.keyPlaceholder')} disabled={controlsLocked}
				class="w-full min-w-0 min-h-11 lg:min-h-0 bg-surface-sunken border border-line-2 rounded px-2 py-2 lg:py-1 text-xs text-ink-0 font-mono focus:outline-none focus:border-action-warm disabled:opacity-50"
				onkeydown={(e) => { if (e.key === 'Enter') { e.preventDefault(); if (!controlsLocked) s.addProperty(); } }} />
			<input bind:value={s.newPropValue} placeholder={t('propertiesSection.valuePlaceholder')} aria-label={t('propertiesSection.valuePlaceholder')} disabled={controlsLocked}
				class="w-full min-w-0 min-h-11 lg:min-h-0 bg-surface-sunken border border-line-2 rounded px-2 py-2 lg:py-1 text-xs text-ink-0 font-mono focus:outline-none focus:border-action-warm disabled:opacity-50"
				onkeydown={(e) => { if (e.key === 'Enter') { e.preventDefault(); if (!controlsLocked) s.addProperty(); } }} />
			<button onclick={() => { if (!controlsLocked) s.addProperty(); }} disabled={controlsLocked} class="min-h-11 lg:min-h-0 text-xs text-warm-text hover:text-warm-text-hover px-2 disabled:opacity-50 disabled:cursor-not-allowed">{t('propertiesSection.add')}</button>
		</div>

		{#if s.propsError}
			<p class="text-state-danger-text text-xs mb-2 break-words" role="alert">{s.propsError}</p>
		{/if}

		<div class="flex flex-wrap gap-2 justify-end">
			<button onclick={() => { if (!controlsLocked) s.cancelEditProps(); }} disabled={controlsLocked} data-testid="props-cancel"
				class="min-h-11 lg:min-h-0 text-xs text-ink-2 hover:text-ink-0 px-3 py-2 lg:py-1 border border-line-2 rounded disabled:opacity-50 disabled:cursor-not-allowed">{t('propertiesSection.cancel')}</button>
			<button onclick={() => { if (!controlsLocked) s.saveProperties(); }} disabled={controlsLocked} data-testid="props-save" aria-busy={s.savingProps}
				class="min-h-11 lg:min-h-0 text-xs text-action-on-warm bg-action-warm hover:bg-action-warm-hover disabled:bg-surface-selected disabled:text-ink-2 disabled:opacity-50 disabled:cursor-not-allowed px-3 py-2 lg:py-1 rounded">
				{#if s.savingProps}<ActivityIndicator size="xs" label={t('propertiesSection.saving')} />{:else}{t('propertiesSection.save')}{/if}
			</button>
		</div>
	{/if}
</div>
