<script module lang="ts">
	/** Decimal places of a finite number as written, capped at 3, so counting keeps its precision. */
	export function decimalsOf(value: number): number {
		if (!Number.isFinite(value) || Number.isInteger(value)) return 0;
		const text = String(value);
		const point = text.indexOf('.');
		return point < 0 ? 0 : Math.min(3, text.length - point - 1);
	}
</script>

<script lang="ts">
	import { MOTION_DURATION_MS } from '$lib/design/tokens';
	import { canAnimate } from '$lib/utils/motion';

	interface Props {
		value: number;
		/** Formats both intermediate and settled values; defaults to the number as written. */
		format?: (value: number) => string;
		duration?: number;
		class?: string;
	}

	let { value, format, duration = MOTION_DURATION_MS.data, class: className = '' }: Props = $props();

	let node = $state<HTMLSpanElement | null>(null);
	/** Intermediate value while counting; `null` once settled. */
	let shown = $state<number | null>(null);
	let settled = 0;

	const target = $derived(Number.isFinite(value) ? value : 0);
	const render = (n: number) => {
		if (format) return format(n);
		const decimals = decimalsOf(target);
		return n === target ? String(target) : n.toFixed(decimals);
	};
	$effect(() => {
		const end = target;
		const el = node;
		// bind:this lands after the first effect pass; wait for it so the first count still starts at 0.
		if (!el) return;
		// Count only where it can be seen: reduced motion, no Web Animations (SSR/jsdom) or an
		// element without layout boxes renders the settled value directly.
		if (!canAnimate(el) || el.getClientRects().length === 0 || settled === end) {
			settled = end;
			shown = null;
			return;
		}
		const start = settled;
		const startedAt = performance.now();
		shown = start;
		let frame = requestAnimationFrame(function step(now) {
			const t = Math.min(1, (now - startedAt) / duration);
			if (t >= 1) {
				settled = end;
				shown = null;
				return;
			}
			shown = start + (end - start) * (1 - (1 - t) ** 3);
			frame = requestAnimationFrame(step);
		});
		return () => {
			cancelAnimationFrame(frame);
			// Retargeting mid-count continues from what is on screen instead of jumping.
			if (shown !== null) settled = shown;
		};
	});
</script>

<span bind:this={node} class="animated-number {className}">
	{#if shown === null}
		{render(target)}
	{:else}
		<span aria-hidden="true">{render(shown)}</span><span class="sr-only">{render(target)}</span>
	{/if}
</span>

<style>
	.animated-number { font-variant-numeric: tabular-nums; }
</style>
