<script lang="ts">
	import { onDestroy, untrack } from 'svelte';
	import { auth, authReady, projectSwitching } from '$lib/stores/auth';
	import { imageStudioApi, imageModelReadiness, type ImageModel, type ImageRun, type ImageApiScope, type ImageCapabilities } from '$lib/api/imageStudio';
	import { isChatImageMime } from '$lib/api/chatAttachments';
	import { ApiError } from '$lib/api/client';
	import { ActivityIndicator, Alert, Button, Field, PageShell, SelectInput, TextareaInput } from '$lib/components/ui';
	import { IMAGE_STUDIO_STYLES, composeImagePrompt, imageRequestAspectRatio, type ImageStudioStyleId } from './imageStudioStyles';
	import { t } from '$lib/i18n/ns/chat-studio';
	import { serviceCapabilities, serviceDenials } from '$lib/stores/servicePermissions';
	import LumenPermissionNotice from './LumenPermissionNotice.svelte';

	// The actor survives token/permission refresh; each action checks its own leaf.
	const scope = $derived($authReady && !$projectSwitching && $auth.token && $auth.projectId && $auth.userId ? { token: $auth.token, projectId: $auth.projectId } : null);
	const imagesAllowed = $derived(Boolean(scope) && $serviceCapabilities('lumen-images_user'));
	const assetsAllowed = $derived(Boolean(scope) && $serviceCapabilities('lumen-assets_editor'));
	const storageKey = $derived(`afterglow:image-studio:${$auth.userId ?? ''}:${$auth.projectId ?? ''}`);
	let models = $state<ImageModel[]>([]);
	let modelId = $state('');
	let modelsLoading = $state(false);
	let modelsLoaded = $state(false);
	let modelsError = $state('');
	let capabilities = $state<ImageCapabilities | null>(null);
	let capabilitiesLoading = $state(false);
	let capabilitiesError = $state('');
	let capabilityRequest = 0;
	let prompt = $state('');
	let styleId = $state<ImageStudioStyleId | null>(null);
	let size = $state('1024x1024');
	let quality = $state('high');
	let count = $state('1');
	let inputAssetId = $state('');
	let inputFileName = $state('');
	let inputPreviewUrl = $state('');
	let fileInput = $state<HTMLInputElement>();
	let uploading = $state(false);
	let inputGeneration = 0;
	let submitting = $state(false);
	let error = $state('');
	let runIds = $state<string[]>([]);
	let selectedRunId = $state<string | null>(null);
	let currentRun = $state<ImageRun | null>(null);
	interface RunContext { size: string | null; startedAt: number; submitted: boolean }
	const runContexts = new Map<string, RunContext>();
	const revealedOutputs = new Set<string>();
	let runContext = $state<RunContext | null>(null);
	let liveRunId = $state<string | null>(null);
	let elapsedSeconds = $state(0);
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
	const runActive = $derived(Boolean(currentRun && !currentRun.terminal));
	const busy = $derived(submitting || uploading || runActive);
	const selectedStyle = $derived(IMAGE_STUDIO_STYLES.find((style) => style.id === styleId));
	const composedPrompt = $derived(composeImagePrompt(prompt, styleId));
	const hasInput = $derived(Boolean(inputPreviewUrl));
	const variants = $derived((capabilities?.available_image_variants ?? []).map((variant) => {
		const [variantSize, variantQuality] = variant.split(':');
		return { size: variantSize, quality: variantQuality };
	}).filter(({ size: variantSize, quality: variantQuality }) => Boolean(variantSize && variantQuality)));
	const sizes = $derived([...new Set(variants.map((variant) => variant.size))]);
	const qualities = $derived([...new Set(variants.filter((variant) => variant.size === size).map((variant) => variant.quality))]);
	const maxCount = $derived(Math.min(capabilities?.max_image_count ?? 1, 10));
	const variantReady = $derived(Boolean(variants.some((variant) => variant.size === size && variant.quality === quality) && Number(count) >= 1 && Number(count) <= maxCount));
	const requestFingerprint = $derived(JSON.stringify({ project: storageKey, modelId, prompt: composedPrompt, style: styleId, size, quality, count, inputAssetId }));
	const canSubmit = $derived(imagesAllowed && !readiness && !modelsLoading && !capabilitiesLoading && variantReady && !busy && Boolean(composedPrompt) && (!hasInput || Boolean(inputAssetId)));
	const developingRatio = $derived(imageRequestAspectRatio(runContext?.size) ?? '1 / 1');
	$effect(() => {
		const active = runActive;
		const startedAt = runContext?.startedAt;
		if (!active || startedAt === undefined) return;
		// This measures the local wait, not unreported server execution time.
		const updateElapsed = () => { elapsedSeconds = Math.max(0, Math.floor((Date.now() - startedAt) / 1000)); };
		updateElapsed();
		const clock = setInterval(updateElapsed, 1000);
		return () => clearInterval(clock);
	});
	$effect(() => {
		const fingerprint = requestFingerprint;
		untrack(() => {
			if (pendingIntent && pendingIntent.fingerprint !== fingerprint) pendingIntent = null;
		});
	});
	function canPublish(requestScope: ImageApiScope): boolean {
		return imagesAllowed && activeScopeKey === storageKey && requestScope.projectId === scope?.projectId;
	}
	function selectModel(event: Event) {
		if (!imagesAllowed) return;
		modelId = (event.currentTarget as HTMLSelectElement).value;
		count = '1';
	}
	async function loadCapabilities(model: ImageModel, requestScope: ImageApiScope, generation: number) {
		if (!canPublish(requestScope)) return;
		capabilitiesLoading = true;
		capabilitiesError = '';
		try {
			const loaded = await imageStudioApi.capabilities(model.id, requestScope);
			if (generation !== capabilityRequest || !canPublish(requestScope)) return;
			capabilities = loaded;
			const first = loaded.available_image_variants?.[0]?.split(':');
			size = first?.[0] ?? '';
			quality = first?.[1] ?? '';
			count = '1';
		} catch (cause) {
			if (generation === capabilityRequest && canPublish(requestScope)) capabilitiesError = message(cause);
		} finally {
			if (generation === capabilityRequest) capabilitiesLoading = false;
		}
	}
	$effect(() => {
		const selected = chosenModel;
		const key = storageKey;
		const authenticated = Boolean(scope);
		const allowed = imagesAllowed;
		const capabilityKey = selected && authenticated ? `${key}:${selected.id}` : '';
		if (!allowed) return;
		if (capabilityKey === activeCapabilityKey && untrack(() => Boolean(capabilities || capabilitiesLoading))) return;
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
	function clearInput() {
		inputGeneration += 1;
		uploadAbort?.abort();
		uploadAbort = null;
		uploading = false;
		if (inputPreviewUrl) URL.revokeObjectURL(inputPreviewUrl);
		inputPreviewUrl = '';
		inputAssetId = '';
		inputFileName = '';
		if (fileInput) fileInput.value = '';
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
	function revealLiveResult(node: HTMLImageElement, assetId: string) {
		const key = `${currentRun?.run_id}:${assetId}`;
		// Mark on mount so even an overlapping status poll cannot replay a finished image's entrance.
		if (liveRunId === currentRun?.run_id && !revealedOutputs.has(key)) node.classList.add('motion-pop');
		revealedOutputs.add(key);
	}

	async function loadModels(requestScope: ImageApiScope, generation: number) {
		if (!canPublish(requestScope)) return;
		modelsLoading = true;
		modelsError = '';
		try {
			const loaded = await imageStudioApi.models(requestScope);
			if (generation !== modelRequest || !canPublish(requestScope)) return;
			models = loaded;
			modelsLoaded = true;
			if (!loaded.some((model) => String(model.id) === modelId)) modelId = loaded[0] ? String(loaded[0].id) : '';
		} catch (cause) {
			if (generation === modelRequest && canPublish(requestScope)) modelsError = message(cause);
		} finally {
			if (generation === modelRequest) modelsLoading = false;
		}
	}
	async function loadRun(id: string, requestScope: ImageApiScope, generation: number) {
		if (generation !== operation || !canPublish(requestScope) || !scope) return;
		requestScope = scope;
		loadingRun = true;
		try {
			const run = await imageStudioApi.run(id, requestScope);
			if (generation !== operation || selectedRunId !== id || !canPublish(requestScope)) return;
			const firstCompletion = currentRun?.run_id !== run.run_id || currentRun?.status !== 'completed';
			currentRun = run;
			loadingRun = false;
			if (run.terminal) {
				if (run.status === 'completed' && firstCompletion) void loadPreviews(run, requestScope, generation);
			} else {
				clearTimer();
				timer = setTimeout(() => { void loadRun(id, requestScope, generation); }, 2000);
			}
		} catch (cause) {
			if (generation === operation && canPublish(requestScope)) {
				loadingRun = false;
				error = t('imageStudio.runLoadFailed', { message: message(cause) });
			}
		}
	}
	async function loadPreviews(run: ImageRun, requestScope: ImageApiScope, generation: number) {
		if (!canPublish(requestScope)) return;
		const controller = new AbortController();
		downloadAbort = controller;
		for (const asset of run.output_assets ?? []) {
			if (generation !== operation || controller.signal.aborted || !canPublish(requestScope) || !scope) return;
			if (previewUrls[asset.asset_id]) continue;
			try {
				const blob = await imageStudioApi.download(asset.asset_id, scope, controller.signal);
				if (generation !== operation || controller.signal.aborted || !canPublish(requestScope)) return;
				if (asset.mime_type.startsWith('image/')) previewUrls = { ...previewUrls, [asset.asset_id]: URL.createObjectURL(blob) };
			} catch (cause) {
				if (generation === operation && !controller.signal.aborted && canPublish(requestScope)) error = t('imageStudio.previewLoadFailed', { message: message(cause) });
			}
		}
	}
	function selectRun(id: string, requestScope: ImageApiScope) {
		if (!canPublish(requestScope)) return;
		operation += 1;
		clearTimer();
		clearPreviews();
		error = '';
		currentRun = null;
		selectedRunId = id;
		liveRunId = null;
		runContext = runContexts.get(id) ?? { size: null, startedAt: Date.now(), submitted: false };
		void loadRun(id, requestScope, operation);
	}

	function resetStudio(clearAssets = true) {
		operation += 1;
		modelRequest += 1;
		capabilityRequest += 1;
		activeCapabilityKey = '';
		capabilities = null;
		capabilitiesLoading = false;
		capabilitiesError = '';
		clearTimer();
		clearPreviews();
		if (clearAssets) clearInput();
		submitAbort?.abort();
		pendingIntent = null;
		submitting = false;
		loadingRun = false;
		modelsLoading = false;
		models = [];
		modelsLoaded = false;
		modelId = '';
		runIds = [];
		selectedRunId = null;
		currentRun = null;
		runContexts.clear();
		revealedOutputs.clear();
		runContext = null;
		liveRunId = null;
		error = '';
	}
	$effect(() => {
		const nextScopeKey = scope ? storageKey : '';
		if (nextScopeKey === activeScopeKey) return;
		activeScopeKey = nextScopeKey;
		untrack(() => resetStudio());
	});
	$effect(() => {
		const denied = $serviceDenials('lumen-images_user');
		const assetsDenied = $serviceDenials('lumen-assets_editor');
		untrack(() => {
			if (denied) resetStudio(false);
			if (assetsDenied) clearInput();
		});
	});
	$effect(() => {
		const allowed = imagesAllowed;
		const key = storageKey;
		untrack(() => {
			if (!allowed || !scope) return;
			if (!modelsLoaded && !modelsLoading) {
				void loadModels(scope, modelRequest);
				runIds = readHistory(key);
				if (runIds[0]) selectRun(runIds[0], scope);
			} else if (selectedRunId && !currentRun?.terminal) {
				clearTimer();
				void loadRun(selectedRunId, scope, operation);
			} else if (currentRun?.status === 'completed' && currentRun.output_assets?.some((asset) => !previewUrls[asset.asset_id])) {
				void loadPreviews(currentRun, scope, operation);
			}
		});
	});
	onDestroy(() => {
		modelRequest += 1;
		capabilityRequest += 1;
		operation += 1;
		clearTimer();
		clearPreviews();
		clearInput();
		submitAbort?.abort();
	});

	async function selectFile(event: Event) {
		if (!assetsAllowed || activeScopeKey !== storageKey || uploading || submitting) return;
		const file = (event.currentTarget as HTMLInputElement).files?.[0];
		if (!file || !scope) return;
		if (!isChatImageMime(file.type)) {
			if (fileInput) fileInput.value = '';
			error = t('imageStudio.invalidFile');
			return;
		}
		// Replacing an input invalidates only the previous input; run selection and submission never discard it.
		clearInput();
		const generation = inputGeneration;
		const controller = new AbortController();
		uploadAbort = controller;
		const requestScope = scope;
		inputPreviewUrl = URL.createObjectURL(file);
		inputFileName = file.name;
		uploading = true;
		error = '';
		try {
			const asset = await imageStudioApi.upload(file, requestScope, controller.signal);
			if (generation !== inputGeneration || !assetsAllowed || activeScopeKey !== storageKey || requestScope.projectId !== scope?.projectId) return;
			inputAssetId = asset.id;
			inputFileName = asset.name;
		} catch (cause) {
			if (generation !== inputGeneration || !assetsAllowed || activeScopeKey !== storageKey || requestScope.projectId !== scope?.projectId) return;
			error = t('imageStudio.uploadFailed', { message: message(cause) });
		} finally {
			if (uploadAbort === controller) {
				uploadAbort = null;
				uploading = false;
			}
		}
	}
	async function submit() {
		if (!canSubmit || !scope || !canPublish(scope)) return;
		const requestScope = scope;
		const generation = ++operation;
		const controller = new AbortController();
		submitAbort = controller;
		clearTimer();
		clearPreviews();
		currentRun = null;
		selectedRunId = null;
		liveRunId = null;
		const context: RunContext = { size, startedAt: Date.now(), submitted: true };
		runContext = context;
		error = '';
		submitting = true;
		try {
			const request = { model_id: modelId, prompt: composedPrompt, size, quality, n: Number(count) };
			const fingerprint = requestFingerprint;
			const idempotencyKey = pendingIntent?.fingerprint === fingerprint ? pendingIntent.key : crypto.randomUUID();
			pendingIntent = { fingerprint, key: idempotencyKey };
			const descriptor = await imageStudioApi.submit(inputAssetId ? 'edits' : 'generations', inputAssetId ? { ...request, input_asset_id: inputAssetId } : request, requestScope, idempotencyKey, controller.signal);
			if (generation !== operation || !canPublish(requestScope)) return;
			pendingIntent = null;
			// A completed admission or known history ID is replay, not a new live result.
			liveRunId = !runIds.includes(descriptor.run_id) && !['completed', 'failed', 'canceled'].includes(descriptor.status) ? descriptor.run_id : null;
			runContexts.set(descriptor.run_id, context);
			runIds = [descriptor.run_id, ...runIds.filter((id) => id !== descriptor.run_id)].slice(0, 20);
			saveHistory(storageKey, runIds);
			selectedRunId = descriptor.run_id;
			void loadRun(descriptor.run_id, requestScope, generation);
		} catch (cause) {
			if (generation === operation && canPublish(requestScope)) error = message(cause);
		} finally {
			if (submitAbort === controller) submitAbort = null;
			if (generation === operation) submitting = false;
		}
	}
	async function cancel() {
		if (!scope || !canPublish(scope) || !selectedRunId || currentRun?.terminal) return;
		const requestScope = scope;
		const generation = operation;
		try {
			await imageStudioApi.cancel(selectedRunId, scope);
			if (generation === operation && canPublish(requestScope) && selectedRunId && scope) void loadRun(selectedRunId, scope, generation);
		} catch (cause) { if (generation === operation && canPublish(requestScope)) error = t('imageStudio.cancelFailed', { message: message(cause) }); }
	}
	async function download(id: string, name: string) {
		if (!scope || !canPublish(scope)) return;
		const requestScope = scope;
		const generation = operation;
		try {
			const blob = await imageStudioApi.download(id, scope);
			if (generation !== operation || !canPublish(requestScope)) return;
			const url = URL.createObjectURL(blob);
			const anchor = document.createElement('a');
			anchor.href = url;
			anchor.download = name || `image-${id}.png`;
			anchor.click();
			setTimeout(() => URL.revokeObjectURL(url), 1000);
		} catch (cause) { if (generation === operation && canPublish(requestScope)) error = t('imageStudio.downloadFailed', { message: message(cause) }); }
	}
</script>

<PageShell max="7xl">
	<LumenPermissionNotice leaves={['lumen-images_user', 'lumen-assets_editor']} />
	<div class="studio">
		<header class="studio-header">
			<svg class="studio-mark" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="16" rx="2.5" /><circle cx="15.5" cy="9" r="1.75" /><path d="m3.5 17 5-5.5 4 4 2.5-2.5 5.5 5.5" /></svg>
			<h1>{t('imageStudio.title')}</h1>
			<p class="muted">{t('imageStudio.description')}</p>
			<Button href="/dashboard/chat" variant="ghost" size="sm">{t('imageStudio.textChat')}</Button>
		</header>
		{#if modelsError}<Alert tone="danger" title={t('imageStudio.modelsLoadFailed')}>{modelsError} <Button variant="subtle" disabled={!imagesAllowed} onclick={() => imagesAllowed && scope && loadModels(scope, ++modelRequest)}>{t('imageStudio.retry')}</Button></Alert>{/if}
		{#if error}<Alert tone="danger">{error} {#if selectedRunId}<Button variant="subtle" disabled={!imagesAllowed} onclick={() => scope && selectedRunId && selectRun(selectedRunId, scope)}>{t('imageStudio.recheckStatus')}</Button>{/if}</Alert>{/if}

		<form class="composer" aria-label={t('imageStudio.request')} onsubmit={(event) => { event.preventDefault(); void submit(); }}>
			<TextareaInput id="studio-prompt" class="composer-prompt" bind:value={prompt} rows={4} ariaLabel={t('imageStudio.prompt')} ariaDescribedBy={selectedStyle ? 'studio-input-note studio-style-note' : 'studio-input-note'} placeholder={hasInput ? t('imageStudio.referencePlaceholder') : t('imageStudio.promptPlaceholder')} disabled={!imagesAllowed || busy} />
			<p id="studio-input-note" class="muted attachment-hint">{t('imageStudio.attachmentHelp')}</p>
			{#if selectedStyle}
				<div class="style-note">
					<p id="studio-style-note"><span class="style-note-label">{t('imageStudio.styleLabel', { style: t(selectedStyle.labelKey) })}</span> {t('imageStudio.styleNote', { suffix: `스타일: ${selectedStyle.instruction}` })}</p>
					<Button variant="ghost" size="sm" onclick={() => { if (imagesAllowed) styleId = null; }} disabled={!imagesAllowed || busy}>{t('imageStudio.clearStyle')}</Button>
				</div>
			{/if}
			{#if assetsAllowed && inputPreviewUrl}
				<div class="attachment">
					<img src={inputPreviewUrl} alt={t('imageStudio.inputPreview')} />
					<div class="attachment-meta">
						<p class="attachment-name">{inputFileName}</p>
						{#if uploading}<ActivityIndicator variant="upload" label={t('imageStudio.uploading')} />{:else if inputAssetId}<p role="status" class="muted">{t('imageStudio.uploadComplete', { name: inputFileName })}</p>{/if}
					</div>
					<Button variant="ghost" size="sm" ariaLabel={t('imageStudio.removeAttachment')} onclick={clearInput} disabled={submitting}>{t('imageStudio.remove')}</Button>
				</div>
			{/if}
			<div class="composer-bar">
				<div class="composer-options">
					<Field label={t('imageStudio.model')} for="studio-model" class="option-model">
						<SelectInput id="studio-model" value={modelId} onchange={selectModel} disabled={!imagesAllowed || modelsLoading || busy || models.length === 0}><option value="">{t('imageStudio.selectModel')}</option>{#each models as model (model.id)}<option value={String(model.id)}>{model.display_name}</option>{/each}</SelectInput>
					</Field>
					<Field label={t('imageStudio.size')} for="studio-size"><SelectInput id="studio-size" bind:value={size} disabled={!imagesAllowed || busy || capabilitiesLoading || sizes.length === 0}>{#each sizes as option (option)}<option value={option}>{option === 'auto' ? t('imageStudio.autoSize') : option.replace('x', ' × ')}</option>{/each}</SelectInput></Field>
					<Field label={t('imageStudio.qualityLabel')} for="studio-quality"><SelectInput id="studio-quality" bind:value={quality} disabled={!imagesAllowed || busy || capabilitiesLoading || qualities.length === 0}>{#each qualities as option (option)}<option value={option}>{displayQuality(option)}</option>{/each}</SelectInput></Field>
					<Field label={t('imageStudio.imageCount')} for="studio-count"><SelectInput id="studio-count" bind:value={count} disabled={!imagesAllowed || busy || capabilitiesLoading || maxCount < 1}>{#each Array.from({ length: maxCount }, (_, index) => index + 1) as option (option)}<option value={String(option)}>{option}</option>{/each}</SelectInput></Field>
				</div>
				<div class="composer-actions">
					<Button variant="secondary" onclick={() => assetsAllowed && fileInput?.click()} disabled={busy || !assetsAllowed}>{inputPreviewUrl ? t('imageStudio.replaceImage') : t('imageStudio.attachImage')}</Button>
					<input bind:this={fileInput} type="file" accept="image/png,image/jpeg,image/webp" class="sr-only" tabindex="-1" aria-label={t('imageStudio.inputImage')} onchange={selectFile} disabled={busy || !assetsAllowed} />
					<Button type="submit" variant="primary" size="lg" class="composer-submit" disabled={!canSubmit}>{submitting ? t('imageStudio.submitting') : t('imageStudio.createImage')}</Button>
				</div>
			</div>
			<div class="composer-status">
				{#if !scope}<p role="status" class="muted">{t('imageStudio.signInHelp')}</p>
				{:else if imagesAllowed}
					{#if modelsLoading || capabilitiesLoading || (!modelsLoaded && !modelsError)}<p role="status" class="muted">{t('imageStudio.checkingOptions')}</p>
					{:else if modelsError}<p class="muted">{t('imageStudio.modelsRequired')}</p>
					{:else if models.length === 0}<Alert tone="warning" title={t('imageStudio.noModelsTitle')}>{t('imageStudio.noModels')}</Alert>
					{:else if readiness}<Alert tone="warning" title={t('imageStudio.notReady')}>{readiness}</Alert>
					{:else if capabilitiesError}<Alert tone="danger" title={t('imageStudio.optionsLoadFailed')}>{capabilitiesError} <Button variant="subtle" disabled={!imagesAllowed} onclick={() => imagesAllowed && chosenModel && scope && loadCapabilities(chosenModel, scope, ++capabilityRequest)}>{t('imageStudio.retry')}</Button></Alert>
					{:else if !variantReady}<Alert tone="warning">{t('imageStudio.variantUnavailable')}</Alert>
					{:else}<p role="status" class="muted">{t('imageStudio.ready')}</p>{/if}
				{/if}
			</div>
		</form>

		<section class="styles" aria-labelledby="studio-styles-title">
			<div class="section-head">
				<h2 id="studio-styles-title">{t('imageStudio.styles')}</h2>
				<p class="muted">{t('imageStudio.stylesHelp')}</p>
			</div>
			<div class="style-grid">
				{#each IMAGE_STUDIO_STYLES as style (style.id)}
					<button type="button" class="style-card" class:style-selected={styleId === style.id} aria-pressed={styleId === style.id} disabled={!imagesAllowed || busy} onclick={() => { if (imagesAllowed) styleId = styleId === style.id ? null : style.id; }}>
						<img src={style.image} alt="" loading="lazy" decoding="async" />
						<span>{t(style.labelKey)}</span>
					</button>
				{/each}
			</div>
		</section>

		{#if imagesAllowed && (selectedRunId || runIds.length)}
			<section class="results" aria-labelledby="studio-results-title">
				<div class="result-head">
					<h2 id="studio-results-title">{t('imageStudio.jobResults')}</h2>
					{#if currentRun}<span role="status" class="run-status">{displayStatus(currentRun.status)}</span>{/if}
				</div>
				{#if selectedRunId}
					{#if loadingRun && !currentRun}<p role="status" class="muted">{t('imageStudio.checkingJob')}</p>{/if}
					{#if currentRun && !currentRun.terminal}
						<div class="developing motion-skeleton" style:aspect-ratio={developingRatio} aria-busy="true" aria-label={t('imageStudio.developing')}>
							<div class="developing-status">
								<ActivityIndicator variant={currentRun.status === 'running' ? 'orbit' : 'dots'} label={displayStatus(currentRun.status)} size="lg" />
								<p class="muted">{runContext?.submitted ? t('imageStudio.elapsedSinceRequest', { seconds: elapsedSeconds }) : t('imageStudio.elapsedSinceView', { seconds: elapsedSeconds })}</p>
								<p class="muted">{runContext?.size === 'auto' ? t('imageStudio.requestedAutoSize') : runContext?.size ? t('imageStudio.requestedSize', { size: runContext.size.replace('x', ' × ') }) : t('imageStudio.requestedSizeUnknown')}</p>
							</div>
						</div>
						<div class="run-progress"><p class="muted">{t('imageStudio.processing')}</p><Button variant="danger-outline" onclick={cancel}>{t('imageStudio.cancelJob')}</Button></div>
					{/if}
					{#if currentRun?.status === 'failed'}<Alert tone="danger" title={t('imageStudio.jobFailedTitle')}>{t('imageStudio.jobFailed')}</Alert>{/if}
					{#if currentRun?.status === 'canceled'}<Alert tone="neutral">{t('imageStudio.jobCanceled')}</Alert>{/if}
					{#if currentRun?.status === 'completed'}
						{#if currentRun.output_assets?.length}
							<div class="gallery">
								{#each currentRun.output_assets as asset (asset.asset_id)}
									<figure>
										<div class="image-frame">
											{#if previewUrls[asset.asset_id]}
												<img src={previewUrls[asset.asset_id]} alt={t('imageStudio.generatedImage')} use:revealLiveResult={asset.asset_id} />
											{:else}<span>{t('imageStudio.loadingImage')}</span>{/if}
										</div>
										<figcaption><span>{t('imageStudio.imageMime', { mime: asset.mime_type })}</span><Button variant="secondary" onclick={() => download(asset.asset_id, `image-${asset.asset_id}.${asset.mime_type.split('/')[1] ?? 'png'}`)}>{t('imageStudio.download')}</Button></figcaption>
									</figure>
								{/each}
							</div>
						{:else}<Alert tone="warning">{t('imageStudio.noOutputImages')}</Alert>{/if}
					{/if}
				{/if}
				{#if runIds.length}
					<div class="history-block">
						<h3>{t('imageStudio.browserJobs')}</h3>
						<div class="history">{#each runIds as id, index (id)}<Button size="sm" variant={selectedRunId === id ? 'accent' : 'secondary'} ariaPressed={selectedRunId === id} onclick={() => scope && selectRun(id, scope)}>{t('imageStudio.jobLabel', { number: runIds.length - index, id: id.slice(0, 8) })}</Button>{/each}</div>
					</div>
				{/if}
			</section>
		{/if}
	</div>
</PageShell>

<style>
	.studio { display: grid; gap: 2rem; width: 100%; max-width: 68rem; margin-inline: auto; padding-block: 1rem 3rem; }
	.studio-header { display: grid; justify-items: center; gap: 0.5rem; text-align: center; padding-top: 1.5rem; }
	.studio-mark { width: 2.5rem; height: 2.5rem; color: var(--color-ink-1); }
	.studio-header h1 { font-size: 1.25rem; font-weight: 600; line-height: 1.75rem; color: var(--color-ink-0); }
	.studio-header .muted { max-width: 36rem; }
	.muted { margin: 0; color: var(--color-ink-2); font-size: 0.8125rem; line-height: 1.5; }

	.composer { display: grid; gap: 1rem; padding: 1rem; border: 1px solid var(--color-line); border-radius: var(--radius-xl); background: var(--color-surface-raised); box-shadow: var(--shadow-popover); min-width: 0; }
	.composer :global(.composer-prompt) { min-height: 7.5rem; font-size: 0.875rem; line-height: 1.6; padding: 0.875rem 1rem; resize: vertical; }
	.style-note, .attachment { display: flex; align-items: center; gap: 0.75rem; padding: 0.625rem 0.75rem; border: 1px solid var(--color-line); border-radius: var(--radius-lg); background: var(--color-surface-base); }
	.style-note p { flex: 1; margin: 0; font-size: 0.8125rem; line-height: 1.5; color: var(--color-ink-1); min-width: 0; }
	.style-note-label { font-weight: 600; color: var(--color-warm-text); margin-right: 0.375rem; }
	.attachment img { width: 4.5rem; height: 4.5rem; flex: none; object-fit: cover; border-radius: var(--radius-md); background: var(--color-surface-sunken); }
	.attachment-meta { display: grid; gap: 0.125rem; flex: 1; min-width: 0; }
	.attachment-name { margin: 0; font-size: 0.8125rem; font-weight: 500; color: var(--color-ink-0); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
	.attachment-hint { padding-inline: 0.25rem; }
	.composer-bar { display: grid; gap: 0.875rem; padding-top: 1rem; border-top: 1px solid var(--color-line); }
	/* Selects keep a readable minimum ("1024 × 1024") and at most three per row; the model name gets its own row until four columns fit. */
	.composer-options { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, max(9rem, calc((100% - 1.5rem) / 3))), 1fr)); gap: 0.75rem; min-width: 0; }
	.composer-options :global(.option-model) { grid-column: 1 / -1; }
	.composer-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 0.5rem; }
	.composer :global(.composer-submit) { width: 100%; }

	.styles, .results { display: grid; gap: 1rem; min-width: 0; }
	.section-head { display: grid; gap: 0.25rem; }
	.styles h2, .results h2 { margin: 0; font-size: 1rem; font-weight: 600; color: var(--color-ink-0); }
	.style-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0.75rem; }
	.style-card { display: grid; gap: 0.5rem; padding: 0; border: 0; background: transparent; color: var(--color-ink-1); font: inherit; font-size: 0.8125rem; font-weight: 500; text-align: left; cursor: pointer; min-width: 0; }
	.style-card img { display: block; width: 100%; aspect-ratio: 4 / 3; object-fit: cover; border: 1px solid var(--color-line); border-radius: var(--radius-lg); background: var(--color-surface-sunken); transition: border-color var(--motion-duration-fast) var(--motion-ease-standard), box-shadow var(--motion-duration-fast) var(--motion-ease-standard); }
	.style-card:hover:not(:disabled) { color: var(--color-ink-0); }
	.style-card:hover:not(:disabled) img { border-color: var(--color-line-2); }
	.style-card:focus-visible { outline: none; }
	.style-card:focus-visible img { box-shadow: var(--focus-ring); }
	.style-selected { color: var(--color-ink-0); font-weight: 600; }
	.style-selected img { border-color: var(--color-action-warm); box-shadow: 0 0 0 3px var(--warm-ring); }
	.style-card:disabled { opacity: 0.55; cursor: not-allowed; }

	.result-head { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 0.5rem; }
	.run-status { font-size: 0.75rem; font-weight: 500; color: var(--color-ink-1); }
	.run-progress { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 0.75rem; }
	.developing { width: 100%; max-width: 36rem; margin-inline: auto; display: grid; place-items: center; border: 1px solid var(--color-line); border-radius: var(--radius-xl); }
	.developing-status { position: relative; z-index: 1; display: grid; justify-items: center; gap: 0.5rem; padding: 1rem; text-align: center; }
	.gallery { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 22rem), 1fr)); gap: 1rem; }
	.gallery figure { margin: 0; min-width: 0; border: 1px solid var(--color-line); border-radius: var(--radius-xl); overflow: hidden; background: var(--color-surface-raised); }
	.image-frame { min-height: 16rem; display: grid; place-items: center; color: var(--color-ink-2); background: var(--color-surface-sunken); font-size: 0.8125rem; }
	.image-frame img { display: block; width: 100%; height: auto; max-height: 44rem; object-fit: contain; }
	figcaption { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 0.5rem; padding: 0.75rem 1rem; font-size: 0.8125rem; color: var(--color-ink-1); }
	.history-block { display: grid; gap: 0.5rem; padding-top: 1rem; border-top: 1px solid var(--color-line); }
	.history-block h3 { margin: 0; font-size: 0.8125rem; font-weight: 600; color: var(--color-ink-1); }
	.history { display: flex; flex-wrap: wrap; gap: 0.5rem; }

	@media (min-width: 768px) {
		.studio { gap: 2.5rem; }
		.composer { padding: 1.25rem; }
		.composer :global(.composer-submit) { width: auto; margin-left: auto; }
		.style-grid { gap: 1rem; }
	}
	@media (min-width: 1024px) {
		.studio-header { padding-top: 2.5rem; }
		.composer-options { grid-template-columns: minmax(12rem, 2fr) repeat(3, minmax(9rem, 1fr)); }
		.composer-options :global(.option-model) { grid-column: auto; }
		.style-grid { grid-template-columns: repeat(6, minmax(0, 1fr)); }
	}
</style>
