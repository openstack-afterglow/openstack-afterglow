<script lang="ts">
	import RichText from '$lib/i18n/RichText.svelte';
	import { t } from '$lib/i18n/ns/topology';
	// 캔버스 뷰 범례. 색은 토큰 스와치로만 표시하고 상태는 항상 라벨과 함께 둔다.
	import Pill from '$lib/components/ui/Pill.svelte';
	import StatusChip from '$lib/components/ui/StatusChip.svelte';
	import { TOPOLOGY_COLORS, TONE_CSS_VAR } from '$lib/design/tokens';
</script>

{#snippet monoText(text: string)}<span class="mono">{text}</span>{/snippet}

<!-- 일반 div 의 aria-label 은 무시되므로 list/listitem 역할로 이름을 노출한다 -->
<div class="legend" role="list" aria-label={t('canvasLegend.label')}>
	<span role="listitem"><StatusChip status="ACTIVE" /></span>
	<span role="listitem"><StatusChip status="SHUTOFF" /><StatusChip status="BUILD" /></span>
	<span role="listitem"><StatusChip status="ERROR" /></span>
	<span role="listitem"><StatusChip status="DOWN" />{t('canvasLegend.unknown')}</span>
	<span role="listitem">
		<svg class="gl" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true" style:color={TOPOLOGY_COLORS.gateway}><circle cx="8" cy="8" r="6" /><path d="M8 4v8M4 8h8M5.5 5.5l5 5M10.5 5.5l-5 5" /></svg>
		{t('canvasLegend.router')}
	</span>
	<span role="listitem">
		<svg class="gl" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><rect x="2" y="5" width="12" height="6" rx="1" /><path d="M5 8h1M8 8h1M11 8h1" /></svg>
		{t('canvasLegend.switch')}
	</span>
	<span role="listitem">
		<svg class="gl" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" style:color={TOPOLOGY_COLORS.external}><path d="M4.6 10.6a2.4 2.4 0 0 1 .3-4.78 3.3 3.3 0 0 1 6.32-.6A2.6 2.6 0 0 1 11.6 10.6z" /><path d="M8 10.6v2.2M4.4 12.8h7.2" /></svg>
		{t('canvasLegend.internet')}
	</span>
	<span role="listitem">
		<svg class="gl" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.3" aria-hidden="true"><ellipse cx="8" cy="4" rx="5" ry="2" /><path d="M3 4v8a5 2 0 0 0 10 0V4M3 8a5 2 0 0 0 10 0" /></svg>
		{t('canvasLegend.database')}
	</span>
	<span role="listitem">
		<svg class="gl" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="M8 2v12M3 5h10M4 11h8" /></svg>
		{t('resource.loadBalancer')}
	</span>
	<span role="listitem">
		<svg class="gl" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.3" aria-hidden="true"><ellipse cx="8" cy="5" rx="5" ry="2" /><path d="M3 5v6M13 5v6M3 11a5 2 0 0 0 10 0" /></svg>
		{t('resource.instance')}
	</span>
	<span role="listitem"><span class="sw" style:background={TOPOLOGY_COLORS.external}></span>{t('network.external')}</span>
	<span role="listitem"><span class="sw" style:background={TOPOLOGY_COLORS.shared}></span>{t('network.shared')}</span>
	<span role="listitem"><span class="sw" style:background={TOPOLOGY_COLORS.internal}></span><span class="sw" style:background={TOPOLOGY_COLORS.internal2}></span>{t('canvasLegend.internal')}</span>
	<span role="listitem"><Pill tone="neutral" size="xs">{t('hud.isolated')}</Pill>{t('canvasLegend.routerless')}</span>
	<span role="listitem"><span class="mono fip" style:color={TOPOLOGY_COLORS.external}>✦</span>{t('legend.floatingIp')}</span>
	<span role="listitem"><Pill tone="warm" size="xs">2NIC</Pill>{t('canvasLegend.multiNic')}</span>
	<span role="listitem"><span class="ln" style:background={TOPOLOGY_COLORS.internal}></span>{t('canvasLegend.connection')}</span>
	<span role="listitem"><span class="dot dot-in" style:background={TOPOLOGY_COLORS.internal}></span>{t('canvasLegend.isolatedTraffic')}</span>
	<span role="listitem"><span class="dot dot-ns" style:background={TOPOLOGY_COLORS.internal}></span>{t('canvasLegend.gatewayTraffic')}</span>
	<span role="listitem"><span class="ln dash" style:--c={TOPOLOGY_COLORS.internal}></span>{t('canvasLegend.lbMember')}</span>
	<span role="listitem"><span class="ln dash" style:--c={TONE_CSS_VAR.neutral}></span>{t('canvasLegend.inactive')}</span>
	<span role="listitem"><Pill tone="neutral" size="xs"><span class="mono">▼ ▲</span></Pill><RichText segments={t.rich('canvasLegend.trunk')} tags={{ mono: monoText }} /></span>
</div>

<style>
	.dot { display: inline-block; width: 7px; height: 7px; border-radius: 999px; flex-shrink: 0; }
	.dot-ns { border: 1px solid var(--color-surface-base); }
	.dot-in { border: none; }
	.legend {
		display: flex;
		flex-wrap: wrap;
		gap: 0.375rem 1.25rem;
		font-size: 0.75rem;
		color: var(--color-ink-2);
		padding: 0 0.25rem;
	}
	.legend > span { display: inline-flex; align-items: center; gap: 0.375rem; }
	.mono { font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
	.sw { width: 3px; height: 14px; border-radius: 999px; flex-shrink: 0; }
	.ln { width: 24px; height: 2px; border-radius: 999px; }
	.ln.dash { background: repeating-linear-gradient(90deg, var(--c) 0 4px, transparent 4px 7px); }
	.gl { width: 14px; height: 14px; flex-shrink: 0; }
	.fip { font-size: 0.75rem; }
</style>
