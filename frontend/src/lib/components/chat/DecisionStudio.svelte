<script lang="ts">
	import { onDestroy, tick, untrack } from 'svelte';
	import { auth, authReady, projectSwitching } from '$lib/stores/auth';
	import { sessionScopeKey } from '$lib/utils/authSession';
	import { serviceCapabilities, serviceDenials } from '$lib/stores/servicePermissions';
	import { ApiError } from '$lib/api/client';
	import {
		decisionStudioApi, decisionReadiness, validateDecisionRequest, parseDecisionJson, validateDecisionImage,
		MAX_DECISION_IMAGE_BYTES, DECISION_IMAGE_TYPES,
		type DecisionModel, type DecisionCapabilities, type DecisionResult, type DecisionRequest, type DecisionQuestion
	} from '$lib/api/decisionStudio';
	import { Alert, Button, Field, PageShell, SelectInput, TextareaInput, TextInput } from '$lib/components/ui';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import LumenPermissionNotice from './LumenPermissionNotice.svelte';
	import { t } from '$lib/i18n/ns/decision-studio';
	import { intlLocale } from '$lib/i18n/runtime.svelte';

	type OptionDraft = { id: number; value: string; description: string };
	type QuestionDraft = { id: number; type: 'predicate' | 'choice' | 'score'; name: string; instructions: string; options: OptionDraft[] };
	let nextId = 0;
	function newQuestion(): QuestionDraft {
		return { id: nextId++, type: 'predicate', name: '', instructions: '', options: [
			{ id: nextId++, value: '', description: '' }, { id: nextId++, value: '', description: '' }
		] };
	}
	let questions = $state<QuestionDraft[]>([newQuestion()]);
	let models = $state<DecisionModel[]>([]);
	let selected = $state('');
	let verified = $state<DecisionCapabilities | null>(null);
	let inputType = $state<'text' | 'json' | 'image' | 'file'>('text');
	let content = $state('');
	let imageDetail = $state<'auto' | 'low' | 'high' | 'original'>('auto');
	let fileData = $state('');
	let fileName = $state('');
	let fileReading = $state(false);
	let loading = $state(false);
	let checking = $state(false);
	let busy = $state(false);
	let loadError = $state('');
	let failure = $state('');
	let status = $state('');
	let result = $state<DecisionResult | null>(null);
	let resultQuestions = $state<DecisionQuestion[]>([]);
	let activeOwner = $state('');
	let generation = $state(0);
	let fileGeneration = 0;
	let reader: FileReader | null = null;
	let modelRequest: AbortController | null = null;
	let capabilityRequest: AbortController | null = null;
	let decisionRequest: AbortController | null = null;
	let errorSummary = $state<HTMLDivElement>();
	const scope = $derived($authReady && !$projectSwitching && $auth.token && $auth.projectId && $auth.userId
		? { token: $auth.token, projectId: $auth.projectId } : null);
	const allowed = $derived(Boolean(scope) && $serviceCapabilities('lumen-chat_user'));
	const model = $derived(models.find((entry) => String(entry.id) === selected));
	const readiness = $derived(decisionReadiness(model, verified));
	const canRun = $derived(allowed && !loading && !checking && !busy && !fileReading && !loadError && !readiness);

	function message(cause: unknown): string {
		if (cause instanceof ApiError) {
			if (cause.status === 401 || cause.status === 403) return t('decisions.projectDenied');
			if (cause.status === 402) return t('decisions.quotaInsufficient');
			return t('decisions.requestFailed', { status: cause.status });
		}
		return cause instanceof Error ? cause.message : t('decisions.connectionFailed');
	}
	function cancel(announce = true) {
		decisionRequest?.abort(); decisionRequest = null; busy = false;
		if (announce) status = t('decisions.cancelled');
	}
	function stopFileRead() {
		fileGeneration++;
		const pending = reader; reader = null;
		if (pending && pending.readyState === FileReader.LOADING) pending.abort();
		fileReading = false;
	}
	function reset() {
		generation++;
		modelRequest?.abort(); capabilityRequest?.abort(); cancel(false); stopFileRead();
		modelRequest = null; capabilityRequest = null;
		models = []; selected = ''; verified = null; questions = [newQuestion()];
		content = ''; inputType = 'text'; imageDetail = 'auto'; fileData = ''; fileName = '';
		loading = false; checking = false; loadError = ''; failure = ''; status = ''; result = null; resultQuestions = [];
	}
	// Synchronous subscriptions invalidate A→B→A ownership and authority before promise callbacks.
	const unsubscribers = [
		auth.subscribe((value) => untrack(() => {
			const owner = sessionScopeKey(value);
			if (owner !== activeOwner || !value.token) { reset(); activeOwner = owner; }
		})),
		authReady.subscribe((ready) => { if (!ready) untrack(reset); }),
		projectSwitching.subscribe((switching) => { if (switching) untrack(reset); }),
		serviceCapabilities.subscribe((grants) => { if (!grants('lumen-chat_user')) untrack(reset); }),
		serviceDenials.subscribe((denied) => { if (denied('lumen-chat_user')) untrack(reset); })
	];
	async function loadModels() {
		if (!allowed || !scope) return;
		modelRequest?.abort(); capabilityRequest?.abort(); cancel(false);
		capabilityRequest = null; checking = false;
		const request = new AbortController(); modelRequest = request;
		const epoch = generation, owner = activeOwner, requestScope = scope;
		loading = true; loadError = ''; selected = ''; verified = null; models = []; result = null;
		try {
			const list = await decisionStudioApi.models(requestScope, request.signal);
			if (request.signal.aborted || modelRequest !== request || epoch !== generation || owner !== activeOwner || !allowed) return;
			models = list; selected = list[0] ? String(list[0].id) : '';
		} catch (cause) {
			if (!request.signal.aborted && modelRequest === request && epoch === generation && owner === activeOwner && allowed) loadError = message(cause);
		} finally {
			if (modelRequest === request) { modelRequest = null; loading = false; }
		}
	}
	async function loadCapabilities(id: number) {
		if (!allowed || !scope) return;
		capabilityRequest?.abort(); cancel(false);
		const request = new AbortController(); capabilityRequest = request;
		const epoch = generation, owner = activeOwner, requestScope = scope;
		checking = true; verified = null; result = null;
		try {
			const value = await decisionStudioApi.capabilities(id, requestScope, request.signal);
			if (request.signal.aborted || capabilityRequest !== request || epoch !== generation || owner !== activeOwner || !allowed || selected !== String(id)) return;
			verified = value;
		} catch (cause) {
			if (!request.signal.aborted && capabilityRequest === request && epoch === generation && owner === activeOwner && allowed && selected === String(id)) loadError = message(cause);
		} finally {
			if (capabilityRequest === request) { capabilityRequest = null; checking = false; }
		}
	}
	$effect(() => {
		const owner = activeOwner, enabled = allowed, epoch = generation;
		untrack(() => { if (epoch === generation && owner && enabled && !models.length && !loading && !loadError) void loadModels(); });
	});
	$effect(() => {
		const id = selected, enabled = allowed;
		untrack(() => { if (enabled && id && verified?.model_id !== Number(id) && !checking && !loadError) void loadCapabilities(Number(id)); });
	});
	function selectModel(event: Event) {
		if (!allowed || busy) return;
		capabilityRequest?.abort(); capabilityRequest = null; checking = false; verified = null;
		stopFileRead(); selected = (event.currentTarget as HTMLSelectElement).value;
		loadError = ''; failure = ''; status = ''; result = null;
	}
	function selectInputType(event: Event) {
		if (!allowed || busy) return;
		stopFileRead(); inputType = (event.currentTarget as HTMLSelectElement).value as typeof inputType;
		content = ''; fileData = ''; fileName = ''; failure = '';
	}
	function readFile(event: Event) {
		if (!allowed || busy || inputType !== 'file') return;
		const element = event.currentTarget as HTMLInputElement, file = element.files?.[0];
		stopFileRead(); fileData = ''; fileName = ''; failure = '';
		if (!file) return;
		if (!(DECISION_IMAGE_TYPES as readonly string[]).includes(file.type) || file.size > MAX_DECISION_IMAGE_BYTES || !file.size) {
			failure = t('decisions.imageLimit'); element.value = ''; return;
		}
		const pending = new FileReader(); reader = pending;
		const epoch = generation, fileEpoch = fileGeneration, owner = activeOwner, modelId = selected;
		fileReading = true;
		const current = () => reader === pending && epoch === generation && fileEpoch === fileGeneration && owner === activeOwner
			&& allowed && inputType === 'file' && selected === modelId;
		pending.onload = () => {
			if (!current()) return;
			try {
				if (typeof pending.result !== 'string') throw new Error(t('decisions.invalidImage'));
				validateDecisionImage(pending.result); fileData = pending.result; fileName = file.name;
			} catch (cause) { failure = message(cause); }
			reader = null; fileReading = false;
		};
		pending.onerror = () => { if (current()) { failure = t('decisions.invalidImage'); reader = null; fileReading = false; } };
		pending.onabort = () => { if (current()) { reader = null; fileReading = false; } };
		pending.readAsDataURL(file);
	}
	function addQuestion() {
		if (!allowed || busy || questions.length >= 400) return;
		const question = newQuestion(), epoch = generation;
		questions = [...questions, question];
		void tick().then(() => { if (allowed && epoch === generation && questions.some((entry) => entry.id === question.id)) document.getElementById(`decision-instructions-${question.id}`)?.focus(); });
	}
	function removeQuestion(id: number) {
		if (!allowed || busy || questions.length <= 1) return;
		const index = questions.findIndex((entry) => entry.id === id), epoch = generation;
		questions = questions.filter((entry) => entry.id !== id);
		const next = questions[Math.min(index, questions.length - 1)].id;
		void tick().then(() => { if (allowed && epoch === generation) document.getElementById(`decision-instructions-${next}`)?.focus(); });
	}
	function addOption(question: QuestionDraft) {
		if (!allowed || busy || question.options.length >= (question.type === 'choice' ? 255 : 10)) return;
		question.options = [...question.options, { id: nextId++, value: '', description: '' }];
	}
	function removeOption(question: QuestionDraft, id: number) {
		if (!allowed || busy || question.options.length <= 2) return;
		question.options = question.options.filter((entry) => entry.id !== id);
	}
	function changeQuestionType(question: QuestionDraft, event: Event) {
		if (!allowed || busy) return;
		question.type = (event.currentTarget as HTMLSelectElement).value as QuestionDraft['type'];
		question.options = [{ id: nextId++, value: '', description: '' }, { id: nextId++, value: '', description: '' }];
		failure = '';
	}
	async function decide() {
		if (!canRun || !scope || !model) return;
		let payload: DecisionRequest;
		try {
			const input: DecisionRequest['input'] = inputType === 'text' ? content : [{ role: 'user', content: inputType === 'json'
				? [{ type: 'input_json', data: parseDecisionJson(content) }]
				: [{ type: 'input_image', image_url: inputType === 'file' ? fileData : content.trim(), detail: imageDetail }] }];
			const built = questions.map((question): DecisionQuestion => {
				const base = { instructions: question.instructions, ...(question.name.trim() ? { name: question.name.trim() } : {}) };
				if (question.type === 'choice') return { ...base, type: 'choice', choices: question.options.map((entry) => ({ value: entry.value, description: entry.description })) };
				if (question.type === 'score') return { ...base, type: 'score', levels: question.options.map((entry) => ({ label: entry.value, description: entry.description })) };
				return { ...base, type: 'predicate' };
			});
			payload = { model: model.model_name, input, questions: built };
			validateDecisionRequest(payload);
		} catch (cause) {
			failure = message(cause); await tick(); errorSummary?.focus(); return;
		}
		const request = new AbortController(); decisionRequest = request;
		const epoch = generation, owner = activeOwner, requestScope = scope;
		busy = true; failure = ''; status = ''; result = null; resultQuestions = [];
		try {
			const value = await decisionStudioApi.decide(payload, requestScope, request.signal);
			if (request.signal.aborted || decisionRequest !== request || epoch !== generation || owner !== activeOwner || !allowed) return;
			result = value; resultQuestions = payload.questions;
		} catch (cause) {
			if (!request.signal.aborted && decisionRequest === request && epoch === generation && owner === activeOwner && allowed) failure = message(cause);
		} finally {
			if (decisionRequest === request) { decisionRequest = null; busy = false; }
		}
	}
	onDestroy(() => { unsubscribers.forEach((unsubscribe) => unsubscribe()); reset(); });
