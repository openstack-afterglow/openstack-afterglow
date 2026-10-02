<script lang="ts">
	import type { ContextState } from '$lib/api/chatContracts';
	import SlidePanel from '$lib/components/SlidePanel.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import UsageBar from '$lib/components/ui/UsageBar.svelte';
	import { t } from '$lib/i18n/ns/chat-panel';
	import { intlLocale } from '$lib/i18n/runtime.svelte';

	let { state, explanation, onClose }: {
		state: ContextState | null;
		explanation: string;
		onClose: () => void;
	} = $props();

	const labelKeys: Record<string, Parameters<typeof t>[0]> = {
		messages: 'context.components.messages', system_prompt: 'context.components.systemPrompt', workspace: 'context.components.workspace',
		memory: 'context.components.memory', skills: 'context.components.skills', agent: 'context.components.agent', tools: 'context.components.tools',
		mcp_tools: 'context.components.mcpTools', deferred_tools: 'context.components.deferredTools', summary: 'context.components.summary', attachments: 'context.components.attachments', overhead: 'context.components.overhead'
	};
	const format = $derived(new Intl.NumberFormat(intlLocale()));
	const ratio = $derived(new Intl.NumberFormat(intlLocale(), { maximumFractionDigits: 1 }));
	const breakdown = $derived(state?.breakdown);
	const included = $derived(breakdown?.components.filter((component) => component.included) ?? []);
	const deferred = $derived(breakdown?.components.filter((component) => !component.included && !breakdown.uncounted.includes(component.id)) ?? []);
	const unresolved = $derived(breakdown?.components.filter((component) => !component.included && breakdown.uncounted.includes(component.id)) ?? []);
	const fullLimit = $derived(state?.context_limit && state.context_limit > 0 ? state.context_limit : null);
	const knownInput = $derived(state?.input_tokens ?? null);
	const complete = $derived(breakdown?.complete !== false && state?.measurement !== 'unknown' && knownInput !== null);
	const remaining = $derived(complete && state?.input_budget != null ? Math.max(0, state.input_budget - knownInput!) : null);
	const measurement = $derived(t(state?.measurement === 'tokenizer' ? 'context.measurement.tokenizer' : state?.measurement === 'estimated' ? 'context.measurement.estimated' : 'context.measurement.unknown'));
	const label = (id: string) => labelKeys[id] ? t(labelKeys[id]) : id;
	const tokens = (value: number | null) => value === null ? t('context.unknownTokens') : format.format(value);
	const share = (value: number | null) => value === null || fullLimit === null ? t('context.unknownShare') : t('context.share', { percent: ratio.format(value / fullLimit * 100) });
</script>

