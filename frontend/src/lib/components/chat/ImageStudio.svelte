<script lang="ts">
	import { onDestroy, untrack } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { imageStudioApi, imageModelReadiness, type ImageModel, type ImageRun, type ImageApiScope, type ImageCapabilities } from '$lib/api/imageStudio';
	import { isChatImageMime } from '$lib/api/chatAttachments';
	import { ApiError } from '$lib/api/client';
	import { Alert, Button, Field, PageShell, SelectInput, TextareaInput } from '$lib/components/ui';
	import { IMAGE_STUDIO_STYLES, composeImagePrompt, type ImageStudioStyleId } from './imageStudioStyles';

	const scope = $derived($auth.token && $auth.projectId ? { token: $auth.token, projectId: $auth.projectId } : null);
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
	const canSubmit = $derived(Boolean(scope) && !readiness && !modelsLoading && !capabilitiesLoading && variantReady && !busy && Boolean(composedPrompt) && (!hasInput || Boolean(inputAssetId)));
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
			if (cause.status === 401 || cause.status === 403) return '현재 프로젝트에 접근할 수 없습니다. 로그인과 프로젝트 선택을 확인하세요.';
			if (cause.status === 402) return '사용 가능한 이미지 생성 크레딧 또는 할당량이 부족합니다.';
			if (cause.status === 429) return '요청이 많습니다. 잠시 후 다시 시도하세요.';
			if (cause.status === 400 || cause.status === 422 || cause.status === 409) return cause.message.slice(0, 250);
			return `서비스 요청에 실패했습니다 (${cause.status}). 잠시 후 다시 시도하세요.`;
		}
		return '서비스에 연결하지 못했습니다. 네트워크 상태를 확인하고 다시 시도하세요.';
	}
	function displayStatus(status: string): string {
		return ({ queued: '대기 중', running: '생성 중', waiting_resource: '리소스 대기 중', finalizing: '결과 저장 중', completed: '완료', failed: '실패', canceled: '취소됨' } as Record<string, string>)[status] ?? status;
	}

	async function loadModels(requestScope: ImageApiScope, generation: number) {
		modelsLoading = true;
		modelsError = '';
		try {
			const loaded = await imageStudioApi.models(requestScope);
			if (generation !== modelRequest) return;
			models = loaded;
			modelsLoaded = true;
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
				error = `실행 상태를 읽지 못했습니다: ${message(cause)}`;
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
				if (generation === operation && !controller.signal.aborted) error = `이미지 미리보기를 불러오지 못했습니다: ${message(cause)}`;
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
			clearInput();
			submitAbort?.abort();
			pendingIntent = null;
			submitting = false;
			loadingRun = false;
			models = [];
			modelsLoaded = false;
			modelId = '';
			runIds = [];
			selectedRunId = null;
			currentRun = null;
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
		clearInput();
		submitAbort?.abort();
	});

	async function selectFile(event: Event) {
		const file = (event.currentTarget as HTMLInputElement).files?.[0];
		if (!file || !scope) return;
		if (!isChatImageMime(file.type)) {
			if (fileInput) fileInput.value = '';
			error = 'PNG, JPEG, WebP 이미지만 업로드할 수 있습니다.';
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
			if (generation !== inputGeneration) return;
			inputAssetId = asset.id;
			inputFileName = asset.name;
		} catch (cause) {
			if (generation !== inputGeneration) return;
			error = `입력 이미지 업로드 실패: ${message(cause)} 이미지를 교체하거나 제거한 뒤 다시 요청하세요.`;
		} finally {
			if (uploadAbort === controller) {
				uploadAbort = null;
				uploading = false;
			}
		}
	}
	async function submit() {
		if (!canSubmit || !scope) return;
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
			const request = { model_id: modelId, prompt: composedPrompt, size, quality, n: Number(count) };
			const fingerprint = requestFingerprint;
			const idempotencyKey = pendingIntent?.fingerprint === fingerprint ? pendingIntent.key : crypto.randomUUID();
			pendingIntent = { fingerprint, key: idempotencyKey };
			const descriptor = await imageStudioApi.submit(inputAssetId ? 'edits' : 'generations', inputAssetId ? { ...request, input_asset_id: inputAssetId } : request, requestScope, idempotencyKey, controller.signal);
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
		} catch (cause) { error = `취소 요청 실패: ${message(cause)}`; }
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
		} catch (cause) { error = `이미지 다운로드 실패: ${message(cause)}`; }
	}
</script>