</script>

<svelte:head><title>{t('decisions.title')}</title></svelte:head>
<PageShell>
	<LumenPermissionNotice leaves={['lumen-chat_user']} />
	<div class="studio" data-testid="decision-studio">
		<header class="header">
			<div><h1 id="decision-title">{t('decisions.title')}</h1><p class="muted">{t('decisions.description')}</p></div>
			<Button href="/dashboard/chat" variant="secondary">{t('decisions.textChat')}</Button>
		</header>
		<form class="workspace" aria-labelledby="decision-title" onsubmit={(event) => { event.preventDefault(); void decide(); }}>
			<section class="settings" aria-label={t('decisions.model')}>
				<Field label={t('decisions.model')} for="decision-model"><SelectInput id="decision-model" value={selected} onchange={selectModel} disabled={!allowed || loading || busy}><option value="">{t('decisions.selectModel')}</option>{#each models as item (item.id)}<option value={String(item.id)}>{item.display_name}</option>{/each}</SelectInput></Field>
				{#if allowed}
					{#if loading || checking}<LoadingState variant="inline" label={t('decisions.checking')} />
					{:else if loadError}<Alert tone="danger">{loadError}<Button variant="subtle" onclick={() => void loadModels()}>{t('decisions.reload')}</Button></Alert>
					{:else if !models.length}<Alert tone="warning">{t('decisions.noModels')}</Alert>
					{:else if readiness}<Alert tone="warning">{readiness}</Alert>
					{:else}<p role="status" class="muted">{t('decisions.ready')}</p>{/if}
				{/if}
			</section>
			<fieldset disabled={!allowed || busy} class="input-section">
				<legend>{t('decisions.input')}</legend>
				<Field label={t('decisions.inputType')} for="decision-input-type"><SelectInput id="decision-input-type" value={inputType} onchange={selectInputType}><option value="text">{t('decisions.text')}</option><option value="json">{t('decisions.json')}</option><option value="image">{t('decisions.image')}</option><option value="file">{t('decisions.file')}</option></SelectInput></Field>
				{#if inputType === 'text' || inputType === 'json'}
					<Field label={t('decisions.content')} for="decision-content" required><TextareaInput id="decision-content" bind:value={content} rows={5} required /></Field>
				{:else if inputType === 'image'}
					<Field label={t('decisions.imageUrl')} for="decision-image-url" required><TextInput id="decision-image-url" bind:value={content} required /></Field>
				{:else}
					<Field label={t('decisions.file')} for="decision-file" required><input id="decision-file" name="decision-file" type="file" accept={DECISION_IMAGE_TYPES.join(',')} onchange={readFile} aria-describedby="decision-image-help" required /></Field>
					{#if fileReading}<p role="status" class="muted">{t('decisions.fileReading')}</p>{:else if fileName}<p class="muted">{fileName}</p>{/if}
				{/if}
				{#if inputType === 'image' || inputType === 'file'}
					<Field label={t('decisions.imageDetail')} for="decision-image-detail"><SelectInput id="decision-image-detail" bind:value={imageDetail}><option value="auto">auto</option><option value="low">low</option><option value="high">high</option><option value="original">original</option></SelectInput></Field>
				{/if}
				<p id="decision-image-help" class="muted">{t('decisions.imageHelp')}</p>
			</fieldset>
			<section class="questions" aria-labelledby="decision-questions-heading">
				<h2 id="decision-questions-heading">{t('decisions.questions')}</h2>
				{#each questions as question, index (question.id)}
					<fieldset class="question" disabled={!allowed || busy} data-testid="decision-question">
						<legend>{t('decisions.question', { number: index + 1 })}</legend>
						<div class="question-meta">
							<Field label={t('decisions.type')} for={`decision-type-${question.id}`}><SelectInput id={`decision-type-${question.id}`} value={question.type} onchange={(event) => changeQuestionType(question, event)}><option value="predicate">{t('decisions.predicate')}</option><option value="choice">{t('decisions.choice')}</option><option value="score">{t('decisions.score')}</option></SelectInput></Field>
							<Field label={t('decisions.name')} for={`decision-name-${question.id}`} help={t('decisions.optionalName')}><TextInput id={`decision-name-${question.id}`} bind:value={question.name} /></Field>
						</div>
						<Field label={t('decisions.instructions')} for={`decision-instructions-${question.id}`} required><TextareaInput id={`decision-instructions-${question.id}`} bind:value={question.instructions} required rows={2} /></Field>
						{#if question.type !== 'predicate'}
							<fieldset class="options"><legend>{t(question.type === 'choice' ? 'decisions.choices' : 'decisions.levels')}</legend>
								{#each question.options as option, optionIndex (option.id)}
									<div class="option-row">
										<Field label={`${t(question.type === 'choice' ? 'decisions.value' : 'decisions.label')} ${optionIndex + 1}`} for={`decision-value-${option.id}`} required><TextInput id={`decision-value-${option.id}`} bind:value={option.value} required /></Field>
										<Field label={`${t('decisions.descriptionLabel')} ${optionIndex + 1}`} for={`decision-description-${option.id}`} required><TextInput id={`decision-description-${option.id}`} bind:value={option.description} required /></Field>
										<Button variant="ghost" disabled={question.options.length <= 2} onclick={() => removeOption(question, option.id)}>{t(question.type === 'choice' ? 'decisions.removeChoice' : 'decisions.removeLevel', { number: optionIndex + 1 })}</Button>
									</div>
								{/each}
								<Button variant="outline" disabled={question.options.length >= (question.type === 'choice' ? 255 : 10)} onclick={() => addOption(question)}>{t(question.type === 'choice' ? 'decisions.addChoice' : 'decisions.addLevel')}</Button>
							</fieldset>
						{/if}
						<div class="remove-row"><Button variant="ghost" disabled={questions.length <= 1} onclick={() => removeQuestion(question.id)}>{t('decisions.removeQuestion', { number: index + 1 })}</Button></div>
					</fieldset>
				{/each}
				<Button variant="outline" disabled={!allowed || busy || questions.length >= 400} onclick={addQuestion}>{t('decisions.addQuestion')}</Button>
			</section>
			<div class="submit-row">
				<p class="muted">{t('decisions.cancelHelp')}</p>
				<div class="actions">{#if busy}<Button variant="secondary" onclick={() => cancel()}>{t('decisions.cancel')}</Button>{/if}<Button type="submit" disabled={!canRun}>{#if busy}<LoadingState variant="control" label={t('decisions.running')} />{:else}{t('decisions.run')}{/if}</Button></div>
			</div>
		</form>
		{#if allowed && failure}<div bind:this={errorSummary} tabindex="-1" class="error-summary"><Alert tone="danger">{failure}</Alert></div>{/if}
		{#if status}<p role="status" class="muted">{status}</p>{/if}
		{#if allowed && result}
			<section class="results" aria-labelledby="decision-answers-heading" data-testid="decision-results">
				<h2 id="decision-answers-heading">{t('decisions.answers')}</h2>
				{#each result.answers as answer, index}
					<section class="answer" aria-label={answer.name ?? t('decisions.question', { number: index + 1 })}>
						<h3>{answer.name ?? t('decisions.question', { number: index + 1 })}</h3>
						{#if typeof resultQuestions[index]?.instructions === 'string'}<p class="muted">{resultQuestions[index].instructions}</p>{/if}
						{#if answer.type === 'refusal'}<Alert tone="warning" flat>{t('decisions.refusal')}</Alert>
						{:else if answer.type === 'predicate'}<p>{t('decisions.probability')}: {answer.probability.toLocaleString(intlLocale(), { style: 'percent', maximumFractionDigits: 2 })}</p>
						{:else}
							<p>{t(answer.type === 'choice' ? 'decisions.choice' : 'decisions.score')}: {String(answer.type === 'choice' ? answer.choice : answer.score)}</p>
							<p>{t('decisions.confidence')}: {answer.confidence.toLocaleString(intlLocale(), { style: 'percent', maximumFractionDigits: 2 })}</p>
							<dl class="probabilities" aria-label={t('decisions.probability')}>{#each answer.probabilities as entry}<div><dt>{'label' in entry ? entry.label : String(entry.value)}</dt><dd>{entry.probability.toLocaleString(intlLocale(), { style: 'percent', maximumFractionDigits: 2 })}</dd></div>{/each}</dl>
						{/if}
					</section>
				{/each}
				<h2>{t('decisions.usage')}</h2>
				<dl class="usage">
					<div><dt>{t('decisions.inputTokens')}</dt><dd>{result.usage.input_tokens.toLocaleString(intlLocale())}</dd></div>
					<div><dt>{t('decisions.cachedTokens')}</dt><dd>{result.usage.input_tokens_details.cached_tokens.toLocaleString(intlLocale())}</dd></div>
					<div><dt>{t('decisions.cacheWriteTokens')}</dt><dd>{result.usage.input_tokens_details.cache_write_tokens.toLocaleString(intlLocale())}</dd></div>
					<div><dt>{t('decisions.outputTokens')}</dt><dd>{result.usage.output_tokens.toLocaleString(intlLocale())}</dd></div>
					<div><dt>{t('decisions.reasoningTokens')}</dt><dd>{result.usage.output_tokens_details.reasoning_tokens.toLocaleString(intlLocale())}</dd></div>
					<div><dt>{t('decisions.totalTokens')}</dt><dd>{result.usage.total_tokens.toLocaleString(intlLocale())}</dd></div>
					<div><dt>{t('decisions.cost')}</dt><dd>{result.cost_usd.toLocaleString(intlLocale(), { maximumFractionDigits: 10 })}</dd></div>
					<div><dt>{t('decisions.creditedCost')}</dt><dd>{result.credited_cost.toLocaleString(intlLocale(), { maximumFractionDigits: 10 })}</dd></div>
					<div><dt>{t('decisions.usageLog')}</dt><dd class="identifier">{result.usage_log_id}</dd></div>
				</dl>
			</section>
		{:else if !busy}<p class="muted">{t('decisions.emptyResults')}</p>{/if}
	</div>
</PageShell>

<style>
	.studio { display: grid; gap: 1.5rem; min-width: 0; }
	.header, .actions, .submit-row { display: flex; align-items: center; justify-content: space-between; gap: 0.75rem; flex-wrap: wrap; }
	h1 { font-size: var(--type-console-title); font-weight: 600; }
	h2, h3, legend { font-size: var(--type-body); font-weight: 600; color: var(--color-ink-0); }
	p { margin: 0; overflow-wrap: anywhere; }
	.muted { color: var(--color-ink-2); font-size: var(--type-support); }
	.workspace { display: grid; gap: 1.5rem; min-width: 0; padding: 1.25rem; border: 1px solid var(--color-line); border-radius: var(--radius-lg); background: var(--color-surface-base); }
	fieldset { min-width: 0; border: 0; padding: 0; margin: 0; }
	legend { margin-block-end: 0.75rem; }
	.settings, .input-section, .questions, .question, .options, .results { display: grid; gap: 1rem; min-width: 0; }
	.settings { align-items: end; }
	.question { padding-block: 1rem; border-block-start: 1px solid var(--color-line); }
	.question-meta, .option-row { display: grid; gap: 0.75rem; min-width: 0; }
	.option-row { align-items: end; }
	.remove-row { display: flex; justify-content: end; }
	.submit-row { padding-block-start: 1rem; border-block-start: 1px solid var(--color-line); }
	.submit-row > p { flex: 1 1 20rem; }
	.actions { margin-inline-start: auto; }
	.answer { display: grid; gap: 0.5rem; padding-block: 1rem; border-block-start: 1px solid var(--color-line); }
	.probabilities, .usage { display: grid; gap: 0.5rem; min-width: 0; }
	.probabilities > div, .usage > div { display: flex; justify-content: space-between; gap: 1rem; }
	dd { text-align: end; font-variant-numeric: tabular-nums; overflow-wrap: anywhere; min-width: 0; }
	dt { color: var(--color-ink-2); }
	.identifier { font-family: var(--font-mono); font-size: var(--type-identifier); }
	input[type='file'] { max-width: 100%; min-height: var(--control-touch-height); font: inherit; color: var(--color-ink-1); border: 1px solid var(--color-line-2); border-radius: var(--radius-md); background: var(--color-surface-input); padding: 0.5rem; }
	input[type='file']:focus-visible, .error-summary:focus-visible { outline: none; box-shadow: var(--focus-ring); }
	@media (min-width: 768px) { .settings, .question-meta { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); } .option-row { grid-template-columns: minmax(0, 1fr) minmax(0, 2fr) auto; } }
</style>
