<script lang="ts">
	import { onDestroy, untrack } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { imageStudioApi, imageModelReadiness, type ImageModel, type ImageRun, type ImageApiScope, type ImageCapabilities } from '$lib/api/imageStudio';
	import { isChatImageMime } from '$lib/api/chatAttachments';
	import { ApiError } from '$lib/api/client';
	import { Alert, Button, Card, Field, PageShell, SelectInput, TextareaInput } from '$lib/components/ui';

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
		if (!isChatImageMime(file.type)) { error = 'PNG, JPEG, WebP 이미지만 업로드할 수 있습니다.'; return; }
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
			if (generation === operation && !controller.signal.aborted) error = `입력 이미지 업로드 실패: ${message(cause)}`;
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
			<div><p class="eyebrow">AI 채팅 / 미디어</p><h1>이미지 Studio</h1><p class="muted">프롬프트로 이미지를 생성하거나 내 이미지를 업로드해 수정합니다. 결과는 현재 프로젝트에서만 조회할 수 있습니다.</p></div>
			<Button href="/dashboard/chat" variant="secondary">텍스트 채팅으로</Button>
		</header>
		{#if modelsError}<Alert tone="danger" title="모델을 불러오지 못했습니다">{modelsError} <Button variant="subtle" onclick={() => scope && loadModels(scope, ++modelRequest)}>다시 시도</Button></Alert>{/if}
		{#if error}<Alert tone="danger">{error} {#if selectedRunId}<Button variant="subtle" onclick={() => scope && selectedRunId && selectRun(selectedRunId, scope)}>상태 다시 확인</Button>{/if}</Alert>{/if}
		<div class="studio-grid">
			<Card>
				<form class="form" onsubmit={(event) => { event.preventDefault(); void submit(); }}>
					<div class="mode-row" role="group" aria-label="작업 유형">
						<Button variant={!editMode ? 'accent' : 'secondary'} ariaPressed={!editMode} onclick={() => (editMode = false)}>새 이미지</Button>
						<Button variant={editMode ? 'accent' : 'secondary'} ariaPressed={editMode} onclick={() => (editMode = true)}>이미지 수정</Button>
					</div>
					<Field label="이미지 모델" for="studio-model">
						<SelectInput id="studio-model" value={modelId} onchange={selectModel} disabled={modelsLoading || busy}><option value="">모델 선택</option>{#each models as model (model.id)}<option value={String(model.id)}>{model.display_name}</option>{/each}</SelectInput>
					</Field>
					{#if modelsLoading || capabilitiesLoading}<p role="status" class="muted">모델과 사용 가능한 이미지 옵션을 확인하는 중…</p>{:else if readiness}<Alert tone="warning" title="실행 준비 필요">{readiness}</Alert>{:else if capabilitiesError}<Alert tone="danger" title="이미지 옵션 조회 실패">{capabilitiesError} <Button variant="subtle" onclick={() => chosenModel && scope && loadCapabilities(chosenModel, scope, ++capabilityRequest)}>다시 시도</Button></Alert>{:else if !variantReady}<Alert tone="warning">선택한 모델의 가격이 설정된 이미지 크기·품질을 사용할 수 없습니다.</Alert>{:else}<Alert tone="success">모델 제공자, 생성 경로, 선택한 크기·품질의 가격이 준비되었습니다.</Alert>{/if}
					<Field label="프롬프트" for="studio-prompt" required><TextareaInput id="studio-prompt" bind:value={prompt} rows={5} placeholder="만들고 싶은 이미지를 설명하세요" disabled={busy} /></Field>
					<div class="options">
						<Field label="크기" for="studio-size"><SelectInput id="studio-size" bind:value={size} disabled={busy || capabilitiesLoading}>{#each sizes as option (option)}<option value={option}>{option === 'auto' ? '자동' : option.replace('x', ' × ')}</option>{/each}</SelectInput></Field>
						<Field label="품질" for="studio-quality"><SelectInput id="studio-quality" bind:value={quality} disabled={busy || capabilitiesLoading}>{#each qualities as option (option)}<option value={option}>{option}</option>{/each}</SelectInput></Field>
						<Field label="이미지 수" for="studio-count"><SelectInput id="studio-count" bind:value={count} disabled={busy || capabilitiesLoading}>{#each Array.from({ length: maxCount }, (_, index) => index + 1) as option (option)}<option value={String(option)}>{option}</option>{/each}</SelectInput></Field>
					</div>
					{#if editMode}<Field label="수정할 이미지" for="studio-file" help="PNG, JPEG 또는 WebP · 업로드 후 소유권과 검사를 거쳐 사용합니다."><input id="studio-file" type="file" accept="image/png,image/jpeg,image/webp" onchange={selectFile} disabled={busy} class="file-input" /></Field>{#if uploading}<p role="status">입력 이미지를 업로드하는 중…</p>{:else if editAssetId}<p role="status" class="muted">업로드 완료: {editFileName}</p>{/if}{/if}
					<Button type="submit" disabled={!scope || Boolean(readiness) || modelsLoading || capabilitiesLoading || !variantReady || busy || !prompt.trim() || (editMode && !editAssetId)}>{submitting ? '요청 중…' : editMode ? '이미지 수정 시작' : '이미지 생성 시작'}</Button>
				</form>
			</Card>
			<section class="results" aria-label="이미지 결과">
				<Card>
					<h2>이 브라우저의 작업</h2>
					{#if runIds.length === 0}<p class="muted">아직 시작한 이미지 작업이 없습니다.</p>{:else}<div class="history">{#each runIds as id, index (id)}<Button variant={selectedRunId === id ? 'accent' : 'secondary'} ariaPressed={selectedRunId === id} onclick={() => scope && selectRun(id, scope)}>작업 {runIds.length - index} · {id.slice(0, 8)}</Button>{/each}</div>{/if}
				</Card>
				{#if selectedRunId}<Card><div class="result-head"><h2>작업 결과</h2>{#if currentRun}<span role="status">{displayStatus(currentRun.status)}</span>{/if}</div>
					{#if loadingRun && !currentRun}<p role="status">작업 상태를 확인하는 중…</p>{/if}
					{#if currentRun && !currentRun.terminal}<p role="status">서버에서 이미지를 처리 중입니다. 이 페이지를 떠나도 작업은 계속됩니다.</p><Button variant="danger-outline" onclick={cancel}>작업 취소</Button>{/if}
					{#if currentRun?.status === 'failed'}<Alert tone="danger" title="이미지 작업 실패">실행이 실패했습니다. 다시 시도하거나 모델 설정을 확인하세요.</Alert>{/if}
					{#if currentRun?.status === 'canceled'}<Alert tone="neutral">작업이 취소되었습니다.</Alert>{/if}
					{#if currentRun?.status === 'completed'}{#if currentRun.output_assets?.length}<div class="gallery">{#each currentRun.output_assets as asset (asset.asset_id)}<figure><div class="image-frame">{#if previewUrls[asset.asset_id]}<img src={previewUrls[asset.asset_id]} alt="생성된 이미지" />{:else}<span>이미지 불러오는 중…</span>{/if}</div><figcaption><span>이미지 · {asset.mime_type}</span><Button variant="secondary" onclick={() => download(asset.asset_id, `image-${asset.asset_id}.${asset.mime_type.split('/')[1] ?? 'png'}`)}>다운로드</Button></figcaption></figure>{/each}</div>{:else}<Alert tone="warning">작업은 완료됐지만 출력 이미지가 없습니다.</Alert>{/if}{/if}
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
