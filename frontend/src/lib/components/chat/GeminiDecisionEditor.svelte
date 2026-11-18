<script lang="ts">
	import { tick } from 'svelte';
	import {
		GEMINI_DECISION_IMAGE_TYPES, GEMINI_DECISION_RESOLUTIONS, MAX_GEMINI_CRITERIA,
		MAX_GEMINI_DECISION_BYTES, MAX_GEMINI_QUESTIONS, geminiBase64Length, geminiImageType,
		type GeminiDecisionDraft, type GeminiQuestionDraft
	} from '$lib/api/decisionStudio';
	import { Alert, Button, Field, SelectInput, TextareaInput, TextInput } from '$lib/components/ui';
	import { t } from '$lib/i18n/ns/decision-studio';

	const resolutionLabels = {
		low: 'gemini.resolutionLow', medium: 'gemini.resolutionMedium',
		high: 'gemini.resolutionHigh', ultra_high: 'gemini.resolutionUltraHigh'
	} as const;

	let { draft = $bindable(), disabled, allocateId, invalidField, clearValidation }: {
		draft: GeminiDecisionDraft;
		disabled: boolean;
		allocateId: () => number;
		invalidField?: string;
		clearValidation: () => void;
	} = $props();
	let imageError = $state('');

	const describedByError = 'decision-error-summary';

	function addImages(event: Event) {
		if (disabled) return;
		const input = event.currentTarget as HTMLInputElement;
		const files = Array.from(input.files ?? []);
		input.value = '';
		if (!files.length) return;
		imageError = '';
		if (files.some((file) => !geminiImageType(file))) { imageError = t('gemini.invalidImage'); return; }
		const attachedBytes = draft.images.reduce((sum, { file }) => sum + geminiBase64Length(file), 0);
		if (files.reduce((sum, file) => sum + geminiBase64Length(file), attachedBytes) >= MAX_GEMINI_DECISION_BYTES) {
			imageError = t('gemini.requestLimit'); return;
		}
		for (const file of files) draft.images.push({ id: allocateId(), file, resolution: '' });
		clearValidation();
	}

	async function addQuestion() {
		if (disabled || draft.questions.length >= MAX_GEMINI_QUESTIONS) return;
		const id = allocateId();
		draft.questions.push({ id, key: '', type: 'noul', instructions: '', yes: '', no: '', rows: [] });
		await tick();
		if (!disabled) document.getElementById(`gemini-key-${id}`)?.focus();
	}

	async function removeQuestion(index: number) {
		if (disabled || draft.questions.length <= 1) return;
		draft.questions.splice(index, 1);
		clearValidation();
		const next = draft.questions[Math.min(index, draft.questions.length - 1)].id;
		await tick();
		if (!disabled) document.getElementById(`gemini-key-${next}`)?.focus();
	}

	function changeType(question: GeminiQuestionDraft, event: Event) {
		if (disabled) return;
		clearValidation();
		question.type = (event.currentTarget as HTMLSelectElement).value as GeminiQuestionDraft['type'];
		question.rows = question.type === 'noul' ? [] : [
			{ id: allocateId(), key: '', description: '' }, { id: allocateId(), key: '', description: '' }
		];
	}

	async function removeRow(question: GeminiQuestionDraft, rowIndex: number) {
		if (disabled || question.rows.length <= 2) return;
		question.rows.splice(rowIndex, 1);
		clearValidation();
		const next = question.rows[Math.min(rowIndex, question.rows.length - 1)].id;
		const field = question.type === 'choice' ? 'option' : 'description';
		await tick();
		if (!disabled) document.getElementById(`gemini-${field}-${next}`)?.focus();
	}
</script>

