<script lang="ts">
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import type { ComponentProps } from 'svelte';
	import SelectFlavor from './SelectFlavor.svelte';
	import { Alert, Button, Field, SearchSelect, ToggleGroup } from '$lib/components/ui';
	import ResourceQuantityInput from '$lib/components/ui/ResourceQuantityInput.svelte';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import { t } from '$lib/i18n/ns/vm-wizard';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import { flavorCreateBlock, type FlavorOption } from '$lib/types/flavor';
	import type { FlavorComposerController } from '$lib/stores/flavorComposer';
	import { resourceDraftReset, validFlavorComposition, type FlavorComposerMode } from '$lib/stores/flavorResourceDraft';
	import { consumerFlavorLabel } from '$lib/utils/flavorDisplay';

	type Props = ComponentProps<typeof SelectFlavor> & { controller: FlavorComposerController };
	let { controller, ...picker }: Props = $props();
	const ar = createAutoRefresh(async force => { await refresh(force ? 'manual' : 'periodic'); }, { storageKey: 'vm-create-flavor-capacity', defaultActive: true, defaultInterval: 15, invokeOnMount: false });
	async function refresh(mode: 'manual' | 'periodic') {
		if ($controller.saving || !$controller.ready) return;
		await Promise.all([controller.refresh(mode), controller.loadHistory(), picker.onRefresh(mode)]);
	}
	const locked = $derived(!$controller.ready || $controller.saving);
	const editLocked = $derived(locked || $controller.unknown);
	let quantityReset = $state(0);
	const quantityResetKey = $derived(`${quantityReset}:${$resourceDraftReset}:${$controller.draftScope}:${$controller.quantityRevision}`);
	const options = $derived($controller.options);
	const tuple = $derived($controller.composition);
	const cpuInvalid = $derived(tuple.vcpus < 2 || tuple.vcpus % 2 !== 0 || Boolean(options && !options.vcpus.includes(tuple.vcpus)));
	const ramInvalid = $derived(Boolean(options && !options.ram_mb.includes(tuple.ram_mb)));
	const profileInvalid = $derived(Boolean(tuple.gpu_profile_id && options && !options.gpu_profiles.some(profile => profile.id === tuple.gpu_profile_id && profile.status === 'available')));
	const gpuChoices = $derived([{ value: '', label: t('composer.noGpu') }, ...(options?.gpu_profiles ?? []).filter(profile => profile.status === 'available').map(profile => ({ value: profile.id, label: profile.name, description: profile.id }))]);
	const retainedGpu = $derived(options?.gpu_profiles.find(profile => profile.id === tuple.gpu_profile_id)?.name ?? tuple.gpu_profile_id);
	const countInvalid = $derived(Boolean(tuple.gpu_profile_id && options && !options.gpu_counts.includes(tuple.gpu_count)));
	const preview = $derived<FlavorOption>(options?.selection ?? { id: 'composer-preview', name: '', vcpus: tuple.vcpus, ram: tuple.ram_mb, disk: 0, is_public: false });
	const checkedAt = $derived(options?.checked_at ? new Date(options.checked_at).toLocaleTimeString(intlLocale()) : '');
</script>

