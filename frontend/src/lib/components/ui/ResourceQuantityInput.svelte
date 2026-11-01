<script lang="ts">
	import { onDestroy } from 'svelte';
	import Field from './Field.svelte';
	import TextInput from './TextInput.svelte';

	interface Props {
		id: string;
		label: string;
		unit: string;
		value: number;
		values?: number[];
		min: number;
		max: number;
		step?: number;
		disabled?: boolean;
		invalid?: boolean;
		unavailable: string;
		resetKey: unknown;
		pending?: boolean;
		onvalue: (value: number) => void;
	}
	let { id, label, unit, value, values, min, max, step = 1, disabled = false, invalid = false, unavailable, resetKey, pending = $bindable(false), onvalue }: Props = $props();
	let draft = $state('');
	let malformed = $state(false);
	let renderedValue = Number.NaN;
	let renderedReset: unknown = Symbol();
	const steps = $derived(values ?? []);
	const sliderIndex = $derived.by(() => {
		const number = Number(draft);
		return steps.reduce((best, candidate, index) => Math.abs(candidate - number) < Math.abs(steps[best] - number) ? index : best, 0);
	});
	const hasChoices = $derived(Boolean(values?.length));
	const error = $derived(malformed || invalid ? unavailable : undefined);
	$effect(() => {
		if (Object.is(value, renderedValue) && resetKey === renderedReset) return;
		renderedValue = value; renderedReset = resetKey;
		const offStep = value % step !== 0;
		draft = String(value); malformed = offStep; pending = offStep;
	});
	onDestroy(() => { pending = false; });

	function enter(event: Event) {
		draft = (event.currentTarget as HTMLInputElement).value;
		const number = Number(draft);
		const malformedNumber = draft.trim() === '' || !Number.isInteger(number) || number < min || number > max;
		malformed = malformedNumber || number % step !== 0;
		pending = malformed;
		// Keep representable off-step coordinates visible when another resource changes.
		onvalue(malformedNumber ? Number.NaN : number);
	}
	function slide(event: Event, commit: boolean) {
		const next = steps[Number((event.currentTarget as HTMLInputElement).value)];
		if (next === undefined) return;
		draft = String(next); malformed = false;
		pending = !commit;
		if (commit) onvalue(next);
	}
</script>

<Field {label} for={id} {error}>
	<div class="quantity-controls">
		<div class="quantity-slider">
			<div class="quantity-bounds" aria-hidden="true"><span>{hasChoices ? values![0] : '—'}</span><span>{hasChoices ? values![values!.length - 1] : '—'}</span></div>
			<input id={`${id}-slider`} type="range" min="0" max={Math.max(1, steps.length - 1)} step="1" value={sliderIndex} disabled={disabled || !hasChoices || steps.length < 2} aria-label={label} aria-valuetext={`${draft} ${unit}`} aria-invalid={error ? true : undefined} aria-describedby={error ? `${id}-message` : undefined} oninput={event => slide(event, false)} onchange={event => slide(event, true)} />
		</div>
		<div class="quantity-number">
			<TextInput {id} type="number" inputmode="numeric" {min} {max} {step} value={draft} {disabled} ariaInvalid={Boolean(error)} ariaDescribedBy={error ? `${id}-message` : undefined} oninput={enter} class="tabular-nums" />
			<span class="quantity-unit" aria-hidden="true">{unit}</span>
		</div>
	</div>
</Field>

<style>
	.quantity-controls { display: grid; grid-template-columns: minmax(0, 1fr) 8.5rem; gap: 1.5rem; align-items: end; min-width: 0; }
	.quantity-slider { min-width: 0; }
	.quantity-bounds { display: flex; justify-content: space-between; color: var(--color-ink-2); font-size: var(--type-support); font-variant-numeric: tabular-nums; }
	input[type='range'] { display: block; width: 100%; min-width: 0; min-height: var(--control-height); margin: 0; accent-color: var(--color-accent); cursor: pointer; background: transparent; }
	input[type='range']:focus-visible { outline: none; border-radius: var(--radius-md); box-shadow: var(--focus-ring); }
	input[type='range']:disabled { cursor: not-allowed; }
	.quantity-number { display: flex; min-width: 0; align-items: center; gap: 0.5rem; min-height: var(--control-height); }
	.quantity-unit { flex-shrink: 0; color: var(--color-ink-2); font-size: var(--type-support); }
	@media (max-width: 767px), (pointer: coarse) { input[type='range'], .quantity-number { min-height: var(--control-touch-height); } .quantity-controls { gap: 1rem; } }
</style>
