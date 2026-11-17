<script lang="ts">
	import { onDestroy, tick, untrack } from 'svelte';
	import { auth, authReady, projectSwitching } from '$lib/stores/auth';
	import { sessionScopeKey } from '$lib/utils/authSession';
	import { serviceCapabilities, serviceDenials } from '$lib/stores/servicePermissions';
	import { ApiError } from '$lib/api/client';
	import { embeddingStudioApi, embeddingReadiness, cosineMatrix, vectorNorm, type EmbeddingModel, type EmbeddingCapabilities, type EmbeddingResult } from '$lib/api/embeddingStudio';
	import { Alert, Button, CompactResourceCard, Field, PageShell, ResponsiveTable, SelectInput, TextareaInput, TextInput, TableShell } from '$lib/components/ui';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import LumenPermissionNotice from './LumenPermissionNotice.svelte';
	import { t } from '$lib/i18n/ns/chat-studio';
	import { intlLocale } from '$lib/i18n/runtime.svelte';

	let models = $state<EmbeddingModel[]>([]);
	let selected = $state('');
	let capabilities = $state<EmbeddingCapabilities | null>(null);
	let rows = $state([{ id: 0, text: '' }]);
	let nextRow = 1;
	let dimensions = $state('');
	let dimensionBadInput = $state(false);
	let loading = $state(false);
	let checking = $state(false);
	let busy = $state(false);
	let loadError = $state('');
	let failure = $state('');
	let status = $state('');
	let result = $state<EmbeddingResult | null>(null);
	let resultInputs = $state<string[]>([]);
	let resultUrl = $state('');
	let activeOwner = $state('');
	let generation = 0;
	let modelRequest: AbortController | null = null;
	let capabilityRequest: AbortController | null = null;
	let embeddingRequest: AbortController | null = null;
	const scope = $derived($authReady && !$projectSwitching && $auth.token && $auth.projectId && $auth.userId ? { token: $auth.token, projectId: $auth.projectId } : null);
	const allowed = $derived(Boolean(scope) && $serviceCapabilities('lumen-chat_user'));
	const model = $derived(models.find((item) => String(item.id) === selected));
	const readiness = $derived(embeddingReadiness(model, capabilities));
	const maxInputs = $derived(capabilities?.max_inputs ?? 16);
	const parsedDimensions = $derived(dimensions.trim() ? Number(dimensions) : undefined);
	const dimensionError = $derived(capabilities?.supports_dimensions && (dimensionBadInput || (parsedDimensions !== undefined && (
		!Number.isSafeInteger(parsedDimensions) || parsedDimensions < (capabilities.min_dimensions ?? 1)
		|| (capabilities.max_dimensions !== null && parsedDimensions > capabilities.max_dimensions)
	))) ? t('embeddingStudio.dimensionInvalid') : '');
	const ready = $derived(allowed && !loading && !checking && !busy && !loadError && !readiness && !dimensionError
		&& rows.length >= 1 && rows.length <= maxInputs && rows.every((row) => Boolean(row.text.trim())));
	const matrix = $derived(result ? cosineMatrix(result) : []);
	const resultJson = $derived(result ? JSON.stringify(result, null, 2) : '');

	function message(cause: unknown): string {
		if (cause instanceof ApiError) {
			if (cause.status === 401 || cause.status === 403) return t('embeddingStudio.projectDenied');
			if (cause.status === 402) return t('embeddingStudio.quotaInsufficient');
			if ([400, 409, 422].includes(cause.status)) return cause.message.slice(0, 250);
			return t('embeddingStudio.requestFailed', { status: cause.status });
		}
		return cause instanceof Error ? cause.message : t('embeddingStudio.connectionFailed');
	}
	function clearResult() {
		if (resultUrl) URL.revokeObjectURL(resultUrl);
		resultUrl = ''; result = null; resultInputs = []; status = '';
	}
	function cancel(announce = true) {
		embeddingRequest?.abort(); embeddingRequest = null; busy = false;
		if (announce) status = t('embeddingStudio.cancelled');
	}
	function reset() {
		generation++;
		modelRequest?.abort(); capabilityRequest?.abort(); cancel(false);
		modelRequest = null; capabilityRequest = null;
		clearResult(); models = []; selected = ''; capabilities = null;
		rows = [{ id: nextRow++, text: '' }]; dimensions = ''; dimensionBadInput = false;
		loading = false; checking = false; loadError = ''; failure = '';
	}
	// Store subscriptions fence same-tick owner ABA transitions before effects or promises run.
	const unsubscribers = [
		auth.subscribe((value) => untrack(() => {
			const next = sessionScopeKey(value);
			if (next !== activeOwner) { reset(); activeOwner = next; }
		})),
		authReady.subscribe((value) => { if (!value) untrack(reset); }),
		projectSwitching.subscribe((value) => { if (value) untrack(reset); }),
		serviceDenials.subscribe((denied) => { if (denied('lumen-chat_user')) untrack(reset); }),
		serviceCapabilities.subscribe((granted) => { if (!granted('lumen-chat_user')) untrack(() => cancel(false)); })
	];
	async function loadModels() {
		if (!allowed || !scope) return;
		modelRequest?.abort(); capabilityRequest?.abort(); cancel(false);
		const request = new AbortController(); modelRequest = request;
		const epoch = generation, owner = activeOwner, requestScope = scope;
		loading = true; loadError = ''; capabilities = null; selected = ''; clearResult();
		try {
			const list = await embeddingStudioApi.models(requestScope, request.signal);
			if (request.signal.aborted || epoch !== generation || owner !== activeOwner || !allowed) return;
			models = list; selected = list[0] ? String(list[0].id) : '';
		} catch (cause) {
			if (!request.signal.aborted && epoch === generation && owner === activeOwner && allowed) loadError = message(cause);
		} finally {
			if (modelRequest === request) { modelRequest = null; loading = false; }
		}
	}
	async function loadCapabilities(id: number) {
		if (!allowed || !scope) return;
		capabilityRequest?.abort(); cancel(false);
		const request = new AbortController(); capabilityRequest = request;
		const epoch = generation, owner = activeOwner, requestScope = scope;
		checking = true; capabilities = null; dimensions = ''; dimensionBadInput = false; loadError = ''; clearResult();
		try {
			const value = await embeddingStudioApi.capabilities(id, requestScope, request.signal);
			if (request.signal.aborted || capabilityRequest !== request || epoch !== generation || owner !== activeOwner || !allowed || selected !== String(id)) return;
			capabilities = value;
		} catch (cause) {
			if (!request.signal.aborted && capabilityRequest === request && epoch === generation && owner === activeOwner && allowed && selected === String(id)) loadError = message(cause);
		} finally {
			if (capabilityRequest === request) { capabilityRequest = null; checking = false; }
		}
	}
	$effect(() => {
		const owner = activeOwner, enabled = allowed;
		untrack(() => { if (owner && enabled && !models.length && !loading && !loadError) void loadModels(); });
	});
	$effect(() => {
		const id = selected, enabled = allowed;
		untrack(() => {
			if (enabled && id && capabilities?.model_id !== Number(id) && !checking) void loadCapabilities(Number(id));
		});
	});
	function selectModel(event: Event) {
		if (!allowed || busy) return;
		capabilityRequest?.abort(); capabilityRequest = null; checking = false;
		capabilities = null; selected = (event.currentTarget as HTMLSelectElement).value;
		dimensions = ''; dimensionBadInput = false; loadError = ''; failure = ''; clearResult();
	}
	async function embed() {
		if (!ready || !scope || !model || !capabilities) return;
		const request = new AbortController(); embeddingRequest = request;
		const epoch = generation, owner = activeOwner, requestScope = scope;
		const input = rows.map((row) => row.text);
		const payload = { model_id: model.id, input, ...(capabilities.supports_dimensions && parsedDimensions !== undefined ? { dimensions: parsedDimensions } : {}) };
		busy = true; failure = ''; clearResult();
		try {
			const value = await embeddingStudioApi.embed(payload, requestScope, request.signal);
			if (request.signal.aborted || embeddingRequest !== request || epoch !== generation || owner !== activeOwner || !allowed) return;
			result = value; resultInputs = input;
			resultUrl = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' }));
		} catch (cause) {
			if (!request.signal.aborted && embeddingRequest === request && epoch === generation && owner === activeOwner && allowed) failure = message(cause);
		} finally {
			if (embeddingRequest === request) { embeddingRequest = null; busy = false; }
		}
	}
	async function copy() {
		if (!allowed || !result) return;
		const snapshot = result, epoch = generation;
		try {
			await navigator.clipboard.writeText(resultJson);
			if (allowed && result === snapshot && epoch === generation) status = t('embeddingStudio.copied');
		} catch {
			if (allowed && result === snapshot && epoch === generation) status = t('embeddingStudio.copyFailed');
		}
	}
	function addInput() {
		if (!allowed || busy || rows.length >= maxInputs) return;
		const id = nextRow++;
		rows = [...rows, { id, text: '' }];
		void tick().then(() => {
			if (allowed && rows.some((row) => row.id === id)) document.getElementById(`embedding-input-${id}`)?.focus();
		});
	}
	function removeInput(id: number) {
		if (!allowed || busy || rows.length <= 1) return;
		const index = rows.findIndex((row) => row.id === id);
		rows = rows.filter((row) => row.id !== id);
		const focusId = rows[Math.min(index, rows.length - 1)].id;
		void tick().then(() => { if (allowed && rows.some((row) => row.id === focusId)) document.getElementById(`embedding-input-${focusId}`)?.focus(); });
	}
	onDestroy(() => { unsubscribers.forEach((unsubscribe) => unsubscribe()); reset(); });