<PageShell max="7xl">
	<div class="studio">
		<header class="studio-header">
			<svg class="studio-mark" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="16" rx="2.5" /><circle cx="15.5" cy="9" r="1.75" /><path d="m3.5 17 5-5.5 4 4 2.5-2.5 5.5 5.5" /></svg>
			<h1>이미지 Studio</h1>
			<p class="muted">원하는 이미지를 설명하세요. 결과는 현재 프로젝트에서만 조회할 수 있습니다.</p>
			<Button href="/dashboard/chat" variant="ghost" size="sm">텍스트 채팅으로</Button>
		</header>
		{#if modelsError}<Alert tone="danger" title="모델을 불러오지 못했습니다">{modelsError} <Button variant="subtle" onclick={() => scope && loadModels(scope, ++modelRequest)}>다시 시도</Button></Alert>{/if}
		{#if error}<Alert tone="danger">{error} {#if selectedRunId}<Button variant="subtle" onclick={() => scope && selectedRunId && selectRun(selectedRunId, scope)}>상태 다시 확인</Button>{/if}</Alert>{/if}

		<form class="composer" aria-label="이미지 요청" onsubmit={(event) => { event.preventDefault(); void submit(); }}>
			<TextareaInput id="studio-prompt" class="composer-prompt" bind:value={prompt} rows={4} ariaLabel="프롬프트" ariaDescribedBy={selectedStyle ? 'studio-input-note studio-style-note' : 'studio-input-note'} placeholder={hasInput ? '첨부 이미지를 참고해 새로 만들거나 수정할 내용을 설명하세요' : '만들고 싶은 이미지를 설명하세요'} disabled={busy} />
			<p id="studio-input-note" class="muted attachment-hint">이미지 없이 요청하면 새로 생성합니다. 첨부하면 모델이 프롬프트에 따라 참고해서 새로 만들거나 수정합니다.</p>
			{#if selectedStyle}
				<div class="style-note">
					<p id="studio-style-note"><span class="style-note-label">{selectedStyle.label} 스타일</span> 제출할 때 프롬프트 끝에 “스타일: {selectedStyle.instruction}” 지시가 추가됩니다.</p>
					<Button variant="ghost" size="sm" onclick={() => (styleId = null)} disabled={busy}>스타일 지우기</Button>
				</div>
			{/if}
			{#if inputPreviewUrl}
				<div class="attachment">
					<img src={inputPreviewUrl} alt="입력 이미지 미리보기" />
					<div class="attachment-meta">
						<p class="attachment-name">{inputFileName}</p>
						{#if uploading}<p role="status" class="muted">입력 이미지를 업로드하는 중…</p>{:else if inputAssetId}<p role="status" class="muted">업로드 완료: {inputFileName}</p>{/if}
					</div>
					<Button variant="ghost" size="sm" ariaLabel="첨부 이미지 제거" onclick={clearInput} disabled={submitting}>제거</Button>
				</div>
			{/if}
			<div class="composer-bar">
				<div class="composer-options">
					<Field label="이미지 모델" for="studio-model" class="option-model">
						<SelectInput id="studio-model" value={modelId} onchange={selectModel} disabled={modelsLoading || busy || models.length === 0}><option value="">모델 선택</option>{#each models as model (model.id)}<option value={String(model.id)}>{model.display_name}</option>{/each}</SelectInput>
					</Field>
					<Field label="크기" for="studio-size"><SelectInput id="studio-size" bind:value={size} disabled={busy || capabilitiesLoading || sizes.length === 0}>{#each sizes as option (option)}<option value={option}>{option === 'auto' ? '자동' : option.replace('x', ' × ')}</option>{/each}</SelectInput></Field>
					<Field label="품질" for="studio-quality"><SelectInput id="studio-quality" bind:value={quality} disabled={busy || capabilitiesLoading || qualities.length === 0}>{#each qualities as option (option)}<option value={option}>{option}</option>{/each}</SelectInput></Field>
					<Field label="이미지 수" for="studio-count"><SelectInput id="studio-count" bind:value={count} disabled={busy || capabilitiesLoading || maxCount < 1}>{#each Array.from({ length: maxCount }, (_, index) => index + 1) as option (option)}<option value={String(option)}>{option}</option>{/each}</SelectInput></Field>
				</div>
				<div class="composer-actions">
					<Button variant="secondary" onclick={() => fileInput?.click()} disabled={busy || !scope}>{inputPreviewUrl ? '이미지 교체' : '이미지 첨부'}</Button>
					<input bind:this={fileInput} type="file" accept="image/png,image/jpeg,image/webp" class="sr-only" tabindex="-1" aria-label="입력 이미지" onchange={selectFile} disabled={busy || !scope} />
					<Button type="submit" variant="primary" size="lg" class="composer-submit" disabled={!canSubmit}>{submitting ? '요청 중…' : '이미지 만들기'}</Button>
				</div>
			</div>
			<div class="composer-status">
				{#if !scope}<p role="status" class="muted">로그인하고 프로젝트를 선택하면 이미지 모델을 불러옵니다.</p>
				{:else if modelsLoading || capabilitiesLoading || (!modelsLoaded && !modelsError)}<p role="status" class="muted">모델과 사용 가능한 이미지 옵션을 확인하는 중…</p>
				{:else if modelsError}<p class="muted">모델 목록을 불러온 뒤 이미지를 요청할 수 있습니다.</p>
				{:else if models.length === 0}<Alert tone="warning" title="사용 가능한 이미지 모델 없음">현재 프로젝트에서 사용할 수 있는 이미지 모델이 없습니다. 관리자에게 이미지 모델 등록을 요청하세요.</Alert>
				{:else if readiness}<Alert tone="warning" title="실행 준비 필요">{readiness}</Alert>
				{:else if capabilitiesError}<Alert tone="danger" title="이미지 옵션 조회 실패">{capabilitiesError} <Button variant="subtle" onclick={() => chosenModel && scope && loadCapabilities(chosenModel, scope, ++capabilityRequest)}>다시 시도</Button></Alert>
				{:else if !variantReady}<Alert tone="warning">선택한 모델의 가격이 설정된 이미지 크기·품질을 사용할 수 없습니다.</Alert>
				{:else}<p role="status" class="muted">모델 제공자, 생성 경로, 선택한 크기·품질의 가격이 준비되었습니다.</p>{/if}
			</div>
		</form>

		<section class="styles" aria-labelledby="studio-styles-title">
			<div class="section-head">
				<h2 id="studio-styles-title">스타일</h2>
				<p class="muted">선택한 스타일은 별도 모델 옵션이 아니라 프롬프트 끝에 붙는 지시문으로 전송됩니다. 다시 누르면 해제됩니다.</p>
			</div>
			<div class="style-grid">
				{#each IMAGE_STUDIO_STYLES as style (style.id)}
					<button type="button" class="style-card" class:style-selected={styleId === style.id} aria-pressed={styleId === style.id} disabled={busy} onclick={() => (styleId = styleId === style.id ? null : style.id)}>
						<img src={style.image} alt="" loading="lazy" decoding="async" />
						<span>{style.label}</span>
					</button>
				{/each}
			</div>
		</section>

		{#if selectedRunId || runIds.length}
			<section class="results" aria-labelledby="studio-results-title">
				<div class="result-head">
					<h2 id="studio-results-title">작업 결과</h2>
					{#if currentRun}<span role="status" class="run-status">{displayStatus(currentRun.status)}</span>{/if}
				</div>
				{#if selectedRunId}
					{#if loadingRun && !currentRun}<p role="status" class="muted">작업 상태를 확인하는 중…</p>{/if}
					{#if currentRun && !currentRun.terminal}<div class="run-progress"><p role="status" class="muted">서버에서 이미지를 처리 중입니다. 이 페이지를 떠나도 작업은 계속됩니다.</p><Button variant="danger-outline" onclick={cancel}>작업 취소</Button></div>{/if}
					{#if currentRun?.status === 'failed'}<Alert tone="danger" title="이미지 작업 실패">실행이 실패했습니다. 다시 시도하거나 모델 설정을 확인하세요.</Alert>{/if}
					{#if currentRun?.status === 'canceled'}<Alert tone="neutral">작업이 취소되었습니다.</Alert>{/if}
					{#if currentRun?.status === 'completed'}{#if currentRun.output_assets?.length}<div class="gallery">{#each currentRun.output_assets as asset (asset.asset_id)}<figure><div class="image-frame">{#if previewUrls[asset.asset_id]}<img src={previewUrls[asset.asset_id]} alt="생성된 이미지" />{:else}<span>이미지 불러오는 중…</span>{/if}</div><figcaption><span>이미지 · {asset.mime_type}</span><Button variant="secondary" onclick={() => download(asset.asset_id, `image-${asset.asset_id}.${asset.mime_type.split('/')[1] ?? 'png'}`)}>다운로드</Button></figcaption></figure>{/each}</div>{:else}<Alert tone="warning">작업은 완료됐지만 출력 이미지가 없습니다.</Alert>{/if}{/if}
				{/if}
				{#if runIds.length}
					<div class="history-block">
						<h3>이 브라우저의 작업</h3>
						<div class="history">{#each runIds as id, index (id)}<Button size="sm" variant={selectedRunId === id ? 'accent' : 'secondary'} ariaPressed={selectedRunId === id} onclick={() => scope && selectRun(id, scope)}>작업 {runIds.length - index} · {id.slice(0, 8)}</Button>{/each}</div>
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
