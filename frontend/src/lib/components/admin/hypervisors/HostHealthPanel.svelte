<script lang="ts">
	import { auth, authReady, projectSwitching } from '$lib/stores/auth';
	import { api } from '$lib/api/client';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Pill from '$lib/components/ui/Pill.svelte';
	import TableShell from '$lib/components/ui/TableShell.svelte';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import HostMetricCell from './HostMetricCell.svelte';
	import type { HostHealthSnapshot, HostMetricKey, MonitoredHost } from '$lib/types/hostHealth';
	import { t } from '$lib/i18n/ns/admin-compute';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
	import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';

	const metricKeys: HostMetricKey[] = ['cpu', 'memory', 'disk', 'network_rx', 'network_tx'];
	const scope = $derived(JSON.stringify([$auth.userId, $auth.projectId, $auth.token, $auth.isSystemAdmin, $authReady, $projectSwitching]));
	let stored = $state<HostHealthSnapshot | null>(null);
	let owner = $state('');
	let loading = $state(true);
	let refreshing = $state(false);
	let loadFailed = $state(false);
	let receivedAt = $state(0);
	let now = $state(Date.now());
	let refresh = async () => {};
	const snapshot = $derived(owner === scope && $auth.isSystemAdmin && $authReady && !$projectSwitching ? stored : null);
	const age = $derived(snapshot?.collected_at ? now - Date.parse(snapshot.collected_at) : Number.POSITIVE_INFINITY);
	const verified = $derived(Boolean(snapshot?.enabled && !snapshot.stale && !loadFailed && age >= -5_000 && age < 30_000 && now - receivedAt < 30_000));

	function date(value: string | null): string {
		if (!value || !Number.isFinite(Date.parse(value))) return t('hostHealth.unmeasured');
		return new Date(value).toLocaleString(intlLocale(), { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
	}

	$effect(() => {
		const context = scope;
		const token = $auth.token;
		const projectId = $auth.projectId ?? undefined;
		const allowed = $auth.isSystemAdmin && $authReady && !$projectSwitching;
		stored = null;
		owner = context;
		loadFailed = false;
		loading = Boolean(token && allowed);
		refreshing = false;
		if (!token || !allowed) return;
		let active = true;
		let running = false;
		const load = async () => {
			if (!active || running) return;
			running = true;
			refreshing = true;
			try {
				const next = await api.get<HostHealthSnapshot>('/api/v1/admin/host-health', token, projectId, { refresh: true });
				if (!active || context !== scope) return;
				stored = next;
				owner = context;
				receivedAt = Date.now();
				now = receivedAt;
				loadFailed = false;
			} catch {
				if (active && context === scope) loadFailed = true;
			} finally {
				running = false;
				if (active && context === scope) { loading = false; refreshing = false; }
			}
		};
		refresh = load;
		let timer: ReturnType<typeof setInterval> | undefined;
		const visibility = () => {
			if (timer !== undefined) clearInterval(timer);
			timer = undefined;
			now = Date.now();
			if (!document.hidden) { void load(); timer = setInterval(() => { void load(); }, 10_000); }
		};
		const clock = setInterval(() => { now = Date.now(); }, 5_000);
		document.addEventListener('visibilitychange', visibility);
		visibility();
		return () => {
			active = false;
			if (timer !== undefined) clearInterval(timer);
			clearInterval(clock);
			document.removeEventListener('visibilitychange', visibility);
		};
	});
</script>

{#snippet connection(host: MonitoredHost)}
	{@const status = verified ? host.reachability.status : 'unknown'}
	<div class="host-state space-y-1">
		<Pill dot tone={status === 'up' ? 'success' : status === 'down' ? 'danger' : 'neutral'}>{t(`hostHealth.connection.${status}`)}</Pill>
		<p class="text-xs text-ink-2 tabular-nums">{date(host.reachability.checked_at)}</p>
		{#if verified && host.reachability.latency_ms !== null}
			<p class="text-xs text-ink-2 tabular-nums">{t('hostHealth.latency', { value: host.reachability.latency_ms.toLocaleString(intlLocale(), { maximumFractionDigits: 1 }) })}</p>
		{/if}
		{#if host.reachability.error}<p class="text-xs text-ink-2 break-words">{host.reachability.error}</p>{/if}
	</div>
{/snippet}

{#snippet heartbeat(host: MonitoredHost)}
	{@const status = verified ? host.heartbeat.status : 'unknown'}
	<div class="host-state space-y-1">
		<Pill dot tone={status === 'up' ? 'success' : status === 'down' ? 'danger' : 'neutral'}>{t(`hostHealth.heartbeat.${status}`)}</Pill>
		{#if host.heartbeat.source}<p class="text-xs text-ink-2 break-words">{host.heartbeat.source}</p>{/if}
		<p class="text-xs text-ink-2 tabular-nums">{date(host.heartbeat.updated_at)}</p>
	</div>
{/snippet}

<section class="mt-6 space-y-3" aria-label={t('hostHealth.title')}>
	<div class="flex flex-wrap items-start justify-between gap-3">
		<div class="min-w-0 space-y-1">
			<h2 class="text-sm font-semibold text-ink-0">{t('hostHealth.title')}</h2>
			<p class="text-xs text-ink-2">{t('hostHealth.cadence')}</p>
			{#if snapshot?.collected_at}<p class="text-xs text-ink-2 tabular-nums">{t('hostHealth.collectedAt', { time: date(snapshot.collected_at) })}</p>{/if}
		</div>
		<div class="flex flex-wrap gap-2">
			<Button variant="outline" size="sm" href="/admin/infrastructure-topology">{t('hostHealth.topology')}</Button>
			<Button variant="secondary" size="sm" disabled={refreshing || !$auth.isSystemAdmin || !$auth.token} onclick={() => { void refresh(); }}>{t('hostHealth.refresh')}</Button>
		</div>
	</div>
	<p class="text-xs text-ink-2">{t('hostHealth.evidence')}</p>
	{#if loadFailed}<Alert tone="danger">{t('hostHealth.loadFailed')}</Alert>{/if}
	{#if snapshot?.error}<Alert tone="warning">{t('hostHealth.collectionFailed')} <code>{snapshot.error}</code></Alert>{/if}
	{#if snapshot?.enabled && !verified && !loading && !loadFailed}<Alert tone="warning">{t('hostHealth.stale')}</Alert>{/if}
	{#if loading}
		<LoadingSkeleton variant="table" rows={3} />
	{:else if snapshot && !snapshot.enabled}
		<Alert tone="neutral">{t('hostHealth.disabled')}</Alert>
	{:else if snapshot?.hosts.length}
		<ResponsiveTable>
			{#snippet cards()}
				{#each snapshot?.hosts ?? [] as host (host.id)}
					<CompactResourceCard>
						<div class="flex flex-wrap items-start justify-between gap-2"><h3 class="break-all font-mono text-sm text-ink-0">{host.name}</h3><span class="text-xs text-ink-2">{t(`hostHealth.role.${host.role}`)}</span></div>
						<div class="flex flex-wrap gap-2"><Pill dot tone={verified && host.reachability.status === 'up' ? 'success' : verified && host.reachability.status === 'down' ? 'danger' : 'neutral'}>{t(`hostHealth.connection.${verified ? host.reachability.status : 'unknown'}`)}</Pill><Pill dot tone={verified && host.heartbeat.status === 'up' ? 'success' : verified && host.heartbeat.status === 'down' ? 'danger' : 'neutral'}>{t(`hostHealth.heartbeat.${verified ? host.heartbeat.status : 'unknown'}`)}</Pill></div>
						<div class="grid grid-cols-2 gap-2 text-xs"><div><p class="text-ink-2">{t('hostHealth.metric.cpu')}</p><HostMetricCell metric={host.metrics.cpu} verified={verified && host.reachability.status === 'up'} label={t('hostHealth.metric.cpu')} /></div><div><p class="text-ink-2">{t('hostHealth.metric.memory')}</p><HostMetricCell metric={host.metrics.memory} verified={verified && host.reachability.status === 'up'} label={t('hostHealth.metric.memory')} /></div></div>
						{#snippet details()}<div class="space-y-3 text-xs text-ink-2"><p class="break-all font-mono">{host.address ?? '—'}</p><div><p>{t('hostHealth.probe')}</p>{@render connection(host)}</div><div><p>{t('hostHealth.service')}</p>{@render heartbeat(host)}</div>{#each metricKeys.filter((key) => key !== 'cpu' && key !== 'memory') as key}<div><p>{t(`hostHealth.metric.${key}`)}</p><HostMetricCell metric={host.metrics[key]} verified={verified && host.reachability.status === 'up'} label={t(`hostHealth.metric.${key}`)} /></div>{/each}{#if host.metrics_error}<p class="break-words">{t('hostHealth.metricsFailed')} <code>{host.metrics_error}</code></p>{/if}</div>{/snippet}
					</CompactResourceCard>
				{/each}
			{/snippet}
			<TableShell density="compact">
				<table aria-label={t('hostHealth.title')}>
					<thead><tr>
						<th>{t('hostHealth.host')}</th><th>{t('hostHealth.probe')}</th><th>{t('hostHealth.service')}</th>
						{#each metricKeys as key}<th>{t(`hostHealth.metric.${key}`)}</th>{/each}
					</tr></thead>
					<tbody>
						{#each snapshot.hosts as host (host.id)}
							<tr>
								<td><span class="block font-mono text-xs text-ink-0">{host.name}</span><span class="block text-xs text-ink-2">{t(`hostHealth.role.${host.role}`)}</span><span class="block font-mono text-xs text-ink-2">{host.address ?? '—'}</span></td>
								<td>{@render connection(host)}</td><td>{@render heartbeat(host)}</td>
								{#each metricKeys as key}<td><div class="w-24"><HostMetricCell metric={host.metrics[key]} verified={verified && host.reachability.status === 'up'} label={t(`hostHealth.metric.${key}`)} /></div></td>{/each}
							</tr>
							{#if host.metrics_error}<tr><td colspan="8" class="text-xs text-ink-2">{host.name}: {t('hostHealth.metricsFailed')} <code>{host.metrics_error}</code></td></tr>{/if}
						{/each}
					</tbody>
				</table>
			</TableShell>
		</ResponsiveTable>
		<p class="text-xs text-ink-2">{t('hostHealth.trendNote')}</p>
	{:else if snapshot && !snapshot.error && verified}
		<Alert tone="neutral">{t('hostHealth.noHosts')}</Alert>
	{/if}
</section>

<style>
	.host-state :global(.pill) { font-size: 0.75rem; }
</style>
