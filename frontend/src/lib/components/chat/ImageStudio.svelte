<script lang="ts">
	import { onDestroy, untrack } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { imageStudioApi, imageModelReadiness, type ImageModel, type ImageRun, type ImageApiScope, type ImageCapabilities } from '$lib/api/imageStudio';
	import { isChatImageMime } from '$lib/api/chatAttachments';
	import { ApiError } from '$lib/api/client';
	import { Alert, Button, Card, Field, PageShell, SelectInput, TextareaInput } from '$lib/components/ui';
	import { t } from '$lib/i18n/ns/chat-studio';

	const scope = $derived($auth.token && $auth.projectId ? { token: $auth.token, projectId: $auth.projectId } : null);
	const storageKey = $derived(`afterglow:image-studio:${$auth.userId ?? ''}:${$auth.projectId ?? ''}`);
	let models = $state<ImageModel[]>([]);
	let modelId = $state('');
	let modelsLoading = $state(false);
	let modelsError = $state('');
	let capabilities = $state<ImageCapabilities | null>(null);
	let capabilitiesLoading = $state(false);
	let capabilitiesError = $state('');
	let capabilityRequest = 0;
	let prompt = $state('');
	let size = $state('1024x1024');
	let quality = $state('high');
	let count = $state('1');
	let editMode = $state(false);
	let editAssetId = $state('');
	let editFileName = $state('');
	let uploading = $state(false);
	let submitting = $state(false);
	let error = $state('');
	let runIds = $state<string[]>([]);
	let selectedRunId = $state<string | null>(null);
	let currentRun = $state<ImageRun | null>(null);
	let previewUrls = $state<Record<string, string>>({});
	let loadingRun = $state(false);
	let operation = 0;
	let timer: ReturnType<typeof setTimeout> | null = null;
	let modelRequest = 0;
	let uploadAbort: AbortController | null = null;
	let submitAbort: AbortController | null = null;
	let downloadAbort: AbortController | null = null;
	let activeScopeKey = '';
	let activeCapabilityKey = '';
	let pendingIntent: { fingerprint: string; key: string } | null = null;
	const chosenModel = $derived(models.find((model) => String(model.id) === modelId));
	const readiness = $derived(imageModelReadiness(chosenModel));
	const busy = $derived(submitting || uploading || Boolean(currentRun && !currentRun.terminal));
	const variants = $derived((capabilities?.available_image_variants ?? []).map((variant) => {
		const [variantSize, variantQuality] = variant.split(':');
		return { size: variantSize, quality: variantQuality };
	}).filter(({ size: variantSize, quality: variantQuality }) => Boolean(variantSize && variantQuality)));
	const sizes = $derived([...new Set(variants.map((variant) => variant.size))]);
	const qualities = $derived([...new Set(variants.filter((variant) => variant.size === size).map((variant) => variant.quality))]);
	const maxCount = $derived(Math.min(capabilities?.max_image_count ?? 1, 10));
	const variantReady = $derived(Boolean(variants.some((variant) => variant.size === size && variant.quality === quality) && Number(count) >= 1 && Number(count) <= maxCount));
	const requestFingerprint = $derived(JSON.stringify({ project: storageKey, modelId, prompt: prompt.trim(), size, quality, count, editMode, editAssetId }));
	$effect(() => {
		const fingerprint = requestFingerprint;
		untrack(() => {
			if (pendingIntent && pendingIntent.fingerprint !== fingerprint) pendingIntent = null;
		});
	});
	function selectModel(event: Event) {
		modelId = (event.currentTarget as HTMLSelectElement).value;
		count = '1';
	}
	async function loadCapabilities(model: ImageModel, requestScope: ImageApiScope, generation: number) {
		capabilitiesLoading = true;
		capabilitiesError = '';
		try {
			const loaded = await imageStudioApi.capabilities(model.id, requestScope);
			if (generation !== capabilityRequest) return;
			capabilities = loaded;
			const first = loaded.available_image_variants?.[0]?.split(':');
			size = first?.[0] ?? '';
			quality = first?.[1] ?? '';
			count = '1';
		} catch (cause) {
			if (generation === capabilityRequest) capabilitiesError = message(cause);
		} finally {
			if (generation === capabilityRequest) capabilitiesLoading = false;
		}
	}
	$effect(() => {
		const selected = chosenModel;
		const key = storageKey;
		const authenticated = Boolean(scope);
		const capabilityKey = selected && authenticated ? `${key}:${selected.id}` : '';
		if (capabilityKey === activeCapabilityKey) return;
		activeCapabilityKey = capabilityKey;
		const currentScope = authenticated ? untrack(() => scope) : null;
		untrack(() => {
			const generation = ++capabilityRequest;
			capabilities = null;
			capabilitiesError = '';
			capabilitiesLoading = false;
			if (selected && currentScope && !imageModelReadiness(selected)) void loadCapabilities(selected, currentScope, generation);
		});
	});
	$effect(() => {
		if (qualities.length && !qualities.includes(quality)) quality = qualities[0];
	});

	function clearTimer() {
		if (timer) clearTimeout(timer);
		timer = null;
	}
	function clearPreviews() {
		downloadAbort?.abort();
		downloadAbort = null;
		for (const url of Object.values(previewUrls)) URL.revokeObjectURL(url);
		previewUrls = {};
	}
	function saveHistory(key: string, ids: string[]) {
		try { sessionStorage.setItem(key, JSON.stringify(ids.slice(0, 20))); } catch { /* Storage is optional. */ }
	}
	function readHistory(key: string): string[] {
		try {
			const ids: unknown = JSON.parse(sessionStorage.getItem(key) ?? '[]');
			return Array.isArray(ids) ? ids.filter((id): id is string => typeof id === 'string').slice(0, 20) : [];
		} catch { return []; }
	}
	function message(cause: unknown): string {
		if (cause instanceof ApiError) {
			if (cause.status === 401 || cause.status === 403) return t('imageStudio.projectDenied');
			if (cause.status === 402) return t('imageStudio.quotaInsufficient');
			if (cause.status === 429) return t('imageStudio.rateLimited');
			if (cause.status === 400 || cause.status === 422 || cause.status === 409) return cause.message.slice(0, 250);
			return t('imageStudio.requestFailed', { status: cause.status });
		}
		return t('imageStudio.connectionFailed');
	}
	function displayStatus(status: string): string {
		return ({ queued: t('imageStudio.status.queued'), running: t('imageStudio.status.running'), waiting_resource: t('imageStudio.status.waitingResource'), finalizing: t('imageStudio.status.finalizing'), completed: t('imageStudio.status.completed'), failed: t('imageStudio.status.failed'), canceled: t('imageStudio.status.canceled') } as Record<string, string>)[status] ?? status;
	}
	function displayQuality(value: string): string {
		switch (value) {
			case 'auto': return t('imageStudio.quality.auto');
			case 'high': return t('imageStudio.quality.high');
			case 'medium': return t('imageStudio.quality.medium');
			case 'low': return t('imageStudio.quality.low');
			case 'standard': return t('imageStudio.quality.standard');
			case 'hd': return t('imageStudio.quality.hd');
			default: return value;
		}
	}

	async function loadModels(requestScope: ImageApiScope, generation: number) {
		modelsLoading = true;
		modelsError = '';
		try {
			const loaded = await imageStudioApi.models(requestScope);
			if (generation !== modelRequest) return;
			models = loaded;
			if (!loaded.some((model) => String(model.id) === modelId)) modelId = loaded[0] ? String(loaded[0].id) : '';
		} catch (cause) {
			if (generation === modelRequest) modelsError = message(cause);
		} finally {
			if (generation === modelRequest) modelsLoading = false;
		}
	}
	async function loadRun(id: string, requestScope: ImageApiScope, generation: number) {
		loadingRun = true;
		try {
			const run = await imageStudioApi.run(id, requestScope);
			if (generation !== operation || selectedRunId !== id) return;
			currentRun = run;
			loadingRun = false;
			if (run.terminal) {
				if (run.status === 'completed') void loadPreviews(run, requestScope, generation);
			} else {
				clearTimer();
				timer = setTimeout(() => { void loadRun(id, requestScope, generation); }, 2000);
			}
		} catch (cause) {
			if (generation === operation) {
				loadingRun = false;
				error = t('imageStudio.runLoadFailed', { message: message(cause) });
			}
		}
	}
	async function loadPreviews(run: ImageRun, requestScope: ImageApiScope, generation: number) {
		const controller = new AbortController();
		downloadAbort = controller;
		for (const asset of run.output_assets ?? []) {
			if (generation !== operation || controller.signal.aborted) return;
			try {
				const blob = await imageStudioApi.download(asset.asset_id, requestScope, controller.signal);
				if (generation !== operation || controller.signal.aborted) return;
				if (asset.mime_type.startsWith('image/')) previewUrls = { ...previewUrls, [asset.asset_id]: URL.createObjectURL(blob) };
			} catch (cause) {
				if (generation === operation && !controller.signal.aborted) error = t('imageStudio.previewLoadFailed', { message: message(cause) });
			}
		}
	}
	function selectRun(id: string, requestScope: ImageApiScope) {
		operation += 1;
		clearTimer();
		clearPreviews();
		error = '';
		currentRun = null;
		selectedRunId = id;
		void loadRun(id, requestScope, operation);
	}

	$effect(() => {
		const authenticated = Boolean(scope);
		const key = storageKey;
		const nextScopeKey = authenticated ? key : '';
		if (nextScopeKey === activeScopeKey) return;
		activeScopeKey = nextScopeKey;
		const currentScope = authenticated ? untrack(() => scope) : null;
		untrack(() => {
			operation += 1;
			modelRequest += 1;
			capabilityRequest += 1;
			capabilities = null;
			capabilitiesLoading = false;
			capabilitiesError = '';
			clearTimer();
			clearPreviews();
			uploadAbort?.abort();
			submitAbort?.abort();
			pendingIntent = null;
			uploading = false;
			submitting = false;
			loadingRun = false;
			models = [];
			modelId = '';
			runIds = [];
			selectedRunId = null;
			currentRun = null;
			editAssetId = '';
			editFileName = '';
			error = '';
			if (!currentScope) return;
			const generation = modelRequest;
			void loadModels(currentScope, generation);
			runIds = readHistory(key);
			if (runIds[0]) selectRun(runIds[0], currentScope);
		});
	});
	onDestroy(() => {
		modelRequest += 1;
		capabilityRequest += 1;
		operation += 1;
		clearTimer();
		clearPreviews();
		uploadAbort?.abort();
		submitAbort?.abort();
	});

	async function selectFile(event: Event) {
		const file = (event.currentTarget as HTMLInputElement).files?.[0];
		if (!file || !scope) return;
		if (!isChatImageMime(file.type)) { error = t('imageStudio.invalidFile'); return; }
		uploadAbort?.abort();
		const controller = new AbortController();
		uploadAbort = controller;
		const generation = operation;
		const requestScope = scope;
		uploading = true;
		editAssetId = '';
		error = '';
		try {
			const asset = await imageStudioApi.upload(file, requestScope, controller.signal);
			if (generation !== operation || controller.signal.aborted) return;
			editAssetId = asset.id;
			editFileName = asset.name;
		} catch (cause) {
			if (generation === operation && !controller.signal.aborted) error = t('imageStudio.uploadFailed', { message: message(cause) });
		} finally {
			if (generation === operation) uploading = false;
		}
	}
	async function submit() {
		if (!scope || readiness || modelsLoading || capabilitiesLoading || !variantReady || busy || !prompt.trim() || (editMode && !editAssetId)) return;
		const requestScope = scope;
		const generation = ++operation;
		const controller = new AbortController();
		submitAbort = controller;
		clearTimer();
		clearPreviews();
		currentRun = null;
		selectedRunId = null;
		error = '';
		submitting = true;
		try {
			const request = { model_id: modelId, prompt: prompt.trim(), size, quality, n: Number(count) };
			const fingerprint = requestFingerprint;
			const idempotencyKey = pendingIntent?.fingerprint === fingerprint ? pendingIntent.key : crypto.randomUUID();
			pendingIntent = { fingerprint, key: idempotencyKey };
			const descriptor = await imageStudioApi.submit(editMode ? 'edits' : 'generations', editMode ? { ...request, input_asset_id: editAssetId } : request, requestScope, idempotencyKey, controller.signal);
			if (generation !== operation) return;
			pendingIntent = null;
			runIds = [descriptor.run_id, ...runIds.filter((id) => id !== descriptor.run_id)].slice(0, 20);
			saveHistory(storageKey, runIds);
			selectedRunId = descriptor.run_id;
			void loadRun(descriptor.run_id, requestScope, generation);
		} catch (cause) {
			if (generation === operation) error = message(cause);
		} finally {
			if (submitAbort === controller) submitAbort = null;
			if (generation === operation) submitting = false;
		}
	}
	async function cancel() {
		if (!scope || !selectedRunId || currentRun?.terminal) return;
		try {
			await imageStudioApi.cancel(selectedRunId, scope);
			if (selectedRunId && scope) void loadRun(selectedRunId, scope, operation);
		} catch (cause) { error = t('imageStudio.cancelFailed', { message: message(cause) }); }
	}
	async function download(id: string, name: string) {
		if (!scope) return;
		try {
			const blob = await imageStudioApi.download(id, scope);
			const url = URL.createObjectURL(blob);
			const anchor = document.createElement('a');
			anchor.href = url;
			anchor.download = name || `image-${id}.png`;
			anchor.click();
			setTimeout(() => URL.revokeObjectURL(url), 1000);
		} catch (cause) { error = t('imageStudio.downloadFailed', { message: message(cause) }); }
	}