</script>

<svelte:head><title>{t('embeddingStudio.title')}</title></svelte:head>
<PageShell>
	<LumenPermissionNotice leaves={['lumen-chat_user']} />
	<div class="studio">
		<header class="header">
			<div><h1>{t('embeddingStudio.title')}</h1><p class="muted">{t('embeddingStudio.description')}</p></div>
			<Button href="/dashboard/chat" variant="secondary">{t('audioStudio.textChat')}</Button>
		</header>
		<form class="workspace" onsubmit={(event) => { event.preventDefault(); void embed(); }}>
			<section class="inputs" aria-labelledby="embedding-inputs-heading">
				<h2 id="embedding-inputs-heading">{t('embeddingStudio.inputs')}</h2>
				<p class="muted">{t('embeddingStudio.inputHelp', { max: maxInputs })}</p>
				{#each rows as row, index (row.id)}
					<div class="input-row">
						<Field label={t('embeddingStudio.inputLabel', { number: index + 1 })} for={`embedding-input-${row.id}`}>
							<TextareaInput id={`embedding-input-${row.id}`} bind:value={row.text} rows={3} required disabled={!allowed || busy} placeholder={t('embeddingStudio.inputPlaceholder')} />
						</Field>
						<Button variant="ghost" disabled={!allowed || busy || rows.length <= 1} ariaLabel={t('embeddingStudio.removeInput', { number: index + 1 })} onclick={() => removeInput(row.id)}>{t('embeddingStudio.remove')}</Button>
					</div>
				{/each}
				<Button variant="outline" disabled={!allowed || busy || rows.length >= maxInputs} onclick={addInput}>{t('embeddingStudio.addInput')}</Button>
			</section>
			<aside class="settings" aria-labelledby="embedding-settings-heading">
				<h2 id="embedding-settings-heading">{t('embeddingStudio.settings')}</h2>
				<Field label={t('embeddingStudio.model')} for="embedding-model"><SelectInput id="embedding-model" value={selected} onchange={selectModel} disabled={!allowed || loading || busy}><option value="">{t('embeddingStudio.selectModel')}</option>{#each models as item (item.id)}<option value={String(item.id)}>{item.display_name}</option>{/each}</SelectInput></Field>
				{#if allowed}
					{#if loading || checking}<LoadingState variant="inline" label={t('embeddingStudio.checking')} />
					{:else if loadError}<Alert tone="danger">{loadError}<Button variant="subtle" onclick={() => void loadModels()}>{t('embeddingStudio.reload')}</Button></Alert>
					{:else if !models.length}<Alert tone="warning">{t('embeddingStudio.noModels')}</Alert>
					{:else if readiness}<Alert tone="warning">{readiness}</Alert>
					{:else}<p role="status" class="muted">{t('embeddingStudio.ready')}</p>{/if}
				{/if}
				{#if allowed && capabilities?.supports_dimensions}
					<Field label={t('embeddingStudio.dimensions')} for="embedding-dimensions" error={dimensionError} help={t('embeddingStudio.dimensionHelp', { min: capabilities.min_dimensions ?? 1, max: capabilities.max_dimensions ?? t('embeddingStudio.noMaximum'), default: capabilities.default_dimensions ?? t('embeddingStudio.providerDefault') })}>
						<TextInput id="embedding-dimensions" type="number" value={dimensions} oninput={(event) => { const input = event.currentTarget as HTMLInputElement; dimensions = input.value; dimensionBadInput = input.validity.badInput; }} min={capabilities.min_dimensions ?? 1} max={capabilities.max_dimensions ?? undefined} step={1} placeholder={capabilities.default_dimensions === null ? t('embeddingStudio.providerDefault') : String(capabilities.default_dimensions)} disabled={!allowed || busy} ariaInvalid={Boolean(dimensionError)} />
					</Field>
				{/if}
				{#if allowed && capabilities?.max_input_tokens}<p class="muted">{t('embeddingStudio.tokenLimit', { count: capabilities.max_input_tokens })}</p>{/if}
			</aside>
			<div class="submit-row">
				<p class="muted">{t('embeddingStudio.cancelHelp')}</p>
				<div class="actions">{#if busy}<Button variant="secondary" onclick={() => cancel()}>{t('embeddingStudio.cancel')}</Button>{/if}<Button type="submit" disabled={!ready}>{#if busy}<LoadingState variant="control" label={t('embeddingStudio.embedding')} />{:else}{t('embeddingStudio.embed')}{/if}</Button></div>
			</div>
		</form>
		{#if allowed && failure}<Alert tone="danger">{failure}</Alert>{/if}
		{#if status}<p role="status" class="muted">{status}</p>{/if}
		{#if allowed && result}
			<section class="results" aria-labelledby="embedding-results-heading">
				<div class="header"><h2 id="embedding-results-heading">{t('embeddingStudio.results')}</h2><div class="actions"><Button variant="secondary" onclick={() => void copy()}>{t('embeddingStudio.copyJson')}</Button><a class="download" href={resultUrl} download="embeddings.json">{t('embeddingStudio.downloadJson')}</a></div></div>
				<p class="muted">{result.model}</p>
				<p>{t('embeddingStudio.usage', { prompt: result.usage.prompt_tokens.toLocaleString(intlLocale()), total: result.usage.total_tokens.toLocaleString(intlLocale()), cost: result.credited_cost.toLocaleString(intlLocale(), { maximumFractionDigits: 12 }) })}{#if result.usage.estimated} <span class="muted">{t('embeddingStudio.estimated')}</span>{/if}</p>
				{#each result.embeddings as entry (entry.index)}
					<article class="vector"><h3>{t('embeddingStudio.inputLabel', { number: entry.index + 1 })}</h3><p class="input-text">{resultInputs[entry.index]}</p><p>{t('embeddingStudio.vectorStats', { length: entry.embedding.length, norm: vectorNorm(entry.embedding).toLocaleString(intlLocale(), { maximumSignificantDigits: 8 }) })}</p><p class="muted">{t('embeddingStudio.preview')}</p><pre>{JSON.stringify(entry.embedding.slice(0, 8))}</pre><details><summary>{t('embeddingStudio.fullVector')}</summary><pre>{JSON.stringify(entry, null, 2)}</pre></details></article>
				{/each}
				{#if result.embeddings.length >= 2}
					<h3 id="embedding-matrix-heading">{t('embeddingStudio.similarity')}</h3><p class="muted">{t('embeddingStudio.similarityHelp')}</p>
					<ResponsiveTable>
						{#snippet cards()}
							{#each matrix as values, index}
								<CompactResourceCard>
									<h3>{t('embeddingStudio.inputLabel', { number: index + 1 })}</h3>
									<dl class="similarities">{#each values as value, column}<div><dt>{t('embeddingStudio.inputLabel', { number: column + 1 })}</dt><dd>{value === null ? t('embeddingStudio.undefinedSimilarity') : value.toLocaleString(intlLocale(), { minimumFractionDigits: 4, maximumFractionDigits: 4 })}</dd></div>{/each}</dl>
								</CompactResourceCard>
							{/each}
						{/snippet}
						<!-- Keep the overflow region keyboard-scrollable for the wide similarity matrix. -->
						<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
						<div class="matrix-region" role="region" aria-labelledby="embedding-matrix-heading" tabindex="0"><TableShell density="compact" stickyHeader><table><caption class="sr-only">{t('embeddingStudio.similarity')}</caption><thead><tr><th scope="col">{t('embeddingStudio.inputs')}</th>{#each result.embeddings as entry}<th scope="col">{t('embeddingStudio.inputLabel', { number: entry.index + 1 })}</th>{/each}</tr></thead><tbody>{#each matrix as values, index}<tr><th scope="row">{t('embeddingStudio.inputLabel', { number: index + 1 })}</th>{#each values as value}<td>{value === null ? t('embeddingStudio.undefinedSimilarity') : value.toLocaleString(intlLocale(), { minimumFractionDigits: 4, maximumFractionDigits: 4 })}</td>{/each}</tr>{/each}</tbody></table></TableShell></div>
					</ResponsiveTable>
				{/if}
				<details><summary>{t('embeddingStudio.fullResponse')}</summary><pre>{resultJson}</pre></details>
			</section>
		{:else if !busy}<p class="muted">{t('embeddingStudio.emptyResults')}</p>{/if}
	</div>
</PageShell>

<style>
	.studio { display: grid; gap: 1.5rem; min-width: 0; }
	.header, .actions, .submit-row { display: flex; align-items: center; justify-content: space-between; gap: 0.75rem; flex-wrap: wrap; }
	h1 { font-size: var(--type-console-title); font-weight: 600; }
	h2, h3 { font-size: var(--type-body); font-weight: 600; color: var(--color-ink-0); }
	p { margin: 0; overflow-wrap: anywhere; }
	.muted { color: var(--color-ink-2); font-size: var(--type-support); }
	.workspace { display: grid; grid-template-columns: minmax(0, 1fr); border: 1px solid var(--color-line); border-radius: var(--radius-lg); background: var(--color-surface-base); }
	.inputs, .settings, .results { display: grid; gap: 1rem; min-width: 0; padding: 1.25rem; }
	.settings { align-content: start; border-top: 1px solid var(--color-line); }
	.input-row { display: grid; gap: 0.5rem; min-width: 0; }
	.input-row :global(button) { justify-self: end; }
	.submit-row { padding: 1rem 1.25rem; border-top: 1px solid var(--color-line); }
	.results { padding: 0; }
	.vector { display: grid; gap: 0.5rem; padding-block: 1rem; border-top: 1px solid var(--color-line); min-width: 0; }
	.input-text { white-space: pre-wrap; }
	pre { font-family: var(--font-mono); font-size: var(--type-identifier); white-space: pre-wrap; overflow-wrap: anywhere; padding: 0.75rem; background: var(--color-surface-sunken); border-radius: var(--radius-md); max-height: 24rem; overflow: auto; }
	summary { cursor: pointer; min-height: var(--control-touch-height); display: list-item; align-content: center; color: var(--color-ink-1); font-size: var(--type-body); }
	summary:focus-visible, .matrix-region:focus-visible { outline: none; box-shadow: var(--focus-ring); }
	.matrix-region { min-width: 0; max-width: 100%; overflow: auto; border-radius: var(--radius-lg); }
	.matrix-region :global(tbody th) { position: sticky; inset-inline-start: 0; background: var(--color-surface-base); }
	.matrix-region :global(td) { text-align: right; white-space: nowrap; }
	.download { display: inline-flex; align-items: center; justify-content: center; min-height: var(--control-touch-height); padding: 0.375rem 0.75rem; border: 1px solid var(--color-line-2); border-radius: var(--radius-md); color: var(--color-ink-1); font-size: var(--type-body); }
	.download:hover { background: var(--color-surface-sunken); }
	.download:focus-visible { outline: none; box-shadow: var(--focus-ring); }
	.similarities { display: grid; gap: 0.5rem; }
	.similarities > div { display: flex; justify-content: space-between; gap: 0.75rem; }
	.similarities dd { font-variant-numeric: tabular-nums; text-align: right; }
	@media (min-width: 1024px) { .workspace { grid-template-columns: minmax(0, 1fr) minmax(15rem, 20rem); } .settings { border-top: 0; border-left: 1px solid var(--color-line); } .submit-row { grid-column: 1 / -1; } }
</style>