<fieldset class="fields" {disabled}>
	<legend>{t('decisions.input')}</legend>
	<Field label={t('decisions.text')} for="gemini-input-text">
		<TextareaInput id="gemini-input-text" bind:value={draft.text} rows={4} ariaInvalid={invalidField === 'gemini-input-text'} ariaDescribedBy={invalidField === 'gemini-input-text' ? describedByError : undefined} />
	</Field>
	<Field label={t('gemini.json')} for="gemini-input-json" help={t('gemini.jsonHelp')}>
		<TextareaInput id="gemini-input-json" bind:value={draft.json} rows={3} ariaInvalid={invalidField === 'gemini-input-json'} ariaDescribedBy={invalidField === 'gemini-input-json' ? `gemini-input-json-message ${describedByError}` : undefined} />
	</Field>
	<Field label={t('gemini.images')} for="gemini-input-files">
		<input id="gemini-input-files" name="images" type="file" multiple accept={[...GEMINI_DECISION_IMAGE_TYPES, '.heic', '.heif'].join(',')} onchange={addImages} aria-invalid={invalidField === 'gemini-input-files'} aria-describedby={invalidField === 'gemini-input-files' ? `gemini-image-help ${describedByError}` : 'gemini-image-help'} />
	</Field>
	<p id="gemini-image-help" class="hint">{t('gemini.imageHelp')}</p>
	{#if imageError}<Alert tone="danger" flat>{imageError}</Alert>{/if}
	{#if draft.images.length}
		<ul class="fields">
			{#each draft.images as image (image.id)}
				<li class="image-row">
					<p>{image.file.name}</p>
					<Field label={t('gemini.imageResolution')} for={`gemini-resolution-${image.id}`}>
						<SelectInput id={`gemini-resolution-${image.id}`} bind:value={image.resolution}>
							<option value="">{t('gemini.resolutionDefault')}</option>
							{#each GEMINI_DECISION_RESOLUTIONS as resolution (resolution)}<option value={resolution}>{t(resolutionLabels[resolution])}</option>{/each}
						</SelectInput>
					</Field>
					<Button variant="ghost" ariaLabel={t('gemini.removeImageNamed', { name: image.file.name })} onclick={() => {
						draft.images = draft.images.filter(({ id }) => id !== image.id);
						imageError = '';
						clearValidation();
						void tick().then(() => { if (!disabled) document.getElementById('gemini-input-files')?.focus(); });
					}}>{t('gemini.removeImage')}</Button>
				</li>
			{/each}
		</ul>
	{/if}
</fieldset>

<section class="fields" aria-labelledby="gemini-questions-heading">
	<h2 id="gemini-questions-heading">{t('gemini.questions')}</h2>
	{#each draft.questions as question, index (question.id)}
		<fieldset class="fields question" {disabled} data-testid="decision-question">
			<legend>{t('decisions.question', { number: index + 1 })}</legend>
			<div class="pair">
				<Field label={t('gemini.questionKey')} for={`gemini-key-${question.id}`} help={t('gemini.questionKeyHelp')} required>
					<TextInput id={`gemini-key-${question.id}`} required bind:value={question.key} autocomplete="off" ariaInvalid={invalidField === `gemini-key-${question.id}`} ariaDescribedBy={invalidField === `gemini-key-${question.id}` ? `gemini-key-${question.id}-message ${describedByError}` : undefined} />
				</Field>
				<Field label={t('decisions.type')} for={`gemini-type-${question.id}`}>
					<SelectInput id={`gemini-type-${question.id}`} value={question.type} onchange={(event) => changeType(question, event)} ariaInvalid={invalidField === `gemini-type-${question.id}`} ariaDescribedBy={invalidField === `gemini-type-${question.id}` ? describedByError : undefined}>
						<option value="noul">{t('gemini.yesNo')}</option>
						<option value="choice">{t('decisions.choice')}</option>
						<option value="score">{t('decisions.score')}</option>
					</SelectInput>
				</Field>
			</div>
			<Field label={t('decisions.instructions')} for={`gemini-instructions-${question.id}`} required>
				<TextareaInput id={`gemini-instructions-${question.id}`} required bind:value={question.instructions} rows={2} ariaInvalid={invalidField === `gemini-instructions-${question.id}`} ariaDescribedBy={invalidField === `gemini-instructions-${question.id}` ? describedByError : undefined} />
			</Field>
			{#if question.type === 'noul'}
				<div class="pair">
					<Field label={t('gemini.yesDescription')} for={`gemini-yes-${question.id}`}>
						<TextInput id={`gemini-yes-${question.id}`} bind:value={question.yes} />
					</Field>
					<Field label={t('gemini.noDescription')} for={`gemini-no-${question.id}`}>
						<TextInput id={`gemini-no-${question.id}`} bind:value={question.no} />
					</Field>
				</div>
			{:else}
				<fieldset class="fields">
					<legend>{t(question.type === 'choice' ? 'decisions.choices' : 'gemini.levels')}</legend>
					{#each question.rows as row, rowIndex (row.id)}
						<div class="criteria-row" class:choice={question.type === 'choice'}>
							{#if question.type === 'choice'}
								<Field label={t('gemini.optionKey', { number: rowIndex + 1 })} for={`gemini-option-${row.id}`} required>
									<TextInput id={`gemini-option-${row.id}`} required bind:value={row.key} autocomplete="off" ariaInvalid={invalidField === `gemini-option-${row.id}`} ariaDescribedBy={invalidField === `gemini-option-${row.id}` ? describedByError : undefined} />
								</Field>
							{/if}
							<Field label={t(question.type === 'choice' ? 'gemini.optionDescription' : 'gemini.levelDescription', { number: rowIndex + 1 })} for={`gemini-description-${row.id}`} required={question.type === 'score'}>
								<TextInput id={`gemini-description-${row.id}`} bind:value={row.description} required={question.type === 'score'} ariaInvalid={invalidField === `gemini-description-${row.id}`} ariaDescribedBy={invalidField === `gemini-description-${row.id}` ? describedByError : undefined} />
							</Field>
							<Button variant="ghost" disabled={question.rows.length <= 2} onclick={() => void removeRow(question, rowIndex)}>{t(question.type === 'choice' ? 'decisions.removeChoice' : 'decisions.removeLevel', { number: rowIndex + 1 })}</Button>
						</div>
					{/each}
					<Button variant="outline" disabled={question.rows.length >= MAX_GEMINI_CRITERIA} onclick={() => { question.rows.push({ id: allocateId(), key: '', description: '' }); }}>{t(question.type === 'choice' ? 'decisions.addChoice' : 'decisions.addLevel')}</Button>
				</fieldset>
			{/if}
			<div class="remove-row"><Button variant="ghost" disabled={draft.questions.length <= 1} onclick={() => void removeQuestion(index)}>{t('decisions.removeQuestion', { number: index + 1 })}</Button></div>
		</fieldset>
	{/each}
	<Button variant="outline" disabled={disabled || draft.questions.length >= MAX_GEMINI_QUESTIONS} onclick={() => void addQuestion()}>{t('decisions.addQuestion')}</Button>
</section>

<style>
	.fields { display: grid; gap: 1rem; min-width: 0; }
	fieldset { border: 0; padding: 0; margin: 0; }
	h2, legend { font-size: var(--type-body); font-weight: 600; color: var(--color-ink-0); }
	legend { margin-block-end: 0.75rem; }
	.question { padding-block: 1rem; border-block-start: 1px solid var(--color-line); }
	.hint { color: var(--color-ink-2); font-size: var(--type-support); }
	.pair, .criteria-row, .image-row { display: grid; gap: 0.75rem; min-width: 0; align-items: end; }
	.image-row p { overflow-wrap: anywhere; align-self: center; }
	.remove-row { display: flex; justify-content: end; }
	input[type='file'] { width: 100%; max-width: 100%; min-height: var(--control-touch-height); font: inherit; color: var(--color-ink-1); border: 1px solid var(--color-line-2); border-radius: var(--radius-md); background: var(--color-surface-input); padding: 0.5rem; }
	input[type='file']:focus-visible { outline: none; box-shadow: var(--focus-ring); }
	.fields :global([aria-invalid='true']) { border-color: var(--color-state-danger-text); }
	@media (min-width: 768px) {
		.pair { grid-template-columns: repeat(2, minmax(0, 1fr)); align-items: start; }
		.criteria-row { grid-template-columns: minmax(0, 1fr) auto; }
		.criteria-row.choice, .image-row { grid-template-columns: minmax(0, 1fr) minmax(0, 2fr) auto; }
	}
</style>
