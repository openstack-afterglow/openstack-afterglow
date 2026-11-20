<script lang="ts">
	import { onMount } from 'svelte';
	import { REDUCED_MOTION_QUERY } from '$lib/design/tokens';
	import { t } from '$lib/i18n/ns/common';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import type { ChartMount, ChartSpec } from './types';

	interface Props {
		spec: ChartSpec;
		height: number;
		width?: number;
		label?: string;
		decorative?: boolean;
		class?: string;
	}
	let { spec, height, width, label, decorative = false, class: className = '' }: Props = $props();
	let element: HTMLDivElement;
	let chart = $state.raw<ChartMount>();
	let reducedMotion = $state(false);
	let failed = $state(false);

	function snapshotSpec(): ChartSpec {
		// Snapshot only data: callbacks are intentionally shared, not cloneable state.
		if (spec.kind === 'choropleth') {
			const { onSelect, onHover, ...data } = spec;
			return { ...$state.snapshot(data), onSelect, onHover };
		}
		if (spec.kind === 'time-series') {
			const { formatTime, formatValue, ...data } = spec;
			return { ...$state.snapshot(data), formatTime, formatValue };
		}
		if (spec.kind === 'bar') {
			const { formatValue, formatCategory, ...data } = spec;
			return { ...$state.snapshot(data), formatValue, formatCategory };
		}
		return $state.snapshot(spec);
	}

	onMount(() => {
		let alive = true;
		const media = window.matchMedia?.(REDUCED_MOTION_QUERY);
		const updateMotion = () => { reducedMotion = media?.matches ?? false; };
		updateMotion();
		media?.addEventListener('change', updateMotion);
		// React and upstream Bklit are never evaluated during Svelte SSR.
		import('./runtime').then(({ mountChart }) => {
			if (!alive) return;
			chart = mountChart(element, snapshotSpec(), { height, locale: intlLocale(), reducedMotion });
		}).catch((error) => {
			if (!alive) return;
			failed = true;
			console.error('Bklit chart loading failed', error);
		});
		return () => {
			alive = false;
			media?.removeEventListener('change', updateMotion);
			chart?.destroy();
		};
	});

	$effect(() => {
		// Snapshot tracks nested Svelte data mutations without leaking proxies into React.
		const next = snapshotSpec();
		chart?.update(next, { height, locale: intlLocale(), reducedMotion });
	});
</script>

<div
	class="bklit-chart {className}"
	style:width={width === undefined ? undefined : `${width}px`}
	aria-hidden={decorative || undefined}
	role={!decorative && label ? 'group' : undefined}
	aria-label={decorative ? undefined : label}
	data-bklit-kind={spec.kind}
>
	<div class="bklit-chart-plot" style:height={`${height}px`} bind:this={element}></div>
	{#if failed && !decorative}<p class="mt-2 text-[length:var(--type-support)] text-state-danger-text" role="status">{t('chart.error')}</p>{/if}
</div>
