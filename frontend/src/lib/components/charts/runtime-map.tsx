import React from 'react';
import { ParentSize } from '@visx/responsive';
import { ChoroplethChart } from '$lib/vendor/bklit-ui/charts/choropleth/choropleth-chart';
import { ChoroplethFeature } from '$lib/vendor/bklit-ui/charts/choropleth/choropleth-feature';
import { ChoroplethTooltip } from '$lib/vendor/bklit-ui/charts/choropleth/choropleth-tooltip';
import { useChoroplethStable } from '$lib/vendor/bklit-ui/charts/choropleth/choropleth-context';
import type { ChoroplethFeature as GeographicFeature } from '$lib/vendor/bklit-ui/charts/choropleth/choropleth-context';
import type { ChoroplethSpec } from './mapTypes';
import type { ChartRenderOptions } from './types';

/** Logical annotation only; country geometry is rendered by native Bklit Feature. */
export function mapFlowPath(from: [number, number], to: [number, number], width: number, height: number): string {
	const direction = to[0] >= from[0] ? 1 : -1;
	const x = Math.max(4, Math.min(width - 4, (from[0] + to[0]) / 2 + (to[1] - from[1]) * direction * 0.2));
	const y = Math.max(4, Math.min(height - 4, (from[1] + to[1]) / 2 - Math.abs(to[0] - from[0]) * 0.2));
	return `M${from[0]},${from[1]} Q${x},${y} ${to[0]},${to[1]}`;
}

export function MapAnnotations({ spec }: { spec: ChoroplethSpec }) {
	const { projectPoint, width, height } = useChoroplethStable();
	const site = spec.anchor ? projectPoint(spec.anchor.coordinate) : null;
	return <g className="access-flows" aria-hidden="true" pointerEvents="none">
		{(spec.flows ?? []).map(flow => {
			const from = projectPoint(flow.from), to = projectPoint(flow.to);
			if (!from || !to || !Number.isFinite(from[0]) || !Number.isFinite(from[1]) || !Number.isFinite(to[0]) || !Number.isFinite(to[1])) return null;
			return <path key={flow.key} className={`access-flow${flow.highlighted ? ' highlighted' : ''}`} data-country={flow.key}
				d={mapFlowPath(from, to, width, height)} fill="none" stroke={flow.color} strokeWidth={flow.width}
				strokeDasharray={flow.dashed ? '5 3' : undefined} opacity={flow.opacity ?? 1}
				style={flow.highlighted ? { filter: 'drop-shadow(0 0 1px var(--color-ink-0))' } : undefined} />;
		})}
		{site && site.every(Number.isFinite) && <>
			{spec.anchor?.radius != null && <circle className="site-traffic-ring" cx={site[0]} cy={site[1]} r={spec.anchor.radius} fill="none" stroke="var(--color-chart-2)" strokeWidth={2} />}
			<path className="site-marker" d={`M${site[0]},${site[1] - 4} L${site[0] + 4},${site[1]} L${site[0]},${site[1] + 4} L${site[0] - 4},${site[1]} Z`}
				fill="var(--color-ink-0)" stroke="var(--color-surface-base)" strokeWidth={1} />
		</>}
	</g>;
}

export function ChoroplethMap({ spec }: { spec: ChoroplethSpec; options: ChartRenderOptions }) {
	const firstKey = Object.keys(spec.features)[0];
	function keyOf(feature: GeographicFeature): string | null {
		const key = feature.properties[spec.featureKey];
		return typeof key === 'string' && spec.features[key] ? key : null;
	}
	function featureProps(feature: GeographicFeature): React.SVGProps<SVGPathElement> {
		const key = keyOf(feature);
		if (key === null) return { 'aria-hidden': true };
		const state = spec.features[key];
		return {
			role: 'button', tabIndex: spec.selectedKey === key || (!spec.selectedKey && key === firstKey) ? 0 : -1,
			'aria-label': state.label, 'aria-pressed': spec.selectedKey === key,
			stroke: spec.activeKey === key ? 'var(--color-ink-0)' : 'var(--color-line-2)',
			strokeWidth: spec.activeKey === key ? 1.5 : 0.4,
			onClick: () => spec.onSelect(key),
			onKeyDown: event => {
				if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); spec.onSelect(key); }
			},
			onMouseEnter: () => spec.onHover(key), onMouseLeave: () => spec.onHover(null),
			onFocus: () => spec.onHover(key), onBlur: () => spec.onHover(null),
			children: <title>{state.label}</title>,
		};
	}
	return <ParentSize debounceTime={10}>{({ width, height }) => width > 0 && height > 0 ?
		<ChoroplethChart data={spec.data} svgLabel={spec.label} className="h-full" aspectRatio="auto" animationDuration={0}
			enterTransition={{ duration: 0 }} zoomEnabled={false} center={[0, 20]}
			scale={Math.min(width / (2 * Math.PI), height / 4.8)} translate={[width / 2, height / 2]}
		>
			<ChoroplethFeature stroke="var(--color-line-2)" strokeWidth={0.4} fadedOpacity={1}
				getFeatureColor={feature => { const key = keyOf(feature); return key ? spec.features[key].fill : 'var(--color-surface-sunken)'; }}
				getFeatureProps={featureProps} />
			{/* A native SVG group keeps annotation under Bklit's projection provider. */}
			<g><MapAnnotations spec={spec} /></g>
			<ChoroplethTooltip content={({ feature }) => { const key = keyOf(feature); return key ? <span>{spec.features[key].label}</span> : null; }} />
		</ChoroplethChart> : null}</ParentSize>;
}
