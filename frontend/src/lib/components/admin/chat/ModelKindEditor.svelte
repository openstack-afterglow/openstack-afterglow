<script lang="ts">
	import { onDestroy, untrack } from 'svelte';
	import { auth, authReady, projectSwitching } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import { invalidateChatModels } from '$lib/stores/chatModels';
	import { t } from '$lib/i18n/ns/admin-chat';
	import FormModal from '$lib/components/ui/FormModal.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import SelectInput from '$lib/components/ui/SelectInput.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import { MODEL_LABELS, type ModelKind, type MediaPricing } from './modelPricing';

	interface EditableModel {
		id: number;
		model_name: string;
		display_name: string | null;
		model_kind?: ModelKind;
		is_title_model?: boolean;
		is_memory_model?: boolean;
		media_pricing?: MediaPricing | null;
		cache_write_price_per_million?: string | null;
		cache_write_1h_price_per_million?: string | null;
	}
	let { model, mediaSupported, token, projectId, onclose, onsaved }: {
		model: EditableModel;
		mediaSupported: boolean;
		token?: string;
		projectId?: string;
		onclose: () => void;
		onsaved: () => void | Promise<void>;
	} = $props();
	let kind = $state<ModelKind>(untrack(() => model.model_kind ?? 'text'));
	let busy = $state(false);
	let error = $state('');
	let epoch = 0;
	let identity = '';
	let destroyed = false;
	const originalKind = $derived(model.model_kind ?? 'text');
	const protectedText = $derived(model.is_title_model || model.is_memory_model);
	const unavailable = $derived(kind !== 'text' && (!mediaSupported || protectedText));
	const unsubscribe = auth.subscribe((state) => {
		const next = JSON.stringify([state.token, state.projectId, state.userId, state.sessionId, state.identityDomainId, state.domainId, state.isSystemAdmin, state.roles]);
		if (identity && next !== identity) { ++epoch; onclose(); }
		identity = next;
	});
	const stopReadiness = authReady.subscribe((ready) => { if (!ready) { ++epoch; onclose(); } });
	const stopSwitching = projectSwitching.subscribe((switching) => { if (switching) { ++epoch; onclose(); } });
	onDestroy(() => { destroyed = true; ++epoch; unsubscribe(); stopReadiness(); stopSwitching(); });

	async function save() {
		if (busy || !token || kind === originalKind || unavailable || !$authReady || $projectSwitching) return;
		const generation = epoch, target = model, requestToken = token, requestProject = projectId;
		const current = () => !destroyed && epoch === generation && model === target && token === requestToken && projectId === requestProject;
		// Per-kind unit prices cannot be reused as a different operation's prices.
		// Shared token rates remain explicit; reactivation requires a separate review.
		const media = target.media_pricing?.token_rates ? { token_rates: target.media_pricing.token_rates } : null;
		const body = {
			model_kind: kind,
			is_active: false,
			media_pricing: media,
			...(kind !== 'text' ? { cache_write_price_per_million: null, cache_write_1h_price_per_million: null } : {})
		};
		busy = true; error = '';
		try {
			await api.patch(`/api/v1/chat/admin/models/${target.id}`, body, requestToken, requestProject);
			invalidateChatModels();
			if (!current()) return;
			await onsaved();
			if (current()) onclose();
		} catch (caught) {
			if (current()) error = caught instanceof ApiError ? t('pricing.saveStatusError', { status: caught.status }) : t('pricing.saveError');
		} finally { if (current()) busy = false; }
	}
</script>

<FormModal open title={t('pricing.editKind')} onClose={() => { if (!busy) onclose(); }} submitting={busy}>
	<p class="mb-4 break-all text-sm text-ink-1">{model.display_name || model.model_name}</p>
	<Field label={t('configuration.modelType')} for="model-kind-edit">
		<SelectInput id="model-kind-edit" bind:value={kind} disabled={busy}>
			{#each Object.entries(MODEL_LABELS) as [value, label]}
				<option {value} disabled={value !== 'text' && (!mediaSupported || protectedText)}>{label}</option>
			{/each}
		</SelectInput>
	</Field>
	<Alert tone="warning" class="mt-4">{t('pricing.kindChangeHelp')}</Alert>
	{#if protectedText}<p class="mt-3 text-sm text-ink-2">{t('pricing.kindProtected')}</p>{/if}
	{#if !mediaSupported}<p class="mt-3 text-sm text-ink-2">{t('pricing.mediaProviderRequired')}</p>{/if}
	{#if error}<Alert tone="danger" class="mt-3">{error}</Alert>{/if}
	{#snippet actions()}
		<Button variant="secondary" disabled={busy} onclick={onclose}>{t('configuration.cancel')}</Button>
		<Button disabled={busy || kind === originalKind || unavailable} ariaBusy={busy} onclick={save}>{busy ? t('configuration.saving') : t('pricing.saveKind')}</Button>
	{/snippet}
</FormModal>
