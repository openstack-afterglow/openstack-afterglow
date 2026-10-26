<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-system';
	import { untrack } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import StatusChip from '$lib/components/ui/StatusChip.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Pagination from '$lib/components/ui/Pagination.svelte';
	import SelectInput from '$lib/components/ui/SelectInput.svelte';
	import TableShell from '$lib/components/ui/TableShell.svelte';
	import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
	import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';

	interface Props {
		endpoint: string;
		storageKey: string;
		showUser?: boolean;
	}

	let { endpoint, storageKey, showUser = false }: Props = $props();

	interface ActivityLog {
		id: number;
		created_at: string;
		project_id: string;
		user_id: string;
		username: string;
		resource_type: string;
		resource_id: string | null;
		resource_name: string | null;
		action: string;
		status: 'success' | 'failed' | 'started';
		error_message: string | null;
		extra: Record<string, unknown> | null;
	}

	let pageSize = $state('10');
	let cursors = $state<(number | null)[]>([null]);
	let pageIndex = $state(0);

	let logs = $state<ActivityLog[]>([]);
	let loading = $state(true);
	let loadError = $state('');
	let hasMore = $state(false);

	let filterResourceType = $state('');
	let filterAction = $state('');
	let filterUserId = $state('');

	let refreshing = $state(false);
	let expandedId = $state<number | null>(null);
	let loadGeneration = 0;
	let loadController: AbortController | null = null;

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	async function load(reset = false, force = false) {
		const generation = ++loadGeneration;
		loadController?.abort();
		const controller = new AbortController();
		loadController = controller;
		const requestToken = token;
		const requestProjectId = projectId;
		const requestEndpoint = endpoint;
		const owns = () => generation === loadGeneration && token === requestToken && projectId === requestProjectId && endpoint === requestEndpoint;
		if (!requestToken || !requestProjectId) { logs = []; loading = false; refreshing = false; return; }
		if (reset) { cursors = [null]; pageIndex = 0; expandedId = null; }
		const size = Number(pageSize);
		const cursor = cursors[pageIndex];
		const params: Record<string, string> = { limit: String(size + 1) };
		if (cursor != null) params.before_id = String(cursor);
		if (filterResourceType) params.resource_type = filterResourceType;
		if (filterAction) params.action = filterAction;
		if (showUser && filterUserId) params.user_id = filterUserId;
		if (reset) { loading = true; logs = []; }
		else refreshing = true;
		loadError = '';
		try {
			const data = await api.get<ActivityLog[]>(
				`${requestEndpoint}${requestEndpoint.includes('?') ? '&' : '?'}${new URLSearchParams(params)}`,
				requestToken,
				requestProjectId,
				{ signal: controller.signal, refresh: force },
			);
			if (!owns()) return;
			logs = data.slice(0, size);
			hasMore = data.length > size;
		} catch (error) {
			if (
				owns()
				&& !(error instanceof DOMException && error.name === 'AbortError')
			) {
				logs = [];
				hasMore = false;
				loadError = error instanceof ApiError ? error.message : t('activity.loadFailed');
			}
		} finally {
			if (owns()) {
				loading = false;
				refreshing = false;
			}
		}
	}

	function previousPage() {
		if (pageIndex <= 0 || loading || refreshing) return;
		pageIndex -= 1;
		loading = true;
		logs = [];
		expandedId = null;
		void load();
	}

	function nextPage() {
		if (!hasMore || loading || refreshing || logs.length === 0) return;
		cursors = [...cursors.slice(0, pageIndex + 1), logs[logs.length - 1].id];
		pageIndex += 1;
		loading = true;
		logs = [];
		expandedId = null;
		void load();
	}

	const ar = createAutoRefresh((force) => load(false, force), {
		storageKey: untrack(() => storageKey),
		defaultActive: true,
		defaultInterval: 30,
		intervalOptions: [15, 30, 60],
		invokeOnMount: false,
	});

	$effect(() => {
		void $auth.projectId;
		void $auth.token;
		void $auth.userId;
		void pageSize;
		void filterResourceType;
		void filterAction;
		void filterUserId;
		void endpoint;
		loadGeneration += 1;
		loadController?.abort();
		logs = [];
		hasMore = false;
		loading = true;
		loadError = '';
		cursors = [null];
		pageIndex = 0;
		const timer = setTimeout(() => void load(true), 250);
		return () => {
			loadGeneration += 1;
			clearTimeout(timer);
			loadController?.abort();
		};
	});

	function relativeTime(iso: string): string {
		const diff = Date.now() - new Date(iso).getTime();
		const s = Math.floor(diff / 1000);
		if (s < 60) return t('activity.secondsAgo', { count: s });
		const m = Math.floor(s / 60);
		if (m < 60) return t('activity.minutesAgo', { count: m });
		const h = Math.floor(m / 60);
		if (h < 24) return t('activity.hoursAgo', { count: h });
		return t('activity.daysAgo', { count: Math.floor(h / 24) });
	}


	const RESOURCE_TYPES = [
		'instance', 'hypervisor', 'keypair', 'volume', 'volume_snapshot', 'volume_backup',
		'file_storage', 'share_snapshot', 'share_network', 'security_service',
		'network', 'subnet', 'router', 'floating_ip', 'security_group', 'load_balancer',
		'lb_listener', 'lb_pool', 'lb_member', 'lb_health_monitor',
		'k3s_cluster', 'container', 'container_cluster', 'library', 'union_layer',
	];
