<script lang="ts">
	import { t } from '$lib/i18n/ns/chat-studio';
	import Button from '$lib/components/ui/Button.svelte';

	interface Option { id: string; label: string; }
	interface Props {
		question: string;
		options?: Option[];
		allowMultiple?: boolean;
		allowText?: boolean;
		pending?: boolean;
		onResolve: (response: { option_ids: string[]; text: string | null }) => void;
	}
	let { question, options = [], allowMultiple = false, allowText = false, pending = false, onResolve }: Props = $props();
	let selected = $state<string[]>([]);
	let answer = $state('');
	function toggle(id: string) {
		selected = allowMultiple ? (selected.includes(id) ? selected.filter((value) => value !== id) : [...selected, id]) : [id];
	}
	function submit() {
		if (pending || (!selected.length && !answer.trim())) return;
		onResolve({ option_ids: selected, text: answer.trim() || null });
	}
</script>

<section class="interaction" aria-label={t('interactionCard.inputRequired')}>
	<p>{question}</p>
	{#if options.length}
		<div class="options" role={allowMultiple ? 'group' : 'radiogroup'}>
			{#each options as option (option.id)}
				<label><input type={allowMultiple ? 'checkbox' : 'radio'} name="interaction-option" checked={selected.includes(option.id)} onchange={() => toggle(option.id)} disabled={pending} /> {option.label}</label>
			{/each}
		</div>
	{/if}
	{#if allowText}<textarea bind:value={answer} maxlength="4000" disabled={pending} aria-label={t('interactionCard.additionalResponse')}></textarea>{/if}
	<Button variant="secondary" size="sm" disabled={pending || (!selected.length && !answer.trim())} onclick={submit}>{t('interactionCard.sendResponse')}</Button>
</section>

<style>
	.interaction { border: 1px solid var(--color-line); border-radius: .6rem; background: var(--color-surface-sunken); padding: .75rem; color: var(--color-ink-1); }
	.interaction p { margin: 0 0 .6rem; }
	.options { display: grid; gap: .4rem; margin-bottom: .6rem; }
	.options label { color: var(--color-ink-2); }
	textarea { box-sizing: border-box; width: 100%; min-height: 4rem; margin: 0 0 .6rem; border: 1px solid var(--color-line); border-radius: .4rem; background: var(--color-surface-base); color: var(--color-ink-1); padding: .45rem; resize: vertical; }
</style>
