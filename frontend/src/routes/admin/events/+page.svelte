<script lang="ts">
	import { onDestroy, untrack } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import { Alert, Button, Card, Field, PageHeader, PageShell, Pill, SelectInput, TableShell, TextInput } from '$lib/components/ui';
	import SlidePanel from '$lib/components/SlidePanel.svelte';

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
	const dimensions: { key: Dimension; label: string }[] = [
		{ key: 'by_service', label: '서비스별 실패' },
		{ key: 'by_project', label: '프로젝트별 실패' },
		{ key: 'by_action', label: '액션별 실패' },
		{ key: 'by_page', label: '페이지별 실패' },
	];
	const limit = 50;
	const eventDate = new Intl.DateTimeFormat('ko-KR', { year: 'numeric', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', second: '2-digit', timeZoneName: 'short' });
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
		return error instanceof ApiError ? error.message : '서버에 연결하지 못했습니다. 잠시 후 다시 시도하세요.';
	}
	function date(value: string): string {
		const timestamp = new Date(value);
		return Number.isNaN(timestamp.getTime()) ? value : eventDate.format(timestamp);
	}
	function detailFields(row: EventRecord): [string, string | number | null | undefined][] {
		return [
			['시각', date(row.created_at)], ['프로젝트 ID', row.project_id], ['사용자', row.username],
			['사용자 ID', row.user_id], ['서비스', row.service], ['페이지 경로', row.page],
			['출처', row.source], ['상태', row.status], ['HTTP 상태', row.http_status],
			['리소스 유형', row.resource_type], ['리소스 이름', row.resource_name], ['리소스 ID', row.resource_id],
			['액션', row.action], ['이벤트 유형', row.event_type], ['요청 ID', row.request_id],
			['외부 이벤트 ID', row.external_id], ['오류 유형', row.extra?.error_type], ['오류 코드', row.extra?.error_code],
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
	<PageHeader breadcrumb="시스템 / 이벤트" title="운영 이벤트">
		{#snippet actions()}
			<Button variant="secondary" onclick={refresh} disabled={loading || moreLoading}>새로고침</Button>
		{/snippet}
	</PageHeader>
	<p class="mb-6 text-sm text-ink-2">수집된 이벤트만 표시됩니다. OpenStack 알림은 구성된 서비스에서 발행한 경우에만 포함됩니다.</p>

	<Card surface="base" class="mb-6">
		<form onsubmit={apply} aria-label="이벤트 필터">
			<div class="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
				<Field label="기간" for="event-range">
					<SelectInput id="event-range" bind:value={range}><option value="1d">최근 24시간</option><option value="7d">최근 7일</option><option value="30d">최근 30일</option></SelectInput>
				</Field>
				<Field label="프로젝트 ID" for="event-project"><TextInput id="event-project" bind:value={project} /></Field>
				<Field label="사용자 ID" for="event-user"><TextInput id="event-user" bind:value={user} /></Field>
				<Field label="사용자 이름" for="event-username"><TextInput id="event-username" bind:value={username} /></Field>
				<Field label="서비스" for="event-service"><TextInput id="event-service" bind:value={service} /></Field>
				<Field label="페이지 경로" for="event-page"><TextInput id="event-page" bind:value={pageFilter} placeholder="/admin/instances" /></Field>
				<Field label="리소스 유형" for="event-resource"><TextInput id="event-resource" bind:value={resource} /></Field>
				<Field label="리소스 ID" for="event-resource-id"><TextInput id="event-resource-id" bind:value={resourceId} /></Field>
				<Field label="액션" for="event-action"><TextInput id="event-action" bind:value={action} /></Field>
				<Field label="상태" for="event-status"><SelectInput id="event-status" bind:value={status}><option value="">전체</option><option value="started">진행 중</option><option value="success">성공</option><option value="failed">실패</option></SelectInput></Field>
				<Field label="출처" for="event-source"><SelectInput id="event-source" bind:value={source}><option value="">전체</option><option value="afterglow">Afterglow</option><option value="openstack">OpenStack</option></SelectInput></Field>
			</div>
			<div class="mt-4 flex flex-wrap gap-2"><Button type="submit">필터 적용</Button><Button type="button" variant="secondary" onclick={reset}>초기화</Button></div>
		</form>
	</Card>

	<section aria-label="실패 분석" class="mb-6">
		<h2 class="mb-3 text-base font-semibold text-ink-0">실패 분석</h2>
		{#if statsError}<Alert tone="danger" title="실패 분석을 불러오지 못했습니다">{statsError}</Alert>{/if}
		{#if stats && !statsLoading && !statsError}<p class="mb-3 text-sm tabular-nums text-ink-2">전체 {stats.total}건 · 실패 {stats.failed}건 · 성공 {stats.success}건 · 진행 중 {stats.started}건</p>{/if}
		{#if statsLoading}<p role="status" class="text-sm text-ink-2">실패 분석을 불러오는 중…</p>
		{:else if !statsError}
			<div class="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
				{#each dimensions as dimension}
					<Card surface="base">
						<h3 class="mb-3 text-sm font-semibold text-ink-0">{dimension.label}</h3>
						{#if !stats || stats[dimension.key].every((item) => item.failed === 0)}<p class="text-sm text-ink-2">해당 기간에 기록된 실패가 없습니다.</p>
						{:else}<ol class="space-y-2">
							{#each stats[dimension.key].filter((item) => item.failed > 0) as item (item.key)}
								<li class="flex min-w-0 justify-between gap-3 text-sm"><span class="min-w-0 break-all text-ink-1">{item.key || '알 수 없음'}</span><span class="shrink-0 tabular-nums text-state-danger-text">{item.failed}건</span></li>
							{/each}
						</ol>{/if}
					</Card>
				{/each}
			</div>
		{/if}
	</section>

	<section aria-label="이벤트 목록">
		<h2 class="mb-3 text-base font-semibold text-ink-0">이벤트 목록</h2>
		{#if listError}<Alert tone="danger" title="이벤트를 불러오지 못했습니다">{listError} <Button variant="secondary" size="sm" onclick={retryList}>다시 시도</Button></Alert>{/if}
		{#if loading}<p role="status" class="text-sm text-ink-2">이벤트를 불러오는 중…</p>
		{:else if events.length === 0 && !listError}<Card surface="base"><p class="text-sm text-ink-2">조건에 맞는 이벤트가 없습니다.</p></Card>
		{:else if events.length > 0}
			<TableShell>
				<table><thead><tr><th scope="col">시각</th><th scope="col">상태</th><th scope="col">서비스 / 출처</th><th scope="col">프로젝트 / 사용자</th><th scope="col">리소스</th><th scope="col">액션</th><th scope="col">상세</th></tr></thead>
					<tbody>{#each events as row (row.id)}
						<tr><td class="whitespace-nowrap tabular-nums">{date(row.created_at)}</td><td><Pill tone={row.status === 'failed' ? 'danger' : row.status === 'success' ? 'success' : row.status === 'started' ? 'info' : 'neutral'}>{row.status === 'failed' ? '실패' : row.status === 'success' ? '성공' : row.status === 'started' ? '진행 중' : row.status}</Pill></td>
						<td>{row.service || '알 수 없음'} <span class="text-ink-2">/ {row.source}</span></td><td><span class="block max-w-40 truncate" title={row.project_id}>{row.project_id || '알 수 없음'}</span><span class="block max-w-40 truncate text-ink-2" title={row.username || row.user_id}>{row.username || row.user_id || '알 수 없음'}</span></td>
						<td><span class="block max-w-40 truncate" title={row.resource_name || row.resource_type}>{row.resource_name || row.resource_type}</span><span class="block text-ink-2">{row.resource_type}</span></td><td>{row.action}</td><td><Button variant="secondary" size="sm" onclick={() => showDetail(row)} ariaLabel={`${row.action} 이벤트 ${row.id} 상세 보기`}>상세 보기</Button></td></tr>
					{/each}</tbody></table>
			</TableShell>
			{#if cursor}<div class="mt-4 flex justify-center"><Button variant="secondary" disabled={moreLoading || !!listError} onclick={loadMore}>{moreLoading ? '불러오는 중…' : '더 보기'}</Button></div>{/if}
		{/if}
	</section>

	{#if selected}
		<SlidePanel onClose={closeDetail} ariaLabel={`이벤트 상세 ${selected.id}`} width="w-full md:w-[60vw] max-w-3xl" resizable={false}>
			<div class="p-4 md:p-6">
				<h2 class="mb-4 text-base font-semibold">이벤트 상세 #{selected.id}</h2>
				{#if detailLoading}<p role="status" class="text-sm text-ink-2">상세 정보를 불러오는 중…</p>{/if}
				{#if detailError}<Alert tone="danger" title="이벤트 상세를 불러오지 못했습니다">{detailError} <Button variant="secondary" size="sm" onclick={() => selected && showDetail(selected)}>다시 시도</Button></Alert>{/if}
				{#if !detailLoading && !detailError}
					<dl class="grid grid-cols-1 gap-x-6 gap-y-3 text-sm md:grid-cols-2">
						{#each detailFields(selected) as field}
							<div class="min-w-0"><dt class="text-ink-2">{field[0]}</dt><dd class="mt-1 break-all font-mono text-ink-0">{field[1] ?? '—'}</dd></div>
						{/each}
					</dl>
					<h3 class="mt-5 mb-2 text-sm font-semibold">오류 메시지</h3><p class="whitespace-pre-wrap break-words rounded-md border border-line bg-surface-sunken p-3 text-sm text-ink-1">{selected.error_message || (selected.source === 'openstack' ? 'OpenStack 알림의 원문 오류는 수집하지 않습니다. 기록된 오류 유형·코드를 확인하세요.' : '기록된 오류 메시지가 없습니다.')}</p>
				{/if}
			</div>
		</SlidePanel>
	{/if}
</PageShell>