<SlidePanel {onClose} width="w-full md:w-[28rem] max-w-full" resizable={false} ariaLabel={t('context.title')}>
	<section id="chat-context-detail" class="px-4 pb-6 text-sm text-ink-1" aria-labelledby="chat-context-heading">
		<h2 id="chat-context-heading" class="text-base font-semibold text-ink-0">{t('context.title')}</h2>
		<p class="mt-2 break-words text-xs leading-relaxed text-ink-2">{explanation}</p>

		{#if state}
			<div class="mt-5 border-b border-line pb-4">
				<div class="flex flex-wrap items-baseline justify-between gap-2">
					<span class="text-xs text-ink-2">{t('context.inputSummary', { kind: complete ? 'included' : 'known', measurement })}</span>
					<strong class="font-mono text-base tabular-nums text-ink-0">{tokens(knownInput)} / {tokens(fullLimit)}</strong>
				</div>
				{#if knownInput !== null && fullLimit !== null}
					<div class="mt-3">
						<UsageBar percent={knownInput / fullLimit * 100} label={t(complete ? 'context.inputShare' : 'context.knownInputShare')} showValue={false} size="sm" />
					</div>
				{/if}
				<p class="mt-2 text-xs leading-relaxed text-ink-2">{t('context.inputBudget', { tokens: tokens(state.input_budget) })}</p>
			</div>

			{#if breakdown}
				<p class="mt-4 text-xs text-ink-2">{t('context.breakdownSummary', { scope: breakdown.scope, status: breakdown.complete ? 'complete' : 'incomplete' })}</p>
				{#if !breakdown.complete}
					<p class="mt-2 text-xs leading-relaxed text-ink-2">{t('context.incompleteNotice')}</p>
				{/if}
				<div class="mt-4 grid grid-cols-[minmax(0,1fr)_auto_4rem] gap-2 border-b border-line pb-2 text-xs text-ink-2" aria-hidden="true">
					<span>{t('context.includedContext')}</span><span>{t('context.tokens')}</span><span class="text-right">{t('context.totalShare')}</span>
				</div>
				<div class="divide-y divide-line">
					{#each included as component (component.id)}
						<details class="py-1">
							<summary class="grid min-h-11 cursor-pointer grid-cols-[minmax(0,1fr)_auto_4rem] items-center gap-2 rounded-md text-xs focus-visible:outline focus-visible:outline-2 focus-visible:outline-line-2">
								<span class="min-w-0 break-words font-medium">{label(component.id)} <span class="font-normal text-ink-2">({tokens(component.count)})</span></span>
								<span class="font-mono tabular-nums">{component.measurement === 'estimated' && component.tokens !== null ? t('context.estimatedTokens', { tokens: tokens(component.tokens) }) : tokens(component.tokens)}</span>
								<span class="text-right font-mono tabular-nums text-ink-2">{share(component.tokens)}</span>
							</summary>
							{#if component.items.length}
								<ul class="mt-2 space-y-2 border-l border-line pl-3 text-xs leading-relaxed text-ink-2">
									{#each component.items as item, index (`${index}:${item}`)}<li class="break-words">{item}</li>{/each}
								</ul>
							{:else}
								<p class="mt-2 text-xs text-ink-2">{t(component.measurement === 'estimated' ? 'context.estimatedItem' : 'context.countOnlyItem')}</p>
							{/if}
						</details>
					{/each}
				</div>
				{#if breakdown.uncounted.length}
					<p class="mt-3 break-words text-xs leading-relaxed text-ink-2">{t('context.uncounted', { items: breakdown.uncounted.map(label).join(', ') })}</p>
				{/if}
				{#if unresolved.length}
					<h3 class="mt-5 border-t border-line pt-4 text-xs font-semibold">{t('context.unresolvedTitle')}</h3>
					<p class="mt-2 text-xs leading-relaxed text-ink-2">{t('context.unresolvedNotice')}</p>
					{#each unresolved as component (component.id)}
						<details class="mt-3 text-xs">
							<summary class="min-h-11 cursor-pointer content-center break-words">{t('context.componentSummary', { label: label(component.id), count: component.count === null ? t('context.unknownCount') : t('context.componentCount', { count: component.count }) })}</summary>
							<ul class="space-y-2 pl-3 text-ink-2">{#each component.items as item, index (`${index}:${item}`)}<li class="break-words">{item}</li>{/each}</ul>
						</details>
					{/each}
				{/if}
				{#if deferred.length}
					<h3 class="mt-5 border-t border-line pt-4 text-xs font-semibold">{t('context.deferredTitle')}</h3>
					<p class="mt-2 text-xs leading-relaxed text-ink-2">{t('context.deferredNotice')}</p>
					{#each deferred as component (component.id)}
						<details class="mt-3 text-xs">
							<summary class="min-h-11 cursor-pointer content-center break-words">{t('context.componentSummary', { label: label(component.id), count: component.count === null ? t('context.unknownCount') : t('context.componentCount', { count: component.count }) })}</summary>
							<ul class="space-y-2 pl-3 text-ink-2">{#each component.items as item, index (`${index}:${item}`)}<li class="break-words">{item}</li>{/each}</ul>
						</details>
					{/each}
				{/if}
			{:else}
				<p class="mt-5 text-xs leading-relaxed text-ink-2">{t('context.missingBreakdown')}</p>
			{/if}

			<dl class="mt-5 space-y-3 border-t border-line pt-4 text-xs">
				<div class="grid grid-cols-[minmax(0,1fr)_auto_4rem] gap-2"><dt>{t('context.outputReserve')}</dt><dd class="font-mono tabular-nums">{tokens(state.output_reserve)}</dd><dd class="text-right font-mono text-ink-2">{share(state.output_reserve)}</dd></div>
				<div class="grid grid-cols-[minmax(0,1fr)_auto_4rem] gap-2"><dt>{t('context.safetyReserve')}</dt><dd class="font-mono tabular-nums">{tokens(state.safety_reserve)}</dd><dd class="text-right font-mono text-ink-2">{share(state.safety_reserve)}</dd></div>
				<div class="grid grid-cols-[minmax(0,1fr)_auto_4rem] gap-2 font-semibold"><dt>{t('context.remainingInput')}</dt><dd class="font-mono tabular-nums">{tokens(remaining)}</dd><dd class="text-right font-mono text-ink-2">{share(remaining)}</dd></div>
			</dl>
			<p class="mt-4 break-all text-xs leading-relaxed text-ink-2">{t('context.model', { model: state.model_name })}<br />{t('context.revision', { revision: state.revision })}</p>
		{/if}

		<div class="mt-5 flex flex-wrap gap-2 border-t border-line pt-4">
			<Button href="/dashboard/chat/settings?section=memory" variant="ghost" size="sm" class="min-h-11">{t('context.viewMemory')}</Button>
			<Button href="/dashboard/chat/settings?section=tools" variant="ghost" size="sm" class="min-h-11">{t('context.viewTools')}</Button>
			<Button href="/dashboard/chat/settings?section=mcp" variant="ghost" size="sm" class="min-h-11">{t('context.viewMcp')}</Button>
			<Button href="/dashboard/chat/settings?section=skills" variant="ghost" size="sm" class="min-h-11">{t('context.viewSkills')}</Button>
		</div>
		<p class="mt-3 text-xs leading-relaxed text-ink-2">{t('context.billingNotice')}</p>
	</section>
</SlidePanel>
