<script lang="ts">
	import { t } from '$lib/i18n/ns/topology';
	// 토폴로지 네트워크(스위치) 읽기 전용 상세. 페이지가 SlidePanel 안에 렌더링한다.
	// 조작 컨트롤은 두지 않으며, provider 세그먼트·MTU 등 관리자 행은 showProvider 일 때만 렌더링한다.
	import Button from '$lib/components/ui/Button.svelte';
	import Pill from '$lib/components/ui/Pill.svelte';
	import SectionHeader from '$lib/components/ui/SectionHeader.svelte';
	import StatusChip from '$lib/components/ui/StatusChip.svelte';
	import TableShell from '$lib/components/ui/TableShell.svelte';
	import ToggleGroup from '$lib/components/ui/ToggleGroup.svelte';
	import type {
		TopologyData,
		TopologyInstance,
		TopologyRouter,
		TopologyTraffic,
		TopologyTrafficHistory,
	} from '$lib/types/topology';
	import { fmtRate } from './canvasHelpers';
	import TrafficSparkline from './TrafficSparkline.svelte';
	import { untrack } from 'svelte';

	interface Props {
		networkId: string;
		data: TopologyData;
		traffic?: TopologyTraffic | null;
		/** 관리자 응답 전용 provider 메타(네트워크 타입·세그먼트·물리 네트워크)를 표시 */
		showProvider?: boolean;
		onSelectInstance?: (id: string) => void;
		onSelectRouter?: (id: string) => void;
		/**
		 * 사용량 히스토리 로더. 라우트가 주입한다(패널은 auth·api 를 모른다).
		 * 없으면 "사용량 추이" 섹션 자체를 렌더링하지 않는다.
		 */
		loadHistory?: (networkId: string, range: string) => Promise<TopologyTrafficHistory | null>;
	}

	let {
		networkId,
		data,
		traffic = null,
		showProvider = false,
		onSelectInstance,
		onSelectRouter,
		loadHistory,
	}: Props = $props();

	const net = $derived(data.networks.find((n) => n.id === networkId) ?? null);
	const kind = $derived(net ? (net.is_external ? 'external' : net.is_shared ? 'shared' : 'internal') : 'internal');
	const subnetIds = $derived(new Set((net?.subnet_details ?? []).map((s) => s.id)));
	const routers = $derived<TopologyRouter[]>(
		net
			? data.routers.filter((r) => r.external_gateway_network_id === net.id || r.connected_subnet_ids.some((sid) => subnetIds.has(sid)))
			: [],
	);
	const isolated = $derived(kind === 'internal' && routers.length === 0);
	const instances = $derived<{ inst: TopologyInstance; ips: string[] }[]>(
		net
			? data.instances
				.map((inst) => ({
					inst,
					ips: inst.ip_addresses
						.filter((a) => a.type !== 'floating' && (a.network_id ? a.network_id === net.id : a.network_name === net.name))
						.map((a) => a.addr),
				}))
				.filter((x) => x.ips.length > 0)
			: [],
	);
	const cidrs = $derived((net?.subnet_details ?? []).map((s) => s.cidr));
	const gateways = $derived((net?.subnet_details ?? []).map((s) => s.gateway_ip).filter((g): g is string => Boolean(g)));
	const dhcpText = $derived.by(() => {
		const subs = net?.subnet_details ?? [];
		if (!subs.length) return '—';
		if (subs.every((s) => s.dhcp_enabled)) return t('panel.enabled');
		if (subs.some((s) => s.dhcp_enabled)) return t('panel.partial');
		return t('panel.disabled');
	});
	const segmentLabel = $derived.by(() => {
		if (!net || net.provider_segmentation_id == null) return null;
		return net.provider_network_type === 'vlan' ? t('panel.vlanTag') : 'VXLAN VNI';
	});
	const rateText = $derived(fmtRate(net ? traffic?.networks?.[net.id] : null));

	// 백엔드 `_HISTORY_RANGES` 와 같은 키를 쓴다. 여기 없는 구간은 사용자가 고를 수 없다 —
	// API 만 지원하고 UI 에 노출하지 않으면 "구현했지만 쓸 수 없는" 상태가 된다.
	const RANGE_OPTIONS = $derived([
		{ value: '15m', label: t('panel.range15') },
		{ value: '30m', label: t('panel.range30') },
		{ value: '1h', label: t('panel.rangeHour') },
	]);
	const RANGE_LABEL: Record<string, string> = $derived({ '15m': t('panel.recent15'), '30m': t('panel.recent30'), '1h': t('panel.recentHour') });
	const networkTypeKeys = {
		external: ['panel.typeExternal', 'panel.typeExternalIsolated'],
		shared: ['panel.typeShared', 'panel.typeSharedIsolated'],
		internal: ['panel.typeInternal', 'panel.typeInternalIsolated'],
	} as const;
	let historyRange = $state('15m');

	/** 마지막 표본의 시각. `합산 트래픽`(15초 폴링)과 달리 이 섹션은 패널 열 때 1회라 기준 시각을 밝힌다. */
	const sampledAt = $derived.by(() => {
		const last = history?.series.at(-1);
		if (!last) return '';
		const d = new Date(last.ts * 1000);
		return t('panel.sampledAt', { time: `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}` });
	});

	let history = $state<TopologyTrafficHistory | null>(null);
	let historyLoading = $state(false);
	let historyError = $state('');
	/** 마지막으로 조회를 시작한 `networkId|range`. 같은 조합의 중복 조회를 막는 유일한 기준이다. */
	let historyFor = $state<string | null>(null);

	// 패널을 열 때(= networkId 가 바뀔 때) **1회만** 조회한다. 트래픽 폴링에 얹으면
	// Prometheus 부하가 네트워크 수만큼 곱해진다(백엔드 docstring 과 같은 이유).
	//
	// 무엇이 이 effect 를 다시 깨우든 networkId 가 그대로면 재조회하지 않는다 — `loadHistory` 를
	// untrack 으로 읽는 것만으로는 부족하다(라우트가 인라인 화살표를 넘기거나, 테스트 하네스처럼
	// props 객체를 통째로 교체하는 구현이면 모든 prop 읽기가 한꺼번에 무효화된다).
	$effect(() => {
		const id = networkId;
		const range = historyRange;
		const fetcher = untrack(() => loadHistory);
		if (!fetcher || !id) {
			history = null;
			historyFor = null;
			return;
		}
		// 구간 변경은 사용자 행동이므로 재조회가 맞다 — 막는 건 "같은 조합의" 중복 조회뿐이다.
		const key = `${id}|${range}`;
		if (untrack(() => historyFor) === key) return;
		historyFor = key;

		let stale = false;
		historyLoading = true;
		historyError = '';
		void (async () => {
			try {
				// await 로 감싼다 — 로더가 프라미스를 안 주거나 동기 예외를 던져도 패널이 깨지면 안 된다.
				const res = await fetcher(id, range);
				if (!stale) history = res ?? null;
			} catch {
				if (stale) return;
				history = null;
				historyError = t('panel.historyFailed');
			} finally {
				if (!stale) historyLoading = false;
			}
		})();
		return () => {
			stale = true;
		};
	});
