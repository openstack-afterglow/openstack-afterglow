<script lang="ts">
	import { onMount } from 'svelte';
	import { REDUCED_MOTION_QUERY } from '$lib/design/tokens';
	import { t } from '$lib/i18n/ns/common';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import type { ChartMount, ChartSpec } from './types';
	import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
	import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';

	interface Props {
		spec: ChartSpec;
		height: number;
		width?: number;
		label?: string;
		decorative?: boolean;
		showData?: boolean;
		class?: string;
	}
	let { spec, height, width, label, decorative = false, showData, class: className = '' }: Props = $props();
	let element: HTMLDivElement;
	let chart = $state.raw<ChartMount>();
	let reducedMotion = $state(false);
	let failed = $state(false);
	let dataOpen = $state(false);
	const seriesSpec = $derived(spec.kind === 'time-series' || spec.kind === 'bar' ? spec : null);
	const canShowData = $derived(!decorative && !!seriesSpec && (showData ?? !seriesSpec.compact));

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

	function category(value: string | number | null | undefined): string {
		if (seriesSpec?.kind === 'time-series' && typeof value === 'number') {
			return seriesSpec.formatTime?.(value) ?? new Date(value).toLocaleString(intlLocale());
		}
		if (seriesSpec?.kind === 'bar' && value != null) {
			return seriesSpec.formatCategory?.(String(value), 'detail') ?? String(value);
		}
		return value == null ? '—' : String(value);
	}

	function number(value: string | number | null | undefined): string {
		if (typeof value !== 'number' || !Number.isFinite(value)) return '—';
		return seriesSpec?.formatValue?.(value) ?? value.toLocaleString(intlLocale());
	}
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
	{#if failed && !decorative}<p class="mt-2 text-xs text-state-danger-text" role="status">{t('chart.error')}</p>{/if}
	{#if canShowData && seriesSpec}
		<details class="mt-2 text-xs text-ink-2" bind:open={dataOpen}>
			<summary class="w-fit cursor-pointer rounded-sm py-2 focus-visible:outline-none focus-visible:shadow-[var(--focus-ring)]">{t('chart.data')}</summary>
			{#if dataOpen}
				<ResponsiveTable>
					{#snippet cards()}
						{#each seriesSpec.data as row}
							{#snippet remainingSeries()}<dl>{#each seriesSpec.series.slice(2) as series}<div><dt>{series.label}</dt><dd>{number(row[series.key])}</dd></div>{/each}</dl>{/snippet}
							<CompactResourceCard details={seriesSpec.series.length > 2 ? remainingSeries : undefined}>
								<p class="font-medium text-ink-0">{category(row[seriesSpec.xKey])}</p>
								<dl>{#each seriesSpec.series.slice(0, 2) as series}<div><dt>{series.label}</dt><dd>{number(row[series.key])}</dd></div>{/each}</dl>
							</CompactResourceCard>
						{/each}
					{/snippet}
				<!-- The overflow region remains keyboard-scrollable when the data table is wide. -->
				<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
				<div class="max-h-64 overflow-auto" tabindex="0" role="region" aria-label={label ?? t('chart.data')}>
					<table class="w-full text-left tabular-nums">
						<thead><tr><th class="p-2" scope="col">{seriesSpec.kind === 'time-series' ? t('chart.time') : t('chart.category')}</th>{#each seriesSpec.series as series}<th class="p-2" scope="col">{series.label}</th>{/each}</tr></thead>
						<tbody>{#each seriesSpec.data as row}<tr class="border-t border-line"><th class="p-2 font-normal" scope="row">{category(row[seriesSpec.xKey])}</th>{#each seriesSpec.series as series}<td class="p-2">{number(row[series.key])}</td>{/each}</tr>{/each}</tbody>
					</table>
				</div>
				</ResponsiveTable>
			{/if}
		</details>
	{/if}
</div>
