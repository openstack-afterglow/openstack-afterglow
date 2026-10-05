<script lang="ts">
	import { onDestroy, untrack } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import { Alert, Button, Card, Field, PageHeader, PageShell, Pill, SelectInput, TableShell, TextInput } from '$lib/components/ui';
	import SlidePanel from '$lib/components/SlidePanel.svelte';
	import { t } from '$lib/i18n/ns/admin-ops';
	import { intlLocale } from '$lib/i18n/runtime.svelte';

	interface EventRecord {
		id: number;
		created_at: string;
		project_id: string;
		user_id: string;
		username: string;
		service: string | null;
		page?: string | null;
		source: string;
		resource_type: string;
		resource_id: string | null;
		resource_name: string | null;
		action: string;
		status: string;
		error_message: string | null;
		request_id?: string | null;
		external_id?: string | null;
		event_type?: string | null;
		http_status?: number | null;
		// Only these explicit, backend-sanitized metadata fields may reach the UI.
		extra?: { error_type?: string | null; error_code?: string | number | null } | null;
	}
	interface FailureGroup { key: string | null; total: number; failed: number }
	interface EventStats {
		total: number; success: number; failed: number; started: number;
		by_service: FailureGroup[]; by_project: FailureGroup[]; by_action: FailureGroup[]; by_page: FailureGroup[];
	}
	type Dimension = 'by_service' | 'by_project' | 'by_action' | 'by_page';
	const dimensions: { key: Dimension; labelKey: Parameters<typeof t>[0] }[] = [
		{ key: 'by_service', labelKey: 'events.failuresByService' },
		{ key: 'by_project', labelKey: 'events.failuresByProject' },
		{ key: 'by_action', labelKey: 'events.failuresByAction' },
		{ key: 'by_page', labelKey: 'events.failuresByPage' },
	];
	const limit = 50;
	const eventDate = $derived(new Intl.DateTimeFormat(intlLocale(), { year: 'numeric', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', second: '2-digit', timeZoneName: 'short' }));
	const base = '/api/v1/admin/events';

	let range = $state('7d');
	let project = $state('');
	let user = $state('');
	let username = $state('');
	let service = $state('');
	let pageFilter = $state('');
	let resource = $state('');
	let resourceId = $state('');
	let action = $state('');
	let status = $state('');
	let source = $state('');
	let applied = $state('');
	let events = $state<EventRecord[]>([]);
	let cursor = $state<number | null>(null);
	let loading = $state(false);
	let moreLoading = $state(false);
	let listError = $state<string | null>(null);
	let stats = $state<EventStats | null>(null);
	let statsLoading = $state(false);
	let statsError = $state<string | null>(null);
	let selected = $state<EventRecord | null>(null);
	let detailLoading = $state(false);
	let detailError = $state<string | null>(null);
	let generation = 0;
	let detailGeneration = 0;

	function query(): string {
		const now = new Date();
		const params = new URLSearchParams({ from_at: new Date(now.getTime() - Number.parseInt(range, 10) * 86_400_000).toISOString(), to_at: now.toISOString(), limit: String(limit) });
		for (const [key, value] of Object.entries({ project_id: project, user_id: user, username, service, page: pageFilter, resource_type: resource, resource_id: resourceId, action, status, source })) {
			if (value.trim()) params.set(key, value.trim());
		}
		return params.toString();
	}
	function message(error: unknown): string {
		return error instanceof ApiError ? error.message : t('events.connectionFailed');
	}
	function date(value: string): string {
		const timestamp = new Date(value);
		return Number.isNaN(timestamp.getTime()) ? value : eventDate.format(timestamp);
	}
	function detailFields(row: EventRecord): [string, string | number | null | undefined][] {
		return [
			[t('events.time'), date(row.created_at)], [t('events.projectId'), row.project_id], [t('events.user'), row.username],
			[t('events.userId'), row.user_id], [t('events.service'), row.service], [t('events.pagePath'), row.page],
			[t('events.source'), row.source], [t('events.status'), row.status], [t('events.httpStatus'), row.http_status],
			[t('events.resourceType'), row.resource_type], [t('events.resourceName'), row.resource_name], [t('events.resourceId'), row.resource_id],
			[t('events.action'), row.action], [t('events.eventType'), row.event_type], [t('events.requestId'), row.request_id],
			[t('events.externalId'), row.external_id], [t('events.errorType'), row.extra?.error_type], [t('events.errorCode'), row.extra?.error_code],
		];
	}

	async function loadNext(requestGeneration: number, filters: string, token: string, projectId: string | undefined, next?: number) {
		const owns = () => requestGeneration === generation && $auth.token === token && ($auth.projectId ?? undefined) === projectId;
		if (next) moreLoading = true;
		else loading = true;
		listError = null;
		try {
			const params = new URLSearchParams(filters);
			if (next) params.set('before_id', String(next));
			const rows = await api.get<EventRecord[]>(`${base}?${params}`, token, projectId);
			if (!owns()) return;
			events = next ? [...events, ...rows] : rows;
			cursor = rows.length === limit ? rows[rows.length - 1].id : null;
		} catch (error) {
			if (owns()) listError = message(error);
		} finally {
			if (owns()) { loading = false; moreLoading = false; }
		}
	}

	async function loadStats(requestGeneration: number, filters: string, token: string, projectId: string | undefined) {
		const owns = () => requestGeneration === generation && $auth.token === token && ($auth.projectId ?? undefined) === projectId;
		statsLoading = true;
		statsError = null;
		const params = new URLSearchParams(filters);
		params.delete('limit');
		try {
			const result = await api.get<EventStats>(`${base}/stats?${params}`, token, projectId);
			if (owns()) stats = result;
		} catch (error) {
			if (owns()) statsError = message(error);
		} finally {
			if (owns()) statsLoading = false;
		}
	}

	function reload(filters = applied) {
		const requestGeneration = ++generation;
		++detailGeneration;
		selected = null;
		detailError = null;
		events = [];
		cursor = null;
		stats = null;
		listError = null;
		statsError = null;
		loading = false;
		moreLoading = false;
		statsLoading = false;
		const token = $auth.token;
		if (!token) return;
		const projectId = $auth.projectId ?? undefined;
		void loadNext(requestGeneration, filters, token, projectId);
		void loadStats(requestGeneration, filters, token, projectId);
	}

	function refresh() {
		const params = new URLSearchParams(applied);
		const duration = Date.parse(params.get('to_at')!) - Date.parse(params.get('from_at')!);
		const now = Date.now();
		params.set('from_at', new Date(now - duration).toISOString());
		params.set('to_at', new Date(now).toISOString());
		applied = params.toString();
		reload(applied);
	}

	function apply(event: SubmitEvent) {
		event.preventDefault();
		applied = query();
		reload(applied);
	}
	function reset() {
		range = '7d'; project = ''; user = ''; username = ''; service = ''; pageFilter = ''; resource = ''; resourceId = ''; action = ''; status = ''; source = '';
		applied = query();
		reload(applied);
	}
	function loadMore() {
		if (!cursor || loading || moreLoading || listError) return;
		const token = $auth.token;
		if (token) void loadNext(generation, applied, token, $auth.projectId ?? undefined, cursor);
	}
	function retryList() {
		if (cursor !== null && events.length) {
			listError = null;
			loadMore();
		} else reload();
	}
	function closeDetail() {
		++detailGeneration;
		selected = null;
		detailError = null;
	}
	async function showDetail(row: EventRecord) {
		const current = ++detailGeneration;
		selected = row;
		detailLoading = true;
		detailError = null;
		const token = $auth.token;
		const projectId = $auth.projectId ?? undefined;
		if (!token) return;
		try {
			const full = await api.get<EventRecord>(`${base}/${row.id}`, token, projectId);
			if (current === detailGeneration && $auth.token === token && ($auth.projectId ?? undefined) === projectId) selected = full;
		} catch (error) {
			if (current === detailGeneration) detailError = message(error);
		} finally {
			if (current === detailGeneration) detailLoading = false;
		}
	}

	$effect(() => {
		// The global event feed must never display data from an earlier login or project context.
		void $auth.token;
		void $auth.projectId;
		untrack(() => {
			const filters = query();
			applied = filters;
			reload(filters);
		});
	});
	onDestroy(() => { ++generation; ++detailGeneration; });
</script>

<PageShell>
	<PageHeader breadcrumb={t('events.breadcrumb')} title={t('events.title')}>
		{#snippet actions()}
			<Button variant="secondary" onclick={refresh} disabled={loading || moreLoading}>{t('events.refresh')}</Button>
		{/snippet}
	</PageHeader>
	<p class="mb-6 text-sm text-ink-2">{t('events.collectionNotice')}</p>

	<Card surface="base" class="mb-6">
		<form onsubmit={apply} aria-label={t('events.filters')}>
			<div class="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
				<Field label={t('events.period')} for="event-range">
					<SelectInput id="event-range" bind:value={range}><option value="1d">{t('events.lastDay')}</option><option value="7d">{t('events.lastWeek')}</option><option value="30d">{t('events.lastMonth')}</option></SelectInput>
				</Field>
				<Field label={t('events.projectId')} for="event-project"><TextInput id="event-project" bind:value={project} /></Field>
				<Field label={t('events.userId')} for="event-user"><TextInput id="event-user" bind:value={user} /></Field>
				<Field label={t('events.username')} for="event-username"><TextInput id="event-username" bind:value={username} /></Field>
				<Field label={t('events.service')} for="event-service"><TextInput id="event-service" bind:value={service} /></Field>
				<Field label={t('events.pagePath')} for="event-page"><TextInput id="event-page" bind:value={pageFilter} placeholder="/admin/instances" /></Field>
				<Field label={t('events.resourceType')} for="event-resource"><TextInput id="event-resource" bind:value={resource} /></Field>
				<Field label={t('events.resourceId')} for="event-resource-id"><TextInput id="event-resource-id" bind:value={resourceId} /></Field>
				<Field label={t('events.action')} for="event-action"><TextInput id="event-action" bind:value={action} /></Field>
				<Field label={t('events.status')} for="event-status"><SelectInput id="event-status" bind:value={status}><option value="">{t('events.all')}</option><option value="started">{t('events.started')}</option><option value="success">{t('events.success')}</option><option value="failed">{t('events.failed')}</option></SelectInput></Field>
				<Field label={t('events.source')} for="event-source"><SelectInput id="event-source" bind:value={source}><option value="">{t('events.all')}</option><option value="afterglow">Afterglow</option><option value="openstack">OpenStack</option></SelectInput></Field>
			</div>
			<div class="mt-4 flex flex-wrap gap-2"><Button type="submit">{t('events.applyFilters')}</Button><Button type="button" variant="secondary" onclick={reset}>{t('events.reset')}</Button></div>
		</form>
	</Card>

	<section aria-label={t('events.failureAnalysis')} class="mb-6">
		<h2 class="mb-3 text-base font-semibold text-ink-0">{t('events.failureAnalysis')}</h2>
		{#if statsError}<Alert tone="danger" title={t('events.statsFailed')}>{statsError}</Alert>{/if}
		{#if stats && !statsLoading && !statsError}<p class="mb-3 text-sm tabular-nums text-ink-2">{t('events.statsSummary', { total: stats.total, failed: stats.failed, success: stats.success, started: stats.started })}</p>{/if}
		{#if statsLoading}<p role="status" class="text-sm text-ink-2">{t('events.statsLoading')}</p>
		{:else if !statsError}
			<div class="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
				{#each dimensions as dimension}
					<Card surface="base">
						<h3 class="mb-3 text-sm font-semibold text-ink-0">{t(dimension.labelKey)}</h3>
						{#if !stats || stats[dimension.key].every((item) => item.failed === 0)}<p class="text-sm text-ink-2">{t('events.noFailures')}</p>
						{:else}<ol class="space-y-2">
							{#each stats[dimension.key].filter((item) => item.failed > 0) as item (item.key)}
								<li class="flex min-w-0 justify-between gap-3 text-sm"><span class="min-w-0 break-all text-ink-1">{item.key || t('events.unknown')}</span><span class="shrink-0 tabular-nums text-state-danger-text">{t('events.count', { count: item.failed })}</span></li>
							{/each}
						</ol>{/if}
					</Card>
				{/each}
			</div>
		{/if}
	</section>

	<section aria-label={t('events.list')}>
		<h2 class="mb-3 text-base font-semibold text-ink-0">{t('events.list')}</h2>
		{#if listError}<Alert tone="danger" title={t('events.listFailed')}>{listError} <Button variant="secondary" size="sm" onclick={retryList}>{t('events.retry')}</Button></Alert>{/if}
		{#if loading}<p role="status" class="text-sm text-ink-2">{t('events.listLoading')}</p>
		{:else if events.length === 0 && !listError}<Card surface="base"><p class="text-sm text-ink-2">{t('events.noEvents')}</p></Card>
		{:else if events.length > 0}
			<TableShell>
				<table><thead><tr><th scope="col">{t('events.time')}</th><th scope="col">{t('events.status')}</th><th scope="col">{t('events.serviceSource')}</th><th scope="col">{t('events.projectUser')}</th><th scope="col">{t('events.resource')}</th><th scope="col">{t('events.action')}</th><th scope="col">{t('events.details')}</th></tr></thead>
					<tbody>{#each events as row (row.id)}
						<tr><td class="whitespace-nowrap tabular-nums">{date(row.created_at)}</td><td><Pill tone={row.status === 'failed' ? 'danger' : row.status === 'success' ? 'success' : row.status === 'started' ? 'info' : 'neutral'}>{row.status === 'failed' ? t('events.failed') : row.status === 'success' ? t('events.success') : row.status === 'started' ? t('events.started') : row.status}</Pill></td>
						<td>{row.service || t('events.unknown')} <span class="text-ink-2">/ {row.source}</span></td><td><span class="block max-w-40 truncate" title={row.project_id}>{row.project_id || t('events.unknown')}</span><span class="block max-w-40 truncate text-ink-2" title={row.username || row.user_id}>{row.username || row.user_id || t('events.unknown')}</span></td>
						<td><span class="block max-w-40 truncate" title={row.resource_name || row.resource_type}>{row.resource_name || row.resource_type}</span><span class="block text-ink-2">{row.resource_type}</span></td><td>{row.action}</td><td><Button variant="secondary" size="sm" onclick={() => showDetail(row)} ariaLabel={t('events.viewDetailsAria', { action: row.action, id: row.id })}>{t('events.viewDetails')}</Button></td></tr>
					{/each}</tbody></table>
			</TableShell>
			{#if cursor}<div class="mt-4 flex justify-center"><Button variant="secondary" disabled={moreLoading || !!listError} onclick={loadMore}>{moreLoading ? t('events.loading') : t('events.showMore')}</Button></div>{/if}
		{/if}
	</section>

	{#if selected}
		<SlidePanel onClose={closeDetail} ariaLabel={t('events.detailAria', { id: selected.id })} width="w-full md:w-[60vw] max-w-3xl" resizable={false}>
			<div class="p-4 md:p-6">
				<h2 class="mb-4 text-base font-semibold">{t('events.detailTitle', { id: selected.id })}</h2>
				{#if detailLoading}<p role="status" class="text-sm text-ink-2">{t('events.detailLoading')}</p>{/if}
				{#if detailError}<Alert tone="danger" title={t('events.detailFailed')}>{detailError} <Button variant="secondary" size="sm" onclick={() => selected && showDetail(selected)}>{t('events.retry')}</Button></Alert>{/if}
				{#if !detailLoading && !detailError}
					<dl class="grid grid-cols-1 gap-x-6 gap-y-3 text-sm md:grid-cols-2">
						{#each detailFields(selected) as field}
							<div class="min-w-0"><dt class="text-ink-2">{field[0]}</dt><dd class="mt-1 break-all font-mono text-ink-0">{field[1] ?? '—'}</dd></div>
						{/each}
					</dl>
					<h3 class="mt-5 mb-2 text-sm font-semibold">{t('events.errorMessage')}</h3><p class="whitespace-pre-wrap break-words rounded-md border border-line bg-surface-sunken p-3 text-sm text-ink-1">{selected.error_message || (selected.source === 'openstack' ? t('events.openstackErrorNotice') : t('events.noErrorMessage'))}</p>
				{/if}
			</div>
		</SlidePanel>
	{/if}
</PageShell>
