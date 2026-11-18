<script lang="ts">
	import type { GeminiDecisionRequest, GeminiDecisionResult } from '$lib/api/decisionStudio';
	import { t } from '$lib/i18n/ns/decision-studio';
	import { intlLocale } from '$lib/i18n/runtime.svelte';

	let { result, questions, inputPrice }: {
		result: GeminiDecisionResult;
		questions: GeminiDecisionRequest['questions'];
		inputPrice: string | null | undefined;
	} = $props();
	const formatPercent = $derived(new Intl.NumberFormat(intlLocale(), { style: 'percent', maximumFractionDigits: 2 }));
	const formatNumber = $derived(new Intl.NumberFormat(intlLocale(), { maximumFractionDigits: 4 }));
	const rate = $derived(inputPrice?.trim() ? Number(inputPrice) : NaN);
	const cost = $derived(Number.isFinite(rate) && rate >= 0 ? rate * (result.usage.total_input_tokens / 1_000_000) : null);
</script>

<section class="results" aria-labelledby="decision-answers-heading" data-testid="decision-results">
	<h2 id="decision-answers-heading">{t('decisions.answers')}</h2>
	{#each Object.entries(questions) as [key, question] (key)}
		{@const answer = result.answers[key]}
		<section class="answer" aria-labelledby={`gemini-answer-${key}`}>
			<h3 id={`gemini-answer-${key}`}>{key}</h3>
			<p class="muted">{question.instructions}</p>
			{#if answer.type === 'noul'}
				<p>{t('gemini.yesProbability')}: <strong>{formatPercent.format(answer.noul)}</strong></p>
			{:else if answer.type === 'choice'}
				<p>{t('gemini.winner')}: <strong>{answer.choice}</strong></p>
			{:else}
				<p>{t('decisions.score')}: <strong>{formatNumber.format(answer.score)}</strong></p>
			{/if}
			<p>{t('decisions.confidence')}: {formatPercent.format(answer.confidence)}</p>
			{#if answer.type !== 'noul'}
				<dl class="distribution" aria-label={t('decisions.probability')}>
					{#each Object.entries(answer.probabilities) as [label, probability] (label)}
						<div>
							<dt>{answer.type === 'score' ? t('gemini.legendLevel', { number: formatNumber.format(Number(label)), description: answer.legend[label] }) : label}</dt>
							<dd>{formatPercent.format(probability)}</dd>
							<meter min="0" max="1" value={probability} aria-hidden="true"></meter>
						</div>
					{/each}
				</dl>
			{/if}
		</section>
	{/each}
	<h2>{t('decisions.usage')}</h2>
	<dl class="usage">
		<div><dt>{t('decisions.inputTokens')}</dt><dd>{formatNumber.format(result.usage.total_input_tokens)}</dd></div>
		{#each result.usage.input_tokens_by_modality as entry}
			<div><dt>{t(entry.modality === 'image' ? 'gemini.imageTokens' : 'gemini.textTokens')}</dt><dd>{formatNumber.format(entry.tokens)}</dd></div>
		{/each}
		<div><dt>{t('decisions.outputTokens')}</dt><dd>{formatNumber.format(result.usage.total_output_tokens)}</dd></div>
		<div><dt>{t('decisions.totalTokens')}</dt><dd>{formatNumber.format(result.usage.total_tokens)}</dd></div>
		<div><dt>{t('gemini.estimatedCost')}</dt><dd>{cost === null ? t('gemini.estimateUnavailable') : cost.toLocaleString(intlLocale(), { maximumFractionDigits: 10 })}</dd></div>
	</dl>
</section>

<style>
	.results, .answer, .distribution, .usage { display: grid; min-width: 0; }
	.results { gap: 1rem; }
	.answer, .distribution, .usage { gap: 0.5rem; }
	.answer { padding-block: 1rem; border-block-start: 1px solid var(--color-line); }
	h2, h3 { font-size: var(--type-body); font-weight: 600; color: var(--color-ink-0); overflow-wrap: anywhere; }
	p, dt { overflow-wrap: anywhere; }
	.muted, dt { color: var(--color-ink-2); }
	.muted { font-size: var(--type-support); }
	.distribution > div, .usage > div { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 0.25rem 1rem; }
	dd { text-align: end; font-variant-numeric: tabular-nums; }
	meter { grid-column: 1 / -1; width: 100%; height: 0.5rem; border: none; background: var(--color-surface-sunken); border-radius: var(--radius-sm); }
	meter::-webkit-meter-bar { border: none; background: var(--color-surface-sunken); border-radius: var(--radius-sm); }
	meter::-webkit-meter-optimum-value { background: var(--color-accent); }
	meter::-moz-meter-bar { background: var(--color-accent); }
</style>