</script>

<div class="p-6 space-y-5">
	<!--
		닫기 버튼은 SlidePanel 이 제공한다(`data-slide-panel-close`). 여기서 또 그리면 헤더에 × 가 두 개 보인다.
		상태(StatusChip)도 아래 "상태" 행에만 둔다 — 헤더에 같이 두면 같은 값이 한 화면에 두 번 나온다.
	-->
	<div class="min-w-0">
		<p class="text-xs text-ink-2">{t('resource.network')}</p>
		<h2 class="text-lg font-semibold text-ink-0 break-words">{net?.name ?? networkId}</h2>
		<p class="text-xs text-ink-2 mt-0.5 font-mono break-all">{networkId}</p>
		<div class="mt-2 flex flex-wrap items-center gap-1.5">
			<Pill tone="neutral" size="sm">{t('panel.readOnly')}</Pill>
			{#if isolated}<Pill tone="neutral" size="sm">{t('hud.isolated')}</Pill>{/if}
		</div>
	</div>

	{#if !net}
		<p class="text-sm text-ink-2">{t('panel.missingNetwork')}</p>
	{:else}
		<dl class="kv">
			<dt>{t('panel.type')}</dt>
			<dd>{t(networkTypeKeys[kind][isolated ? 1 : 0])}</dd>
			<dt>{t('panel.status')}</dt>
			<dd><StatusChip status={net.status} /></dd>
			<dt>{t('panel.project')}</dt>
			<dd class:mono={Boolean(net.project_id)}>{net.project_id ?? t('panel.public')}</dd>
			<dt>CIDR</dt>
			<dd class="mono">{cidrs.length ? cidrs.join(', ') : '—'}</dd>
			<dt>DHCP</dt>
			<dd>{dhcpText}</dd>
			<dt>{t('panel.gateway')}</dt>
			<dd class="mono">{gateways.length ? gateways.join(', ') : '—'}</dd>
			<dt>MTU</dt>
			<dd class="mono">{net.mtu ?? '—'}</dd>
			<dt>{t('panel.totalTraffic')}</dt>
			<dd class="mono">{rateText}</dd>
			{#if showProvider}
				<dt>{t('panel.networkType')}</dt>
				<dd><span class="mono">{net.provider_network_type ?? '—'}</span> <Pill tone="admin-tone" size="xs">{t('panel.admin')}</Pill></dd>
				<dt>{segmentLabel ?? t('panel.segment')}</dt>
				<dd><span class="mono">{net.provider_segmentation_id ?? '—'}</span> <Pill tone="admin-tone" size="xs">{t('panel.admin')}</Pill></dd>
				<dt>{t('panel.physicalNetwork')}</dt>
				<dd><span class="mono">{net.provider_physical_network ?? '—'}</span> <Pill tone="admin-tone" size="xs">{t('panel.admin')}</Pill></dd>
			{/if}
		</dl>
		{#if isolated}
			<p class="note">{t('panel.isolatedNote')}</p>
		{/if}

		{#if loadHistory}
			<section class="space-y-2">
				<SectionHeader title={t('panel.history')} meta={history ? (RANGE_LABEL[history.range] ?? history.range) : ''} />
				<ToggleGroup
					value={historyRange}
					options={RANGE_OPTIONS}
					size="xs"
					ariaLabel={t('panel.historyRange')}
					onchange={(v) => (historyRange = v)}
				/>
				{#if historyLoading}
					<p class="text-sm text-ink-2">{t('panel.loading')}</p>
				{:else if historyError}
					<p class="text-sm text-ink-2">{historyError}</p>
				{:else if history?.series.length}
					<TrafficSparkline series={history.series} rangeLabel={sampledAt ? t('panel.sampleIntervalAt', { seconds: history.step_s, sampledAt }) : t('panel.sampleInterval', { seconds: history.step_s })} />
					<!--
						위 `합산 트래픽` 행과 **같은 방향별 표기**(fmtRate)를 쓴다. 합계 하나로 두면
						`▼ 5.8M ▲ 2.0M` 옆에 `7.8M` 이 붙어 사용자가 두 행을 대조할 수 없다.
					-->
					<dl class="kv">
						<dt>{t('panel.average')}</dt>
						<dd class="mono">{fmtRate(history.stats.avg)}</dd>
						<dt>{t('panel.maximum')}</dt>
						<dd class="mono">{fmtRate(history.stats.max)}</dd>
						<dt>{t('panel.latest')}</dt>
						<dd class="mono">{fmtRate(history.stats.latest)}</dd>
					</dl>
					<p class="note">
						{t('panel.historyNote', { window: history.window })}
					</p>
				{:else}
					<p class="text-sm text-ink-2">{t('panel.noSamples')}</p>
				{/if}
			</section>
		{/if}

		<section class="space-y-2">
			<SectionHeader title={t('resource.subnet')} meta={t('panel.count', { count: net.subnet_details.length })} />
			{#if net.subnet_details.length}
				<TableShell density="compact">
					<table>
						<thead>
							<tr><th>{t('panel.name')}</th><th>CIDR</th><th>{t('panel.gateway')}</th><th>DHCP</th></tr>
						</thead>
						<tbody>
							{#each net.subnet_details as sub (sub.id)}
								<tr>
									<td>{sub.name || sub.id}</td>
									<td class="mono">{sub.cidr}</td>
									<td class="mono">{sub.gateway_ip ?? '—'}</td>
									<td>{sub.dhcp_enabled ? t('panel.enabled') : t('panel.disabled')}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</TableShell>
			{:else}
				<p class="text-sm text-ink-2">{t('empty.subnets')}</p>
			{/if}
		</section>

		<section class="space-y-2">
			<SectionHeader title={t('resource.instance')} meta={t('panel.count', { count: instances.length })} />
			{#if instances.length}
				<div class="flex flex-wrap gap-1.5">
					{#each instances as { inst, ips } (inst.id)}
						<Button variant="outline" size="xs" title={ips.join(', ')} onclick={() => onSelectInstance?.(inst.id)}>
							{inst.name}<span class="mono text-ink-2">{ips[0]}</span>
						</Button>
					{/each}
				</div>
			{:else}
				<p class="text-sm text-ink-2">{t('panel.noInstances')}</p>
			{/if}
		</section>

		<section class="space-y-2">
			<SectionHeader title={t('resource.router')} meta={t('panel.count', { count: routers.length })} />
			{#if routers.length}
				<div class="flex flex-wrap gap-1.5">
					{#each routers as r (r.id)}
						<Button variant="outline" size="xs" onclick={() => onSelectRouter?.(r.id)}>
							{r.name}{#if r.external_gateway_network_id === net.id}<span class="text-ink-2">{t('panel.gateway')}</span>{/if}
						</Button>
					{/each}
				</div>
			{:else}
				<p class="text-sm text-ink-2">{t('panel.noRouters')}</p>
			{/if}
		</section>

		<p class="text-xs text-ink-2">{t('panel.actionsNote')}</p>
	{/if}
</div>

<style>
	.mono { font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
	.kv {
		display: grid;
		grid-template-columns: minmax(6rem, 9rem) 1fr;
		gap: 0.375rem 0.75rem;
		margin: 0;
		font-size: 0.875rem;
	}
	.kv dt { font-size: 0.75rem; color: var(--color-ink-2); padding-top: 0.125rem; }
	.kv dd { margin: 0; color: var(--color-ink-1); min-width: 0; overflow-wrap: anywhere; }
	.note {
		font-size: 0.75rem;
		color: var(--color-ink-2);
		border-left: 2px solid var(--color-line-2);
		padding-left: 0.625rem;
	}
</style>
