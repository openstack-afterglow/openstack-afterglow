<script lang="ts">
	type Range = '24h' | '7d' | '14d';

	interface Props {
		value: Range;
		onchange: (range: Range) => void;
	}

	const { value, onchange }: Props = $props();

	const options: Array<{ label: string; value: Range }> = [
		{ label: '24h', value: '24h' },
		{ label: '7d',  value: '7d' },
		{ label: '14d', value: '14d' },
	];

	function handleKeydown(e: KeyboardEvent, idx: number) {
		if (e.key === 'ArrowRight' && idx < options.length - 1) {
			onchange(options[idx + 1].value);
		} else if (e.key === 'ArrowLeft' && idx > 0) {
			onchange(options[idx - 1].value);
		}
	}
</script>

<div
	class="inline-flex gap-0.5 bg-surface-sunken rounded-lg p-0.5"
	role="group"
	aria-label="기간 선택"
>
	{#each options as opt, idx}
		<button
			type="button"
			aria-pressed={value === opt.value}
			class="px-2.5 py-1 text-[11px] font-medium rounded-md transition-colors {value === opt.value
				? 'bg-surface-selected text-[var(--color-ink-0)]'
				: 'text-[var(--color-ink-3)] hover:text-[var(--color-ink-1)]'}"
			onclick={() => onchange(opt.value)}
			onkeydown={(e) => handleKeydown(e, idx)}
		>
			{opt.label}
		</button>
	{/each}
</div>
