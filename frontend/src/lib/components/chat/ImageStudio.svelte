<script lang="ts">
	import { onDestroy, untrack } from 'svelte';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import { auth, authReady, projectSwitching } from '$lib/stores/auth';
	import { imageStudioApi, imageModelReadiness, type ImageEditFields, type ImageModel, type ImageRun, type ImageUsage, type ImageApiScope, type ImageCapabilities } from '$lib/api/imageStudio';
	import { isChatImageMime } from '$lib/api/chatAttachments';
	import { ApiError } from '$lib/api/client';
	import { Alert, Button, Field, PageShell, SelectInput, TextareaInput, TextInput } from '$lib/components/ui';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import { IMAGE_STUDIO_STYLES, composeImagePrompt, imageRequestAspectRatio, type ImageStudioStyleId } from './imageStudioStyles';
	import { estimateImageOutputTokens, imageAssetExtension, imageDimensions, imageInteger, validCustomImageSize } from './imageStudioOptions';
	import { t } from '$lib/i18n/ns/chat-studio';
	import { effortLabel } from '$lib/api/chatEffort';
	import { t as chatT } from '$lib/i18n/ns/chat-panel';
	import { serviceCapabilities, serviceDenials } from '$lib/stores/servicePermissions';
	import LumenPermissionNotice from './LumenPermissionNotice.svelte';
	import { beginExperienceAction, beginExperienceLoad, experienceApplied, experienceDiscarded, experienceState } from '$lib/utils/experience';

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
	let customSize = $state('');
	let customSizeField = $state<HTMLInputElement | null>(null);
	let customSizeChecked = $state(false);
	let background = $state('');
	let outputFormat = $state('');
	let compression = $state('');
	let complexity = $state('');
	let frameCount = $state('');
	let frameDuration = $state('');
	type AttachmentRole = 'input' | 'mask' | 'markup';
	interface ImageAttachment { key: number; role: AttachmentRole; id: string; name: string; url: string }
	let attachments = $state<ImageAttachment[]>([]);
	let attachmentSequence = 0;
	let svgAuthor = $state('');
	let svgEffort = $state('');
	let inputFidelity = $state('');
	let moderation = $state('');
	let fileInput = $state<HTMLInputElement>();
	let overlayInput = $state<HTMLInputElement>();
	let pickingOverlay = $state<'mask' | 'markup'>('mask');
	let uploading = $state(false);
	let inputGeneration = 0;
	let submitting = $state(false);
	let error = $state('');
	let runIds = $state<string[]>([]);
	let selectedRunId = $state<string | null>(null);
	let currentRun = $state<ImageRun | null>(null);
	let usage = $state<ImageUsage | null>(null);
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
	let usageAbort: AbortController | null = null;
	let activeScopeKey = '';
	let activeCapabilityKey = '';
	let pendingIntent: { fingerprint: string; key: string } | null = null;
	const chosenModel = $derived(models.find((model) => String(model.id) === modelId));
	const readiness = $derived(imageModelReadiness(chosenModel));
	const runActive = $derived(Boolean(currentRun && !currentRun.terminal));
	const busy = $derived(submitting || uploading || runActive);
	const selectedStyle = $derived(IMAGE_STUDIO_STYLES.find((style) => style.id === styleId));
	const composedPrompt = $derived(composeImagePrompt(prompt, styleId));
	const inputs = $derived(attachments.filter((asset) => asset.role === 'input'));
	const overlay = $derived(attachments.find((asset) => asset.role !== 'input'));
	const hasInput = $derived(inputs.length > 0);
	const maxInputs = $derived(Math.min(16, capabilities?.max_image_input_count ?? 1));
	const variants = $derived((capabilities?.available_image_variants ?? []).map((variant) => {
		const [variantSize, variantQuality] = variant.split(':');
		return { size: variantSize, quality: variantQuality };
	}).filter(({ size: variantSize, quality: variantQuality }) => Boolean(variantSize && variantQuality)));
	const presetSizes = $derived([...new Set(variants.map((variant) => variant.size))]);
	const customLimits = $derived(capabilities?.image_custom_size);
	const custom = $derived(size === 'custom' && !!customLimits);
	const customSizeValid = $derived(!custom || validCustomImageSize(customSize, customLimits!));
	const requestedSize = $derived(custom ? customSize.trim().toLowerCase() : size);
	const qualities = $derived([...new Set(variants.filter((variant) => custom || variant.size === size).map((variant) => variant.quality))]);
	const gif = $derived(capabilities?.image_gif);
	const formats = $derived((capabilities?.image_output_formats ?? []).filter((value) => (value !== 'svg' || !hasInput) &&
		(value !== 'gif' || (gif && (gif.size_auto_supported !== false || customLimits || presetSizes.some((value) => value !== 'auto'))))));
	const format = $derived(formats.includes(outputFormat) ? outputFormat : '');
	const gifNeedsSize = $derived(format === 'gif' && gif?.size_auto_supported === false);
	const sizes = $derived(gifNeedsSize ? presetSizes.filter((value) => value !== 'auto') : presetSizes);
	const svgAuthors = $derived(format === 'svg' ? capabilities?.image_svg_author_models ?? [] : []);
	const svgEfforts = $derived(svgAuthors.find(({ model }) => model === svgAuthor)?.reasoning_efforts ?? []);
	const canMask = $derived(hasInput && format !== 'gif' && capabilities?.image_mask_supported === true);
	const canMarkup = $derived(hasInput && capabilities?.image_markup_supported === true);
	const attachmentConflict = $derived(inputs.length > maxInputs || !!(overlay && !(overlay.role === 'mask' ? canMask : canMarkup)));
	const backgrounds = $derived((capabilities?.image_backgrounds ?? []).filter((value) => value !== 'transparent' || ['', 'png', 'webp'].includes(format)));
	const selectedBackground = $derived(backgrounds.includes(background) ? background : '');
	const compressed = $derived(format === 'jpeg' || format === 'webp');
	const maxCount = $derived(format === 'svg' ? 1 : Math.min(capabilities?.max_image_count ?? 1, 10));
	const variantReady = $derived(qualities.includes(quality) && imageInteger(count, 1, maxCount) !== undefined);
	const compressionValue = $derived(compressed ? imageInteger(compression, 0, 100) : undefined);
	const frames = $derived(format === 'gif' && gif ? imageInteger(frameCount, gif.min_frame_count, gif.max_frame_count) : undefined);
	const duration = $derived(format === 'gif' && gif ? imageInteger(frameDuration, gif.min_frame_duration_ms, gif.max_frame_duration_ms) : undefined);
	const dimensions = $derived(imageDimensions(requestedSize));
	const gifBudgetExceeded = $derived(format === 'gif' && !!gif && !!dimensions && frames !== undefined &&
		dimensions[0] * dimensions[1] * frames * Number(count) > gif.max_total_pixels);
	const optionalFields = $derived({
		...(selectedBackground ? { background: selectedBackground } : {}),
		...(format ? { output_format: format } : {}),
		...(compressionValue !== undefined ? { output_compression: compressionValue } : {}),
		...(capabilities?.image_complexities?.includes(complexity) ? { complexity } : {}),
		...(frames !== undefined ? { frame_count: frames } : {}),
		...(duration !== undefined ? { frame_duration_ms: duration } : {}),
		...(capabilities?.image_moderation_options?.includes(moderation) ? { moderation } : {}),
		...(svgAuthors.some(({ model }) => model === svgAuthor) ? { svg_model: svgAuthor } : {}),
		...(svgEfforts.includes(svgEffort) ? { svg_reasoning_effort: svgEffort } : {})
	});
	const imageRequest = $derived({ model_id: modelId, prompt: composedPrompt, size: requestedSize, quality, n: Number(count), ...optionalFields });
	const editFields = $derived.by((): ImageEditFields | null => {
		if (!inputs.length) return null;
		const ids = inputs.map(({ id }) => id);
		return {
			...(ids.length === 1 ? { input_asset_id: ids[0] } : { input_asset_ids: ids }),
			...(overlay?.role === 'mask' ? { mask_asset_id: overlay.id } : {}),
			...(overlay?.role === 'markup' ? { markup_asset_id: overlay.id } : {}),
			...(capabilities?.image_input_fidelities?.includes(inputFidelity) ? { input_fidelity: inputFidelity } : {})
		};
	});
	const requestFingerprint = $derived(JSON.stringify([storageKey, imageRequest, editFields]));
	const canSubmit = $derived(imagesAllowed && !readiness && !modelsLoading && !capabilitiesLoading && variantReady && !busy && Boolean(composedPrompt) &&
		!attachmentConflict && attachments.every(({ id }) => Boolean(id)));
	const estimate = $derived.by(() => {
		const rate = capabilities?.image_output_price_per_million;
		if (!rate || !chosenModel || !variantReady || !customSizeValid || format === 'gif' || format === 'svg') return null;
		const tokens = estimateImageOutputTokens(chosenModel.api_model_name ?? chosenModel.model_name, requestedSize, quality, Number(count));
		const usd = Number(rate);
		return tokens !== null && Number.isFinite(usd) && usd >= 0 ? { tokens, usd: tokens * usd / 1_000_000 } : null;
	});
	const currency = $derived(new Intl.NumberFormat(intlLocale(), { style: 'currency', currency: 'USD', maximumFractionDigits: 8 }));
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
		requestScope = { ...requestScope, experience: beginExperienceLoad('lumen', 'resource.detail') };
		experienceState(requestScope.experience, 'loading', 1);
		capabilitiesLoading = true;
		capabilitiesError = '';
		try {
			const loaded = await imageStudioApi.capabilities(model.id, requestScope);
			if (generation !== capabilityRequest || !canPublish(requestScope)) { experienceDiscarded(requestScope.experience, 'stale'); return; }
			capabilities = loaded;
			const first = loaded.available_image_variants?.[0]?.split(':');
			size = first?.[0] ?? '';
			quality = first?.[1] ?? '';
			count = '1';
			customSize = '';
			customSizeChecked = false;
			background = '';
			outputFormat = '';
			compression = '';
			complexity = '';
			moderation = '';
			svgAuthor = '';
			svgEffort = '';
			inputFidelity = '';
			frameCount = loaded.image_gif ? String(loaded.image_gif.default_frame_count) : '';
			frameDuration = loaded.image_gif ? String(loaded.image_gif.default_frame_duration_ms) : '';
			experienceState(requestScope.experience, 'ready', 1);
			void experienceApplied(requestScope.experience, {}, () => generation === capabilityRequest && canPublish(requestScope));
		} catch (cause) {
			if (generation === capabilityRequest && canPublish(requestScope)) {
				capabilitiesError = message(cause); experienceState(requestScope.experience, 'error', 1);
				const displayedError = capabilitiesError;
				void experienceApplied(requestScope.experience, {}, () => generation === capabilityRequest && canPublish(requestScope) && capabilitiesError === displayedError);
			}
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
	$effect(() => {
		if (outputFormat && format !== outputFormat) outputFormat = '';
		if (background && selectedBackground !== background) background = '';
		if (format === 'svg' && count !== '1') count = '1';
		if (gifNeedsSize && size === 'auto') size = sizes[0] ?? 'custom';
		if (format !== 'svg') svgAuthor = '';
		if (svgEffort && !svgEfforts.includes(svgEffort)) svgEffort = '';
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
		usageAbort?.abort();
		usageAbort = null;
		usage = null;
	}
	function clearInput() {
		inputGeneration += 1;
		uploadAbort?.abort();
		uploadAbort = null;
		uploading = false;
		for (const item of attachments) URL.revokeObjectURL(item.url);
		attachments = [];
		if (fileInput) fileInput.value = '';
		if (overlayInput) overlayInput.value = '';
	}
	function removeAttachment(item: ImageAttachment) {
		if (uploading) {
			inputGeneration += 1;
			uploadAbort?.abort();
			uploadAbort = null;
			uploading = false;
		}
		const pairedOverlay = item.role === 'input' && inputs[0]?.key === item.key ? overlay : undefined;
		attachments = attachments.filter(({ key }) => key !== item.key && key !== pairedOverlay?.key);
		URL.revokeObjectURL(item.url);
		if (pairedOverlay) URL.revokeObjectURL(pairedOverlay.url);
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
			case 'xhigh': return t('imageStudio.quality.xhigh');
			case 'max': return t('imageStudio.quality.max');
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
		requestScope = { ...requestScope, experience: beginExperienceLoad('lumen', 'resource.list') };
		experienceState(requestScope.experience, 'loading', 0);
		modelsLoading = true;
		modelsError = '';
		try {
			const loaded = await imageStudioApi.models(requestScope);
			if (generation !== modelRequest || !canPublish(requestScope)) { experienceDiscarded(requestScope.experience, 'stale'); return; }
			models = loaded;
			modelsLoaded = true;
			if (!loaded.some((model) => String(model.id) === modelId)) modelId = loaded[0] ? String(loaded[0].id) : '';
			experienceState(requestScope.experience, loaded.length ? 'ready' : 'empty', 0);
			void experienceApplied(requestScope.experience, {}, () => generation === modelRequest && canPublish(requestScope));
		} catch (cause) {
			if (generation === modelRequest && canPublish(requestScope)) {
				modelsError = message(cause); experienceState(requestScope.experience, 'error', 0);
				const displayedError = modelsError;
				void experienceApplied(requestScope.experience, {}, () => generation === modelRequest && canPublish(requestScope) && modelsError === displayedError);
			}
		} finally {
			if (generation === modelRequest) modelsLoading = false;
		}
	}
	async function loadRun(id: string, requestScope: ImageApiScope, generation: number) {
		if (generation !== operation || !canPublish(requestScope) || !scope) return;
		if (document.hidden || navigator.onLine === false) {
			clearTimer();
			timer = setTimeout(() => { void loadRun(id, requestScope, generation); }, 2000);
			return;
		}
		requestScope = { ...scope, experience: requestScope.experience ?? beginExperienceLoad('lumen', 'shared.stream') };
		loadingRun = true;
		try {
			const run = await imageStudioApi.run(id, requestScope);
			if (generation !== operation || selectedRunId !== id || !canPublish(requestScope)) { experienceDiscarded(requestScope.experience, 'stale'); return; }
			const firstCompletion = currentRun?.run_id !== run.run_id || currentRun?.status !== 'completed';
			const stateChanged = currentRun?.run_id !== run.run_id || currentRun?.status !== run.status || currentRun?.terminal !== run.terminal;
			currentRun = run;
			loadingRun = false;
			// Admission and polling are not terminal success. Only the native run's terminal status is observed.
			if (stateChanged) {
				experienceState(requestScope.experience, !run.terminal ? 'loading' : run.status === 'completed' ? 'ready' : run.status === 'failed' ? 'error' : 'disabled', 3);
				void experienceApplied(requestScope.experience, {}, () => generation === operation && selectedRunId === id && canPublish(requestScope) && currentRun?.status === run.status && currentRun?.terminal === run.terminal);
			}
			if (run.terminal) {
				if (run.status === 'completed' && firstCompletion) {
					void loadPreviews(run, requestScope, generation);
					void loadUsage(id, requestScope, generation);
				}
			} else {
				clearTimer();
				timer = setTimeout(() => { void loadRun(id, requestScope, generation); }, 2000);
			}
		} catch (cause) {
			if (generation === operation && canPublish(requestScope)) {
				loadingRun = false;
				error = t('imageStudio.runLoadFailed', { message: message(cause) });
				experienceState(requestScope.experience, 'error', 3);
			}
		}
	}
	async function loadUsage(id: string, requestScope: ImageApiScope, generation: number) {
		const controller = new AbortController();
		usageAbort?.abort();
		usageAbort = controller;
		const timer = setTimeout(() => controller.abort(), 15_000);
		try {
			const result = await imageStudioApi.usage(id, requestScope, controller.signal);
			if (!controller.signal.aborted && generation === operation && selectedRunId === id && canPublish(requestScope)) usage = result;
		} catch {
			// Older or expired journals can omit usage. Do not invent a charge or hide images.
		} finally {
			clearTimeout(timer);
			if (usageAbort === controller) usageAbort = null;
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
				const blob = await imageStudioApi.download(asset.asset_id, { ...scope, experience: requestScope.experience }, controller.signal);
				if (generation !== operation || controller.signal.aborted || !canPublish(requestScope)) { experienceDiscarded(requestScope.experience, 'stale'); return; }
				if (imageAssetExtension(asset.mime_type) && blob.type === asset.mime_type) {
					previewUrls = { ...previewUrls, [asset.asset_id]: URL.createObjectURL(blob) };
					void experienceApplied(requestScope.experience, {}, () => generation === operation && !controller.signal.aborted && canPublish(requestScope));
				}
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

	async function selectFile(event: Event, role: AttachmentRole = 'input') {
		const picker = event.currentTarget as HTMLInputElement;
		const files = Array.from(picker.files ?? []);
		picker.value = '';
		if (!assetsAllowed || activeScopeKey !== storageKey || busy || !scope || !files.length) return;
		if (files.some((file) => role === 'input' ? !isChatImageMime(file.type) : file.type !== 'image/png')) {
			error = t(role === 'input' ? 'imageStudio.invalidFile' : 'imageStudio.advanced.overlayHelp');
			return;
		}
		if (role === 'input') {
			if (files.length > maxInputs || (maxInputs > 1 && files.length + inputs.length > maxInputs)) {
				error = t('imageStudio.advanced.inputLimit', { max: maxInputs });
				return;
			}
			if (maxInputs === 1) {
				if (inputs.length > 1) return;
				clearInput();
			}
		} else {
			if (files.length !== 1 || (role === 'mask' ? !canMask : !canMarkup)) return;
			if (overlay) removeAttachment(overlay);
		}
		const generation = inputGeneration;
		const controller = new AbortController();
		uploadAbort = controller;
		const requestScope = { ...scope, experience: beginExperienceAction('lumen', 'attach', 'resource.detail') };
		experienceState(requestScope.experience, 'loading', 5);
		const added = files.map((file) => ({ key: ++attachmentSequence, role, id: '', name: file.name, url: URL.createObjectURL(file) }));
		attachments = [...attachments, ...added];
		uploading = true;
		error = '';
		try {
			for (const [index, file] of files.entries()) {
				const asset = await imageStudioApi.upload(file, requestScope, controller.signal);
				if (generation !== inputGeneration || !assetsAllowed || activeScopeKey !== storageKey || requestScope.projectId !== scope?.projectId) { experienceDiscarded(requestScope.experience, 'stale'); return; }
				const attachment = attachments.find(({ key }) => key === added[index].key);
				if (attachment) { attachment.id = asset.id; attachment.name = asset.name; }
			}
			experienceState(requestScope.experience, 'ready', 5);
			void experienceApplied(requestScope.experience, {}, () => generation === inputGeneration && assetsAllowed && activeScopeKey === storageKey && requestScope.projectId === scope?.projectId);
		} catch (cause) {
			if (generation !== inputGeneration || !assetsAllowed || activeScopeKey !== storageKey || requestScope.projectId !== scope?.projectId) { experienceDiscarded(requestScope.experience, 'stale'); return; }
			error = t('imageStudio.uploadFailed', { message: message(cause) });
			experienceState(requestScope.experience, 'error', 5);
		} finally {
			if (uploadAbort === controller) {
				uploadAbort = null;
				uploading = false;
			}
		}
	}
	async function submit() {
		if (!canSubmit || !scope || !canPublish(scope)) return;
		if (!customSizeValid) {
			customSizeChecked = true;
			customSizeField?.focus();
			return;
		}
		if (gifBudgetExceeded || (format === 'gif' && (frames === undefined || duration === undefined)) ||
			(compressed && compression != null && compression !== '' && compressionValue === undefined)) return;
		const requestScope = { ...scope, experience: beginExperienceAction('lumen', 'submit', 'shared.stream') };
		experienceState(requestScope.experience, 'loading', 2);
		const generation = ++operation;
		const controller = new AbortController();
		submitAbort = controller;
		clearTimer();
		clearPreviews();
		currentRun = null;
		selectedRunId = null;
		liveRunId = null;
		const context: RunContext = { size: requestedSize, startedAt: Date.now(), submitted: true };
		runContext = context;
		error = '';
		submitting = true;
		try {
			const request = imageRequest;
			const fingerprint = requestFingerprint;
			const idempotencyKey = pendingIntent?.fingerprint === fingerprint ? pendingIntent.key : crypto.randomUUID();
			pendingIntent = { fingerprint, key: idempotencyKey };
			const descriptor = await imageStudioApi.submit(editFields ? 'edits' : 'generations', editFields ? { ...request, ...editFields } : request, requestScope, idempotencyKey, controller.signal);
			if (generation !== operation || !canPublish(requestScope)) { experienceDiscarded(requestScope.experience, 'stale'); return; }
			pendingIntent = null;
			// A completed admission or known history ID is replay, not a new live result.
			liveRunId = !runIds.includes(descriptor.run_id) && !['completed', 'failed', 'canceled'].includes(descriptor.status) ? descriptor.run_id : null;
			runContexts.set(descriptor.run_id, context);
			runIds = [descriptor.run_id, ...runIds.filter((id) => id !== descriptor.run_id)].slice(0, 20);
			saveHistory(storageKey, runIds);
			selectedRunId = descriptor.run_id;
			void experienceApplied(requestScope.experience, {}, () => generation === operation && canPublish(requestScope));
			void loadRun(descriptor.run_id, requestScope, generation);
		} catch (cause) {
			if (generation === operation && canPublish(requestScope)) {
				error = message(cause);
				experienceState(requestScope.experience, 'error', 2);
				if (controller.signal.aborted) experienceDiscarded(requestScope.experience, 'aborted');
				else if (!(cause instanceof ApiError && cause.status >= 400 && cause.status < 500)) experienceDiscarded(requestScope.experience, 'unknown');
			}
		} finally {
			if (submitAbort === controller) submitAbort = null;
			if (generation === operation) submitting = false;
		}
	}
	async function cancel() {
		if (!scope || !canPublish(scope) || !selectedRunId || currentRun?.terminal) return;
		const requestScope = { ...scope, experience: beginExperienceAction('lumen', 'cancel', 'shared.stream') };
		const generation = operation;
		try {
			await imageStudioApi.cancel(selectedRunId, requestScope);
			// A cancellation response is only a request; read the actual run before changing its displayed state.
			if (generation === operation && canPublish(requestScope) && selectedRunId && scope) void loadRun(selectedRunId, { ...scope, experience: requestScope.experience }, generation);
			else experienceDiscarded(requestScope.experience, 'stale');
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

<PageShell>
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
			{#if assetsAllowed}
				{#each attachments as item (item.key)}
					<div class="attachment">
						<img src={item.url} alt={t('imageStudio.inputPreview')} />
						<div class="attachment-meta">
							<p class="attachment-name">{#if item.role !== 'input'}{t(item.role === 'mask' ? 'imageStudio.advanced.mask' : 'imageStudio.advanced.markup')} · {/if}{item.name}</p>
							{#if item.id}<p role="status" class="muted">{t('imageStudio.uploadComplete', { name: item.name })}</p>{:else if uploading}<LoadingState variant="inline" label={t('imageStudio.uploading')} />{/if}
						</div>
						<Button variant="ghost" size="sm" ariaLabel={attachments.length === 1 ? t('imageStudio.removeAttachment') : t('imageStudio.advanced.remove', { name: item.name })} onclick={() => removeAttachment(item)} disabled={submitting || runActive}>{t('imageStudio.remove')}</Button>
					</div>
				{/each}
			{/if}
			<div class="composer-bar">
				<div class="composer-options">
					<Field label={t('imageStudio.model')} for="studio-model" class="option-model">
						<SelectInput id="studio-model" value={modelId} onchange={selectModel} disabled={!imagesAllowed || modelsLoading || busy || models.length === 0}><option value="">{t('imageStudio.selectModel')}</option>{#each models as model (model.id)}<option value={String(model.id)}>{model.display_name}</option>{/each}</SelectInput>
					</Field>
					<Field label={t('imageStudio.size')} for="studio-size"><SelectInput id="studio-size" bind:value={size} disabled={!imagesAllowed || busy || capabilitiesLoading || sizes.length === 0}>{#each sizes as option (option)}<option value={option}>{option === 'auto' ? t('imageStudio.autoSize') : option.replace('x', ' × ')}</option>{/each}{#if customLimits}<option value="custom">{t('imageStudio.options.custom')}</option>{/if}</SelectInput></Field>
					<Field label={t('imageStudio.qualityLabel')} for="studio-quality"><SelectInput id="studio-quality" bind:value={quality} disabled={!imagesAllowed || busy || capabilitiesLoading || qualities.length === 0}>{#each qualities as option (option)}<option value={option}>{displayQuality(option)}</option>{/each}</SelectInput></Field>
					<Field label={t('imageStudio.imageCount')} for="studio-count"><SelectInput id="studio-count" bind:value={count} disabled={!imagesAllowed || busy || capabilitiesLoading || maxCount < 1}>{#each Array.from({ length: maxCount }, (_, index) => index + 1) as option (option)}<option value={String(option)}>{option}</option>{/each}</SelectInput></Field>
				</div>
				{#if formats.length || backgrounds.length || capabilities?.image_complexities?.length || capabilities?.image_moderation_options?.length || (hasInput && capabilities?.image_input_fidelities?.length) || custom}
					<fieldset class="advanced-options" disabled={!imagesAllowed || busy || capabilitiesLoading}>
						<legend class="muted">{t('imageStudio.options.title')}</legend>
						{#if custom}
							{@const limits = { multiple: customLimits!.dimension_multiple, edge: customLimits!.max_edge, ratio: customLimits!.max_aspect_ratio, min: customLimits!.min_pixels, max: customLimits!.max_pixels }}
							{@const help = t('imageStudio.options.sizeHelp', limits)}
							<div class="custom-size" onfocusout={() => { if (customSize) customSizeChecked = true; }}>
								<Field label={t('imageStudio.options.custom')} for="studio-custom-size" help={help} error={customSizeChecked && !customSizeValid ? t('imageStudio.options.badSize', { limits: help }) : undefined}>
									<TextInput id="studio-custom-size" bind:value={customSize} bind:element={customSizeField} placeholder="1024x1024" maxlength={9} ariaInvalid={customSizeChecked && !customSizeValid} />
								</Field>
							</div>
						{/if}
						{#if capabilities?.image_complexities?.length}
							<Field label={t('imageStudio.options.complexity')} for="studio-complexity"><SelectInput id="studio-complexity" bind:value={complexity}><option value="">{t('imageStudio.options.default')}</option>{#each capabilities.image_complexities as value (value)}<option {value}>{displayQuality(value)}</option>{/each}</SelectInput></Field>
						{/if}
						{#if formats.length}
							<Field label={t('imageStudio.options.format')} for="studio-format"><SelectInput id="studio-format" bind:value={outputFormat}><option value="">{t('imageStudio.options.default')}</option>{#each formats as value (value)}<option {value}>{value.toUpperCase()}</option>{/each}</SelectInput></Field>
						{/if}
						{#if backgrounds.length}
							<Field label={t('imageStudio.options.background')} for="studio-background"><SelectInput id="studio-background" bind:value={background}><option value="">{t('imageStudio.options.default')}</option>{#each backgrounds as value (value)}<option {value}>{value === 'transparent' ? t('imageStudio.options.transparent') : value === 'opaque' ? t('imageStudio.options.opaque') : displayQuality(value)}</option>{/each}</SelectInput></Field>
						{/if}
						{#if capabilities?.image_moderation_options?.length}
							<Field label={t('imageStudio.advanced.moderation')} for="studio-moderation"><SelectInput id="studio-moderation" bind:value={moderation}><option value="">{t('imageStudio.options.default')}</option>{#each capabilities.image_moderation_options as value (value)}<option {value}>{displayQuality(value)}</option>{/each}</SelectInput></Field>
						{/if}
						{#if hasInput && capabilities?.image_input_fidelities?.length}
							<Field label={t('imageStudio.advanced.fidelity')} for="studio-fidelity"><SelectInput id="studio-fidelity" bind:value={inputFidelity}><option value="">{t('imageStudio.options.default')}</option>{#each capabilities.image_input_fidelities as value (value)}<option {value}>{displayQuality(value)}</option>{/each}</SelectInput></Field>
						{/if}
						{#if svgAuthors.length}
							<Field label={t('imageStudio.advanced.svgAuthor')} for="studio-svg-author"><SelectInput id="studio-svg-author" bind:value={svgAuthor}><option value="">{t('imageStudio.options.default')}</option>{#each svgAuthors as author (author.model)}<option value={author.model}>{author.model}</option>{/each}</SelectInput></Field>
						{/if}
						{#if svgEfforts.length}
							<Field label={chatT('input.reasoningEffort')} for="studio-svg-effort"><SelectInput id="studio-svg-effort" bind:value={svgEffort}><option value="">{t('imageStudio.options.default')}</option>{#each svgEfforts as value (value)}<option {value}>{effortLabel(value)}</option>{/each}</SelectInput></Field>
						{/if}
						{#if compressed}
							<Field label={t('imageStudio.options.compression')} for="studio-compression" help={t('imageStudio.options.compressionHelp')}>
								<TextInput id="studio-compression" type="number" min={0} max={100} step={1} bind:value={compression} />
							</Field>
						{/if}
						{#if format === 'gif' && gif}
							<Field label={t('imageStudio.options.frames')} for="studio-frames"><SelectInput id="studio-frames" bind:value={frameCount}>{#each Array.from({ length: gif.max_frame_count - gif.min_frame_count + 1 }, (_, index) => gif!.min_frame_count + index) as value (value)}<option value={String(value)}>{value}</option>{/each}</SelectInput></Field>
							<Field label={t('imageStudio.options.frameDuration')} for="studio-frame-duration" help={t('imageStudio.options.durationHelp', { min: gif.min_frame_duration_ms, max: gif.max_frame_duration_ms })}>
								<TextInput id="studio-frame-duration" type="number" min={gif.min_frame_duration_ms} max={gif.max_frame_duration_ms} step={1} required bind:value={frameDuration} />
							</Field>
							{#if gifBudgetExceeded}<p class="custom-size muted" role="status">{t('imageStudio.options.gifBudget')}</p>{/if}
						{/if}
					</fieldset>
				{/if}
				{#if estimate}<p class="muted">{t('imageStudio.options.estimate', { tokens: estimate.tokens, cost: currency.format(estimate.usd) })}</p>{/if}
				<div class="composer-actions">
					<Button variant="secondary" onclick={() => assetsAllowed && fileInput?.click()} disabled={busy || !assetsAllowed || (maxInputs > 1 ? inputs.length >= maxInputs : inputs.length > 1)}>{hasInput && maxInputs === 1 ? t('imageStudio.replaceImage') : t('imageStudio.attachImage')}</Button>
					<input bind:this={fileInput} type="file" accept="image/png,image/jpeg,image/webp" multiple={maxInputs > 1} class="sr-only" tabindex="-1" aria-label={t('imageStudio.inputImage')} onchange={(event) => selectFile(event)} disabled={busy || !assetsAllowed || (maxInputs > 1 ? inputs.length >= maxInputs : inputs.length > 1)} />
					{#if canMask}<Button variant="secondary" disabled={busy || !assetsAllowed} onclick={() => { pickingOverlay = 'mask'; overlayInput?.click(); }}>{t('imageStudio.advanced.mask')}</Button>{/if}
					{#if canMarkup}<Button variant="secondary" disabled={busy || !assetsAllowed} onclick={() => { pickingOverlay = 'markup'; overlayInput?.click(); }}>{t('imageStudio.advanced.markup')}</Button>{/if}
					{#if canMask || canMarkup}<input bind:this={overlayInput} type="file" accept="image/png" hidden aria-label={t('imageStudio.advanced.overlayFile')} onchange={(event) => selectFile(event, pickingOverlay)} disabled={busy || !assetsAllowed} />{/if}
					<Button type="submit" variant="primary" size="lg" class="composer-submit" disabled={!canSubmit || gifBudgetExceeded}>{#if submitting}<LoadingState variant="control" label={t('imageStudio.submitting')} />{:else}{t('imageStudio.createImage')}{/if}</Button>
				</div>
				{#if canMask || canMarkup}<p class="muted">{t('imageStudio.advanced.overlayHelp')}</p>{/if}
				{#if attachmentConflict}<Alert tone="warning">{t('imageStudio.advanced.attachmentConflict')}</Alert>{/if}
			</div>
			<div class="composer-status">
				{#if !scope}<p role="status" class="muted">{t('imageStudio.signInHelp')}</p>
				{:else if imagesAllowed}
					{#if modelsLoading || capabilitiesLoading || (!modelsLoaded && !modelsError)}<LoadingState variant="inline" label={t('imageStudio.checkingOptions')} />
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
					{#if loadingRun && !currentRun}<LoadingState label={t('imageStudio.checkingJob')} />{/if}
					{#if currentRun && !currentRun.terminal}
						<div class="developing" style:aspect-ratio={developingRatio} aria-label={t('imageStudio.developing')}>
							<span class="sr-only" aria-busy="true">{t('imageStudio.developing')}</span>
							<div class="developing-status">
								<LoadingState variant="section" label={displayStatus(currentRun.status)} />
								<p class="muted">{runContext?.submitted ? t('imageStudio.elapsedSinceRequest', { seconds: elapsedSeconds }) : t('imageStudio.elapsedSinceView', { seconds: elapsedSeconds })}</p>
								<p class="muted">{runContext?.size === 'auto' ? t('imageStudio.requestedAutoSize') : runContext?.size ? t('imageStudio.requestedSize', { size: runContext.size.replace('x', ' × ') }) : t('imageStudio.requestedSizeUnknown')}</p>
							</div>
						</div>
						<div class="run-progress"><p class="muted">{t('imageStudio.processing')}</p><Button variant="danger-outline" onclick={cancel}>{t('imageStudio.cancelJob')}</Button></div>
					{/if}
					{#if currentRun?.status === 'failed'}<Alert tone="danger" title={t('imageStudio.jobFailedTitle')}>{t('imageStudio.jobFailed')}</Alert>{/if}
					{#if currentRun?.status === 'canceled'}<Alert tone="neutral">{t('imageStudio.jobCanceled')}</Alert>{/if}
					{#if currentRun?.status === 'completed'}
						{#if usage}
							<p class="muted">{t('imageStudio.options.usage', { input: usage.prompt_tokens, output: usage.completion_tokens, cost: currency.format(Number(usage.raw_cost)) })}</p>
						{/if}
						{#if currentRun.output_assets?.length}
							<div class="gallery">
								{#each currentRun.output_assets as asset (asset.asset_id)}
									<figure>
										<div class="image-frame">
											{#if previewUrls[asset.asset_id]}
												<img src={previewUrls[asset.asset_id]} alt={t('imageStudio.generatedImage')} use:revealLiveResult={asset.asset_id} />
											{:else}<LoadingState variant="section" label={t('imageStudio.loadingImage')} />{/if}
										</div>
										<figcaption><span>{t('imageStudio.imageMime', { mime: asset.mime_type })}</span><Button variant="secondary" onclick={() => download(asset.asset_id, `image-${asset.asset_id}.${imageAssetExtension(asset.mime_type) ?? 'bin'}`)}>{t('imageStudio.download')}</Button></figcaption>
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
	.studio { display: grid; gap: 2rem; width: 100%; min-width: 0; }
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
	.advanced-options { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 10rem), 1fr)); gap: 0.75rem; min-width: 0; margin: 0; padding: 0; border: 0; }
	.advanced-options legend { padding: 0 0 0.5rem; font-weight: 600; }
	.custom-size { grid-column: 1 / -1; }
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
	.developing { width: 100%; max-width: 36rem; margin-inline: auto; display: grid; place-items: stretch; overflow: hidden; border: 1px solid var(--color-line); border-radius: var(--radius-xl); }
	.developing-status { display: grid; grid-template-rows: minmax(0, 1fr) auto auto; justify-items: stretch; gap: 0.5rem; text-align: center; }
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
