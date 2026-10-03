<script lang="ts">
	import TrafficArea from '$lib/components/ui/TrafficArea.svelte';
	import type { WaygateClient } from '$lib/types/waygate';
	import {
		clientTrafficTotals,
		currentClientTraffic,
		formatTrafficBytes,
		waygateTrafficFreshnessMs,
		WAYGATE_TRAFFIC_STALE_MS,
		type ClientTrafficHistory,
	} from '$lib/utils/waygateTraffic';

	interface Props { client: WaygateClient; history?: ClientTrafficHistory; now: number; pollIntervalSeconds?: number; }
	let { client, history, now, pollIntervalSeconds }: Props = $props();
	const freshnessMs = $derived(pollIntervalSeconds === undefined ? WAYGATE_TRAFFIC_STALE_MS : waygateTrafficFreshnessMs(client.report_interval_seconds, pollIntervalSeconds));
	const current = $derived(currentClientTraffic(history, now, freshnessMs));
	const totals = $derived(clientTrafficTotals(client));
	const reportAge = $derived.by(() => {
		if (!client.last_reported_at) return null;
		const reportedAt = Date.parse(client.last_reported_at);
		return Number.isFinite(reportedAt) ? Math.max(0, Math.floor((now - reportedAt) / 1000)) : null;
	});
	const reportState = $derived.by(() => {
		if (!client.enabled) return '비활성화됨 · 트래픽 기록 중지';
		if (!history?.samples.length) return '상태 보고 대기';
		if (!current.fresh) return '보고 지연 · 현재 속도 알 수 없음';
		if (client.online === false) return '최근 보고 · 핸드셰이크 없음';
		return current.rxRate === null && current.txRate === null ? '최근 보고 · 다음 보고 후 속도 계산' : '최근 보고';
	});
	const rows = $derived([
		{ key: 'rx', label: '▼ 클라이언트 수신 RX', total: totals.rxBytes, rate: current.rxRate },
		{ key: 'tx', label: '▲ 클라이언트 송신 TX', total: totals.txBytes, rate: current.txRate },
	]);
</script>

<section class="mt-4 min-w-0 border-t border-line pt-3" aria-label={`${client.name} 클라이언트 기준 트래픽`}>
	<div class="mb-3 flex flex-wrap items-center justify-between gap-x-3 gap-y-1 text-xs text-ink-2">
		<span class="font-medium text-ink-1">클라이언트 기준 트래픽</span>
		<span role="status">{reportState}</span>
	</div>
	{#if pollIntervalSeconds !== undefined}
		<p class="mb-3 text-xs text-ink-2">
			{reportAge === null ? '마지막 보고 없음' : `마지막 보고 ${reportAge}초 전`}
			· {client.report_interval_seconds == null ? '에이전트 보고 주기 미확인' : `에이전트 보고 주기 ${client.report_interval_seconds}초`}
			· 최근 120초 핸드셰이크만 온라인으로 분류하며 연결을 보증하지 않습니다.
		</p>
	{/if}
	{#snippet metrics()}
	<dl class="mb-3 grid grid-cols-1 gap-3 text-sm tabular-nums md:grid-cols-2">
		{#each rows as row (row.key)}
			<div class="min-w-0">
				<dt class="text-xs text-ink-2">{row.label}</dt>
				<dd class="mt-1 flex flex-wrap items-baseline gap-x-3 gap-y-1 text-ink-0">
					<span>{formatTrafficBytes(row.total)} <span class="text-xs text-ink-2">누적</span></span>
					<span>{row.rate === null ? '속도 —' : `${formatTrafficBytes(row.rate)}/s`}</span>
				</dd>
			</div>
		{/each}
	</dl>
	{/snippet}
	{#if client.enabled}
		<TrafficArea samples={history?.samples ?? []} rxLabel="클라이언트 수신 RX" txLabel="클라이언트 송신 TX" fresh={current.fresh}>
			{@render metrics()}
		</TrafficArea>
	{:else}
		{@render metrics()}
	{/if}
	<p class="mt-2 text-xs text-ink-2">
		누적량은 게이트웨이가 마지막으로 보고한 peer 카운터이며 재시작·재활성화 시 0부터 다시 셀 수 있습니다. 속도는 새 보고 사이의 차이입니다.
	</p>
</section>