</script>

<PageShell max="7xl">
	<div class="studio">
		<header class="studio-header">
			<div><p class="eyebrow">{t('imageStudio.breadcrumb')}</p><h1>{t('imageStudio.title')}</h1><p class="muted">{t('imageStudio.description')}</p></div>
			<Button href="/dashboard/chat" variant="secondary">{t('imageStudio.textChat')}</Button>
		</header>
		{#if modelsError}<Alert tone="danger" title={t('imageStudio.modelsLoadFailed')}>{modelsError} <Button variant="subtle" onclick={() => scope && loadModels(scope, ++modelRequest)}>{t('imageStudio.retry')}</Button></Alert>{/if}
		{#if error}<Alert tone="danger">{error} {#if selectedRunId}<Button variant="subtle" onclick={() => scope && selectedRunId && selectRun(selectedRunId, scope)}>{t('imageStudio.recheckStatus')}</Button>{/if}</Alert>{/if}
		<div class="studio-grid">
			<Card>
				<form class="form" onsubmit={(event) => { event.preventDefault(); void submit(); }}>
					<div class="mode-row" role="group" aria-label={t('imageStudio.operationType')}>
						<Button variant={!editMode ? 'accent' : 'secondary'} ariaPressed={!editMode} onclick={() => (editMode = false)}>{t('imageStudio.newImage')}</Button>
						<Button variant={editMode ? 'accent' : 'secondary'} ariaPressed={editMode} onclick={() => (editMode = true)}>{t('imageStudio.editImage')}</Button>
					</div>
					<Field label={t('imageStudio.model')} for="studio-model">
						<SelectInput id="studio-model" value={modelId} onchange={selectModel} disabled={modelsLoading || busy}><option value="">{t('imageStudio.selectModel')}</option>{#each models as model (model.id)}<option value={String(model.id)}>{model.display_name}</option>{/each}</SelectInput>
					</Field>
					{#if modelsLoading || capabilitiesLoading}<p role="status" class="muted">{t('imageStudio.checkingOptions')}</p>{:else if readiness}<Alert tone="warning" title={t('imageStudio.notReady')}>{readiness}</Alert>{:else if capabilitiesError}<Alert tone="danger" title={t('imageStudio.optionsLoadFailed')}>{capabilitiesError} <Button variant="subtle" onclick={() => chosenModel && scope && loadCapabilities(chosenModel, scope, ++capabilityRequest)}>{t('imageStudio.retry')}</Button></Alert>{:else if !variantReady}<Alert tone="warning">{t('imageStudio.variantUnavailable')}</Alert>{:else}<Alert tone="success">{t('imageStudio.ready')}</Alert>{/if}
					<Field label={t('imageStudio.prompt')} for="studio-prompt" required><TextareaInput id="studio-prompt" bind:value={prompt} rows={5} placeholder={t('imageStudio.promptPlaceholder')} disabled={busy} /></Field>
					<div class="options">
						<Field label={t('imageStudio.size')} for="studio-size"><SelectInput id="studio-size" bind:value={size} disabled={busy || capabilitiesLoading}>{#each sizes as option (option)}<option value={option}>{option === 'auto' ? t('imageStudio.autoSize') : option.replace('x', ' × ')}</option>{/each}</SelectInput></Field>
						<Field label={t('imageStudio.qualityLabel')} for="studio-quality"><SelectInput id="studio-quality" bind:value={quality} disabled={busy || capabilitiesLoading}>{#each qualities as option (option)}<option value={option}>{displayQuality(option)}</option>{/each}</SelectInput></Field>
						<Field label={t('imageStudio.imageCount')} for="studio-count"><SelectInput id="studio-count" bind:value={count} disabled={busy || capabilitiesLoading}>{#each Array.from({ length: maxCount }, (_, index) => index + 1) as option (option)}<option value={String(option)}>{option}</option>{/each}</SelectInput></Field>
					</div>
					{#if editMode}<Field label={t('imageStudio.inputImage')} for="studio-file" help={t('imageStudio.inputImageHelp')}><input id="studio-file" type="file" accept="image/png,image/jpeg,image/webp" onchange={selectFile} disabled={busy} class="file-input" /></Field>{#if uploading}<p role="status">{t('imageStudio.uploading')}</p>{:else if editAssetId}<p role="status" class="muted">{t('imageStudio.uploadComplete', { name: editFileName })}</p>{/if}{/if}
					<Button type="submit" disabled={!scope || Boolean(readiness) || modelsLoading || capabilitiesLoading || !variantReady || busy || !prompt.trim() || (editMode && !editAssetId)}>{submitting ? t('imageStudio.submitting') : editMode ? t('imageStudio.startEdit') : t('imageStudio.startGeneration')}</Button>
				</form>
			</Card>
			<section class="results" aria-label={t('imageStudio.results')}>
				<Card>
					<h2>{t('imageStudio.browserJobs')}</h2>
					{#if runIds.length === 0}<p class="muted">{t('imageStudio.noJobs')}</p>{:else}<div class="history">{#each runIds as id, index (id)}<Button variant={selectedRunId === id ? 'accent' : 'secondary'} ariaPressed={selectedRunId === id} onclick={() => scope && selectRun(id, scope)}>{t('imageStudio.jobLabel', { number: runIds.length - index, id: id.slice(0, 8) })}</Button>{/each}</div>{/if}
				</Card>
				{#if selectedRunId}<Card><div class="result-head"><h2>{t('imageStudio.jobResults')}</h2>{#if currentRun}<span role="status">{displayStatus(currentRun.status)}</span>{/if}</div>
					{#if loadingRun && !currentRun}<p role="status">{t('imageStudio.checkingJob')}</p>{/if}
					{#if currentRun && !currentRun.terminal}<p role="status">{t('imageStudio.processing')}</p><Button variant="danger-outline" onclick={cancel}>{t('imageStudio.cancelJob')}</Button>{/if}
					{#if currentRun?.status === 'failed'}<Alert tone="danger" title={t('imageStudio.jobFailedTitle')}>{t('imageStudio.jobFailed')}</Alert>{/if}
					{#if currentRun?.status === 'canceled'}<Alert tone="neutral">{t('imageStudio.jobCanceled')}</Alert>{/if}
					{#if currentRun?.status === 'completed'}{#if currentRun.output_assets?.length}<div class="gallery">{#each currentRun.output_assets as asset (asset.asset_id)}<figure><div class="image-frame">{#if previewUrls[asset.asset_id]}<img src={previewUrls[asset.asset_id]} alt={t('imageStudio.generatedImage')} />{:else}<span>{t('imageStudio.loadingImage')}</span>{/if}</div><figcaption><span>{t('imageStudio.imageMime', { mime: asset.mime_type })}</span><Button variant="secondary" onclick={() => download(asset.asset_id, `image-${asset.asset_id}.${asset.mime_type.split('/')[1] ?? 'png'}`)}>{t('imageStudio.download')}</Button></figcaption></figure>{/each}</div>{:else}<Alert tone="warning">{t('imageStudio.noOutputImages')}</Alert>{/if}{/if}
				</Card>{/if}
			</section>
		</div>
	</div>
</PageShell>

<style>
	.studio { display: grid; gap: 1.25rem; }
	.studio-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 1rem; flex-wrap: wrap; }
	.studio-header h1 { font-size: 1.25rem; font-weight: 600; line-height: 1.75rem; }
	.eyebrow { font-size: 0.75rem; color: var(--color-ink-2); }
	.muted { color: var(--color-ink-2); font-size: 0.8125rem; line-height: 1.5; }
	.studio-grid { display: grid; gap: 1rem; align-items: start; }
	.form, .results { display: grid; gap: 1rem; min-width: 0; }
	.mode-row, .history, .result-head { display: flex; flex-wrap: wrap; align-items: center; gap: 0.5rem; }
	.options { display: grid; gap: 0.75rem; }
	.file-input { width: 100%; border: 1px solid var(--color-line-2); border-radius: var(--radius-md); padding: 0.5rem; background: var(--color-surface-sunken); color: var(--color-ink-1); font-size: 0.8125rem; }
	.file-input:focus-visible { outline: none; box-shadow: var(--focus-ring); }
	.results h2 { font-size: 0.875rem; font-weight: 600; margin-bottom: 0.75rem; }
	.result-head { justify-content: space-between; }
	.result-head h2 { margin-bottom: 0; }
	.gallery { display: grid; gap: 0.75rem; margin-top: 0.75rem; }
	.gallery figure { min-width: 0; border: 1px solid var(--color-line); border-radius: var(--radius-lg); overflow: hidden; background: var(--color-surface-sunken); }
	.image-frame { min-height: 10rem; display: grid; place-items: center; color: var(--color-ink-2); }
	.image-frame img { display: block; width: 100%; height: auto; max-height: 36rem; object-fit: contain; }
	figcaption { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 0.5rem; padding: 0.75rem; font-size: 0.8125rem; }
	@media (min-width: 768px) { .options { grid-template-columns: repeat(2, minmax(0, 1fr)); } .gallery { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
	@media (min-width: 1024px) { .studio-grid { grid-template-columns: minmax(19rem, 0.9fr) minmax(0, 1.1fr); } }
</style>