</script>

<div class="space-y-4">
	<!-- 필터 + 자동갱신 -->
	<div class="flex flex-wrap gap-3 items-center">
		<select
			bind:value={filterResourceType}
			class="bg-surface-sunken border border-line-2 rounded-lg px-3 py-1.5 text-sm text-ink-0 focus:outline-none focus:border-action-warm"
		>
			<option value="">{t('activity.allResources')}</option>
			{#each RESOURCE_TYPES as rt}
				<option value={rt}>{rt}</option>
			{/each}
		</select>
		<input
			bind:value={filterAction}
			type="text"
			placeholder={t('activity.actionFilter')}
			class="bg-surface-sunken border border-line-2 rounded-lg px-3 py-1.5 text-sm text-ink-0 focus:outline-none focus:border-action-warm w-52"
		/>
		{#if showUser}
			<input
				bind:value={filterUserId}
				type="text"
				placeholder={t('activity.userId')}
				class="bg-surface-sunken border border-line-2 rounded-lg px-3 py-1.5 text-sm text-ink-0 focus:outline-none focus:border-action-warm w-44"
			/>
		{/if}
		<div class="ml-auto">
			<AutoRefreshControl
				bind:active={ar.active}
				bind:intervalSeconds={ar.intervalSeconds}
				intervalOptions={ar.intervalOptions}
				{refreshing}
				onManualRefresh={ar.refresh}
			/>
		</div>
	</div>

	<div class="flex items-center gap-2 text-xs text-ink-2">
		<label for={`${storageKey}-page-size`}>{t('activity.pageSize')}</label>
		<SelectInput id={`${storageKey}-page-size`} bind:value={pageSize} class="max-w-28">
			{#each [10, 15, 20] as count}<option value={String(count)}>{t('activity.pageSizeCount', { count })}</option>{/each}
		</SelectInput>
	</div>

	<!-- 테이블 -->
	{#if loading}
		<div class="text-ink-2 text-sm py-8 text-center">{t('activity.loading')}</div>
	{:else if loadError}
		<Alert tone="danger">{loadError}</Alert>
	{:else if logs.length === 0}
		<div class="text-ink-2 text-sm py-8 text-center">{t('activity.empty')}</div>
	{:else}
		<ResponsiveTable>
			{#snippet cards()}
				{#each logs as log (log.id)}
					{#snippet errorAction()}
						<button onclick={() => expandedId = expandedId === log.id ? null : log.id} aria-expanded={expandedId === log.id} class="text-xs text-ink-2 underline">{expandedId === log.id ? t('activity.close') : t('activity.details')}</button>
						{#if expandedId === log.id && log.error_message}
							<p class="w-full rounded border border-state-danger/30 bg-state-danger/10 px-2 py-1.5 text-xs text-state-danger-text break-words">{log.error_message}</p>
						{/if}
					{/snippet}
					<CompactResourceCard actions={log.status === 'failed' && log.error_message ? errorAction : undefined}>
						<div class="flex min-w-0 items-start justify-between gap-2">
							<span class="min-w-0 font-medium break-words">{log.resource_name || log.resource_id || log.resource_type}</span>
							<StatusChip status={log.status} />
						</div>
						<dl>
							<div><dt>{t('activity.action')}</dt><dd class="font-mono">{log.action}</dd></div>
							<div><dt>{t('activity.time')}</dt><dd title={log.created_at}>{relativeTime(log.created_at)}</dd></div>
							{#if showUser}<div><dt>{t('activity.user')}</dt><dd>{log.username}</dd></div>{/if}
						</dl>
						{#snippet details()}
							<dl>
								<div><dt>{t('activity.resource')}</dt><dd>{log.resource_type}</dd></div>
								<div><dt>{t('activity.time')}</dt><dd>{log.created_at}</dd></div>
								{#if log.resource_id}<div><dt>ID</dt><dd class="font-mono">{log.resource_id}</dd></div>{/if}
							</dl>
						{/snippet}
					</CompactResourceCard>
				{/each}
			{/snippet}
		<TableShell density="compact">
			<table class="w-full text-sm">
				<thead class="bg-surface-base text-ink-2 text-xs uppercase tracking-wide">
					<tr>
						<th class="px-4 py-3 text-left font-medium">{t('activity.time')}</th>
						{#if showUser}<th class="px-4 py-3 text-left font-medium">{t('activity.user')}</th>{/if}
						<th class="px-4 py-3 text-left font-medium">{t('activity.resource')}</th>
						<th class="px-4 py-3 text-left font-medium">{t('activity.action')}</th>
						<th class="px-4 py-3 text-left font-medium">{t('activity.status')}</th>
					</tr>
				</thead>
				<tbody class="divide-y divide-line">
					{#each logs as log (log.id)}
						<tr class="hover:bg-surface-sunken/40 transition-colors">
							<td class="px-4 py-3 text-ink-2 whitespace-nowrap" title={log.created_at}>
								{relativeTime(log.created_at)}
							</td>
							{#if showUser}
								<td class="px-4 py-3 text-ink-2">{log.username}</td>
							{/if}
							<td class="px-4 py-3 text-ink-2">
								<span class="text-ink-2 text-xs">{log.resource_type}</span>
								{#if log.resource_name}
									<span class="ml-1 text-ink-0">{log.resource_name}</span>
								{:else if log.resource_id}
									<span class="ml-1 font-mono text-xs text-ink-2">{log.resource_id.slice(0, 8)}</span>
								{/if}
							</td>
							<td class="px-4 py-3 font-mono text-xs text-ink-2">{log.action}</td>
							<td class="px-4 py-3">
								<div class="flex items-center gap-2">
									<StatusChip status={log.status} />
									{#if log.status === 'failed' && log.error_message}
										<button
											onclick={() => expandedId = expandedId === log.id ? null : log.id}
											class="text-ink-2 hover:text-ink-2 text-xs underline"
										>
											{expandedId === log.id ? t('activity.close') : t('activity.details')}
										</button>
									{/if}
								</div>
								{#if expandedId === log.id && log.error_message}
									<div class="mt-2 text-xs text-state-danger-text bg-state-danger/10 border border-state-danger/30 rounded px-2 py-1.5 max-w-xs break-words">
										{log.error_message}
									</div>
								{/if}
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</TableShell>
		</ResponsiveTable>

	{/if}
	{#if !loading && (pageIndex > 0 || logs.length > 0)}
		<Pagination page={pageIndex + 1} hasPrev={pageIndex > 0 && !refreshing} hasNext={hasMore && !refreshing} onPrev={previousPage} onNext={nextPage} />
	{/if}
</div>
