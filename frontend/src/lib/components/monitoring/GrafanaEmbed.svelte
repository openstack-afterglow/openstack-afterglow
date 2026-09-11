<script lang="ts">
	import { auth } from '$lib/stores/auth';
	import { loadGrafanaContext, type GrafanaDashboardKey } from '$lib/stores/grafana';

	interface Props {
		dashboardKey: GrafanaDashboardKey;
		panelId?: number;
		vars?: Record<string, string>;
		range?: string;
		height?: number;
		desktopHeight?: number;
		title?: string;
		fill?: boolean;
	}

	let {
		dashboardKey,
		panelId,
		vars = {},
		range = 'now-1h',
		height = 360,
		desktopHeight,
		title,
		fill = false,
	}: Props = $props();

	const containerHeight = $derived(
		fill
			? '100%'
			: desktopHeight && desktopHeight > height
				? `clamp(${height}px, 85vh, ${desktopHeight}px)`
				: `${height}px`,
	);
	const iframeHeight = $derived(
		fill
			? title
				? 'calc(100% - 36px)'
				: '100%'
			: title
				? desktopHeight && desktopHeight > height
					? `clamp(${height - 36}px, calc(85vh - 36px), ${desktopHeight - 36}px)`
					: `${height - 36}px`
				: containerHeight,
	);

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	// ctx는 $state로 분리 — token/projectId 변경 시만 재로드 (캐시됨)
	type GrafanaCtx = { grafanaUrl: string; dashboards: Record<GrafanaDashboardKey, string> };
	let ctx = $state<GrafanaCtx | null>(null);
	let loadError = $state(false);
	let contextError = $state(false);
	let loading = $state(true);

	$effect(() => {
		// 동기 구간에서 token, projectId를 읽어 의존성 등록
		loading = true;
		loadError = false;
		contextError = false;
		ctx = null;
		loadGrafanaContext(token, projectId).then((result) => {
			loading = false;
			if (!result) { contextError = true; return; }
			ctx = result;
		});
	});

	// iframeUrl은 $derived — ctx, vars, dashboardKey, panelId, range 모두 동기 의존성으로 추적됨
	const iframeUrl = $derived.by(() => {
		if (!ctx) return null;
		const uid = ctx.dashboards[dashboardKey];
		if (!uid) return null;
		const base = ctx.grafanaUrl;
		const varParams = Object.entries(vars)
			.map(([k, v]) => `var-${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
			.join('&');
		const timeParams = `from=${range}&to=now`;
		const common = `orgId=1&theme=dark&kiosk&${timeParams}${varParams ? '&' + varParams : ''}`;
		if (panelId !== undefined) {
			return `${base}/d-solo/${uid}/_?panelId=${panelId}&${common}`;
		}
		return `${base}/d/${uid}/_?${common}`;
	});
</script>

<div class="w-full rounded-xl overflow-hidden bg-surface-base border border-line" style="height: {containerHeight}">
	{#if loading}
		<div class="w-full h-full flex items-center justify-center">
			<div class="w-5 h-5 border-2 border-action-warm border-t-transparent rounded-full animate-spin"></div>
		</div>
	{:else if contextError || loadError}
		<div class="w-full h-full flex flex-col items-center justify-center gap-2 text-center px-6">
			<svg class="w-8 h-8 text-ink-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"
					d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
			</svg>
			<p class="text-sm text-ink-3">모니터링이 구성되지 않았습니다</p>
			<p class="text-xs text-ink-3">config.toml [monitoring] grafana_base_url 확인</p>
		</div>
	{:else if iframeUrl}
		{#if title}
			<div class="px-4 py-2 border-b border-line text-xs font-medium text-ink-2 uppercase tracking-wide">
				{title}
			</div>
		{/if}
		<iframe
			src={iframeUrl}
			class="w-full border-0"
			style="height: {iframeHeight}"
			sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
			loading="lazy"
			title={title ?? dashboardKey}
			onerror={() => { loadError = true; }}
		></iframe>
	{/if}
</div>