<div class="flex min-w-0 flex-col gap-4" data-testid="flavor-composer">
	<ToggleGroup value={$controller.mode} ariaLabel={t('composer.mode')} options={[
		{ value: 'compose', label: t('composer.direct'), disabled: editLocked },
		{ value: 'saved', label: t('composer.saved'), disabled: editLocked },
		{ value: 'catalog', label: t('composer.catalog'), disabled: editLocked },
	]} onchange={value => controller.setMode(value as FlavorComposerMode)} />
	<div class="flex flex-wrap items-center justify-between gap-2">
		<p class="text-xs text-ink-2" role="status" aria-live="polite">
			{#if !$controller.ready}<LoadingState variant="inline" label={t('composer.authPending')} />
			{:else if $controller.loading || $controller.refreshing}<LoadingState variant="inline" label={t('composer.checking')} />
			{:else if checkedAt}{t('flavor.refresh.checkedAt', { time: checkedAt })}
			{:else}{t('flavor.refresh.neverChecked')}{/if}
		</p>
		<AutoRefreshControl bind:active={ar.active} bind:intervalSeconds={ar.intervalSeconds} intervalOptions={ar.intervalOptions} refreshing={$controller.refreshing || $controller.saving} onManualRefresh={() => { void ar.refresh(); }} />
	</div>
	{#if $controller.error}
		<Alert tone="danger" title={t('composer.checkFailed')}><p class="break-words">{$controller.error}</p>{#snippet actions()}<Button variant="secondary" disabled={locked} onclick={() => { void refresh('manual'); }}>{t('flavor.refresh.retry')}</Button>{/snippet}</Alert>
	{:else if $controller.backgroundError}
		<Alert tone="warning">{t('flavor.refresh.backgroundFailed')}</Alert>
	{/if}
	{#if $controller.unknown}
		<Alert tone="warning" title={t('composer.unknownTitle')}>
			{t('composer.unknownBody')}
			{#snippet actions()}<Button variant="secondary" disabled={locked || $controller.historyLoading} onclick={() => { void controller.verifyUnknown(); }}>{t('composer.verifySaved')}</Button>{/snippet}
		</Alert>
	{/if}
	{#if $controller.saveError}<Alert tone="danger" title={t('composer.saveFailed')}><p class="break-words">{$controller.saveError}</p></Alert>{/if}
	{#if $controller.ready && !$controller.canWrite}<Alert tone="warning">{t('composer.readOnly')}</Alert>{/if}
	{#if $controller.mode === 'compose'}
		<p class="text-sm text-ink-2">{t('composer.help')}</p>
		<div class="grid min-w-0 grid-cols-1 gap-5">
			<ResourceQuantityInput id="flavor-composer-cores" label={t('composer.cores')} unit="vCPU" value={tuple.vcpus} values={options?.vcpus} min={2} max={128} step={2} disabled={editLocked} invalid={cpuInvalid} unavailable={t('composer.unavailable')} resetKey={quantityResetKey} bind:pending={() => $controller.quantityPending.vcpus, pending => controller.setQuantityPending('vcpus', pending)} onvalue={vcpus => controller.edit({ vcpus })} />
			<ResourceQuantityInput id="flavor-composer-ram" label={t('composer.ram')} unit="GiB" value={tuple.ram_mb / 1024} values={options?.ram_mb.map(value => value / 1024)} min={1} max={2048} disabled={editLocked} invalid={ramInvalid} unavailable={t('composer.unavailable')} resetKey={quantityResetKey} bind:pending={() => $controller.quantityPending.ram_mb, pending => controller.setQuantityPending('ram_mb', pending)} onvalue={value => controller.edit({ ram_mb: value * 1024 })} />
			<div class="grid min-w-0 grid-cols-1 items-start gap-4 md:grid-cols-2">
			<Field label={t('composer.gpuType')} for="flavor-composer-gpu" error={profileInvalid ? `${retainedGpu} — ${t('composer.unavailable')}` : undefined}>
				<SearchSelect id="flavor-composer-gpu" value={tuple.gpu_profile_id ?? ''} options={gpuChoices} placeholder={profileInvalid ? `${retainedGpu} — ${t('composer.unavailable')}` : t('composer.noGpu')} ariaLabel={t('composer.gpuType')} disabled={editLocked} onchange={id => controller.selectGpu(id || null)} />
			</Field>
			<ResourceQuantityInput id="flavor-composer-gpu-count" label={t('composer.gpuCount')} unit="GPU" value={tuple.gpu_count} values={options?.gpu_counts} min={tuple.gpu_profile_id ? 1 : 0} max={16} disabled={editLocked || !tuple.gpu_profile_id} invalid={countInvalid} unavailable={t('composer.unavailable')} resetKey={`${quantityResetKey}:${tuple.gpu_profile_id ?? ''}`} bind:pending={() => $controller.quantityPending.gpu_count, pending => controller.setQuantityPending('gpu_count', pending)} onvalue={gpu_count => controller.edit({ gpu_count })} />
			</div>
		</div>
		{#if options && options.status !== 'available'}<Alert tone="warning">{t('composer.unavailable')}</Alert>{/if}
		<SelectFlavor {...picker} catalogVisible={false} refreshVisible={false} refreshing={picker.refreshing || locked} initialLoading={false} previewFlavor={preview} />
		<div class="flex flex-wrap items-center justify-between gap-3">
			<Button variant="subtle" disabled={editLocked} onclick={() => { quantityReset += 1; controller.edit({ vcpus: 2, ram_mb: 1024, gpu_profile_id: null, gpu_count: 0 }); }}>{t('composer.resetResources')}</Button>
		</div>
	{:else if $controller.mode === 'saved'}
		<p class="text-sm text-ink-2">{t('composer.savedHelp')}</p>
		{#if $controller.historyLoading}<LoadingState variant={$controller.history.length ? 'inline' : 'section'} label={t('composer.historyLoading')} />{/if}
		{#if $controller.historyError}
			<Alert tone="danger" title={t('composer.historyFailed')}><p class="break-words">{$controller.historyError}</p>{#snippet actions()}<Button variant="secondary" disabled={locked} onclick={() => { void controller.loadHistory(); }}>{t('flavor.refresh.retry')}</Button>{/snippet}</Alert>
		{:else if !$controller.historyLoading && $controller.history.length === 0}<p class="text-sm text-ink-2">{t('composer.historyEmpty')}</p>{/if}
		<ul class="divide-y divide-line">
			{#each $controller.history as flavor (flavor.id)}
				{@const unavailable = !validFlavorComposition(flavor.composition) || flavorCreateBlock(flavor) !== null}
				<li class="flex min-w-0 flex-wrap items-center justify-between gap-3 py-3">
					<div class="min-w-0"><p class="break-words text-sm font-medium text-ink-0">{consumerFlavorLabel(flavor)}</p>{#if unavailable}<p class="text-xs text-ink-2">{t('composer.unavailable')}</p>{/if}</div>
					<Button variant="secondary" disabled={editLocked || !$controller.canWrite || $controller.historyLoading || Boolean($controller.historyError) || unavailable} onclick={() => { void controller.save(flavor); }}>{t('composer.reuse')}</Button>
				</li>
			{/each}
		</ul>
	{/if}
	{#if $controller.mode !== 'compose'}<SelectFlavor {...picker} catalogVisible={$controller.mode === 'catalog'} refreshVisible={false} refreshing={picker.refreshing || editLocked || !$controller.canWrite} initialLoading={$controller.mode === 'catalog' && picker.initialLoading} />{/if}
</div>
