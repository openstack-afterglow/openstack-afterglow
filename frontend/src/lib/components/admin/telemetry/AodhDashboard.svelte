<script lang="ts">
	import { onMount } from 'svelte';
	import { Alert, Button, Card, Field, PageHeader, SelectInput, TableShell } from '$lib/components/ui';
	import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
	import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';
	import { adminTelemetryRequest, TelemetryError } from '$lib/api/adminTelemetry';
	import type { AodhDetail, AodhOverview, NativeAlarm, NativePage, TelemetryStatus } from '$lib/api/adminTelemetry';
	import { t } from '$lib/i18n/ns/admin-telemetry';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import { createTelemetryContext } from './context';
	import type { TelemetryContext } from './context';
	import NativeStatus from './NativeStatus.svelte';

	let context: TelemetryContext | undefined;
	let allowed = $state(false);
	let overview = $state<AodhOverview | null>(null);
	let overviewFailure = $state<TelemetryStatus | null>(null);
	let overviewLoading = $state(false);
	let page = $state<NativePage<NativeAlarm> | null>(null);
	let pageFailure = $state<TelemetryStatus | null>(null);
	let pageLoading = $state(false);
	let stateFilter = $state('');
	let markers = $state<(string | null)[]>([null]);
	let pageIndex = $state(0);
	let selectedId = $state<string | null>(null);
	let detail = $state<AodhDetail | null>(null);
	let detailFailure = $state<TelemetryStatus | null>(null);
	let detailLoading = $state(false);
	let overviewGeneration = 0;
	let pageGeneration = 0;
	let selectionGeneration = 0;
	let contextGeneration = 0;

	const knownStates = ['ok', 'alarm', 'insufficient data'] as const;
	const actionFields = ['alarm_actions', 'ok_actions', 'insufficient_data_actions'] as const;
	const ruleTypes = ['gnocchi_resources_threshold', 'gnocchi_aggregation_by_metrics_threshold', 'gnocchi_aggregation_by_resources_threshold', 'event', 'composite', 'loadbalancer_member_health', 'prometheus'];
	const verifiedPage = $derived(!pageLoading && page?.status === 'available');
	const counts = $derived(verifiedPage && page ? {
		loaded: page.items.length,
		ok: page.items.filter(alarm => alarm.state === 'ok').length,
		alarm: page.items.filter(alarm => alarm.state === 'alarm').length,
		insufficient: page.items.filter(alarm => alarm.state === 'insufficient data').length,
		unknown: page.items.filter(alarm => !knownStates.some(state => state === alarm.state)).length,
	} : null);
	const selectedAlarm = $derived(detail?.alarm ?? null);

	function failureStatus(error: unknown): TelemetryStatus {
		return error instanceof TelemetryError && error.status === 403 ? 'forbidden'
			: error instanceof TelemetryError && error.status === 404 ? 'not_found' : 'unavailable';
	}
	function number(value: number) { return new Intl.NumberFormat(intlLocale()).format(value); }
	function timestamp(value: unknown) {
		if (typeof value !== 'string' || !value) return t('aodh.notReported');
		const date = new Date(value);
		return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat(intlLocale(), { dateStyle: 'medium', timeStyle: 'medium' }).format(date);
	}
	function reported(value: unknown): string {
		return typeof value === 'boolean' ? t(value ? 'aodh.yes' : 'aodh.no')
			: typeof value === 'string' && value ? value : t('aodh.notReported');
	}
	function json(value: unknown): string { return value == null ? t('aodh.notReported') : JSON.stringify(value, null, 2); }
	function stateLabel(value: string | null | undefined) {
		return value === 'ok' ? t('aodh.ok') : value === 'alarm' ? t('aodh.alarm')
			: value === 'insufficient data' ? t('aodh.insufficientData') : reported(value);
	}
	function actionLabel(field: typeof actionFields[number]) {
		return field === 'alarm_actions' ? t('aodh.alarmActions') : field === 'ok_actions' ? t('aodh.okActions') : t('aodh.insufficientDataActions');
	}
	function query() {
		const params = new URLSearchParams({ limit: '25' });
		if (stateFilter) params.set('state', stateFilter);
		const marker = markers[pageIndex];
		if (marker) params.set('marker', marker);
		return params.toString();
	}
	function clearSelection() {
		++selectionGeneration;
		selectedId = null;
		detail = null;
		detailFailure = null;
		detailLoading = false;
	}
	function clearPage() {
		page = null;
		pageFailure = null;
		clearSelection();
	}
	async function loadOverview() {
		const ticket = context?.capture();
		if (!ticket) return;
		const generation = ++overviewGeneration;
		const listGeneration = ++pageGeneration;
		const params = query();
		overview = null;
		overviewFailure = null;
		overviewLoading = true;
		clearPage();
		pageLoading = true;
		try {
			const result = await adminTelemetryRequest<AodhOverview>(`/aodh?${params}`, ticket.authority);
			if (!ticket.current() || generation !== overviewGeneration) return;
			overview = result;
			if (listGeneration === pageGeneration) page = result.alarms;
		} catch (error) {
			if (!ticket.current() || generation !== overviewGeneration) return;
			overviewFailure = failureStatus(error);
			if (listGeneration === pageGeneration) pageFailure = failureStatus(error);
		} finally {
			if (ticket.current() && generation === overviewGeneration) overviewLoading = false;
			if (ticket.current() && listGeneration === pageGeneration) pageLoading = false;
		}
	}
	async function loadPage() {
		const ticket = context?.capture();
		if (!ticket) return;
		const generation = ++pageGeneration;
		const params = query();
		clearPage();
		pageLoading = true;
		try {
			const result = await adminTelemetryRequest<NativePage<NativeAlarm>>(`/aodh/alarms?${params}`, ticket.authority);
			if (ticket.current() && generation === pageGeneration) page = result;
		} catch (error) {
			if (ticket.current() && generation === pageGeneration) pageFailure = failureStatus(error);
		} finally {
			if (ticket.current() && generation === pageGeneration) pageLoading = false;
		}
	}
	function filterChanged(event: Event) {
		stateFilter = (event.currentTarget as HTMLSelectElement).value;
		markers = [null];
		pageIndex = 0;
		void loadPage();
	}
	function nextPage() {
		if (pageLoading || !page?.items.length || !page.next_marker) return;
		markers = [...markers.slice(0, pageIndex + 1), page.next_marker];
		++pageIndex;
		void loadPage();
	}
	function previousPage() {
		if (pageLoading || pageIndex === 0) return;
		--pageIndex;
		void loadPage();
	}
	async function selectAlarm(id: string) {
		const ticket = context?.capture();
		if (!ticket) return;
		const generation = ++selectionGeneration;
		selectedId = id;
		detail = null;
		detailFailure = null;
		detailLoading = true;
		try {
			const result = await adminTelemetryRequest<AodhDetail>(`/aodh/alarms/${encodeURIComponent(id)}`, ticket.authority);
			if (ticket.current() && generation === selectionGeneration && selectedId === id) detail = result;
		} catch (error) {
			if (ticket.current() && generation === selectionGeneration && selectedId === id) detailFailure = failureStatus(error);
		} finally {
			if (ticket.current() && generation === selectionGeneration && selectedId === id) detailLoading = false;
		}
	}

	onMount(() => {
		context = createTelemetryContext(() => {
			const generation = ++contextGeneration;
			++overviewGeneration;
			++pageGeneration;
			overview = null;
			overviewFailure = null;
			overviewLoading = false;
			clearPage();
			pageLoading = false;
			stateFilter = '';
			markers = [null];
			pageIndex = 0;
			allowed = context?.allowed() ?? false;
			queueMicrotask(() => {
				if (generation === contextGeneration && context?.allowed()) void loadOverview();
			});
		});
		allowed = context.allowed();
		void loadOverview();
		return () => { ++contextGeneration; context?.dispose(); };
	});
</script>

<PageHeader breadcrumb={t('aodh.breadcrumb')} title={t('aodh.title')} subtitle={t('aodh.description')}>
	{#snippet actions()}
		<Button variant="secondary" disabled={!allowed || overviewLoading || pageLoading} onclick={() => void loadOverview()}>{t('refresh')}</Button>
		<Button variant="secondary" href="/admin/monitoring/gnocchi">{t('aodh.gnocchi')}</Button>
		<Button variant="secondary" href="/admin/monitoring/aodh/settings" disabled={!allowed}>{t('aodh.settings')}</Button>
		<Button href="/admin/monitoring/aodh/settings?create=1" disabled={!allowed}>{t('aodh.create')}</Button>
	{/snippet}
</PageHeader>

<div class="space-y-4 min-w-0">
	{#if !allowed}
		<Alert tone="neutral">{t('aodh.authorityRequired')}</Alert>
	{:else}
		<section aria-label={t('aodh.overview')} class="space-y-3">
			<Card>
				<h2 class="text-sm font-semibold text-ink-0 mb-2">{t('aodh.overview')}</h2>
				{#if overviewLoading}<p role="status" class="text-sm text-ink-2">{t('loading')}</p>
				{:else if overviewFailure}<NativeStatus status={overviewFailure} />
					<Button variant="secondary" class="mt-2" onclick={() => void loadOverview()}>{t('retry')}</Button>
				{:else if overview}
					<NativeStatus status={overview.status} error={overview.error} />
					<p class="text-xs text-ink-2 mt-2">{t('checkedAt')}: {timestamp(overview.checked_at)}</p>
				{/if}
			</Card>
			<Card>
				<h2 class="text-sm font-semibold text-ink-0 mb-2">{t('aodh.capabilities')}</h2>
				<p class="text-xs text-ink-2 mb-2">{t('aodh.capabilitiesHelp')}</p>
				{#if overviewLoading}<p role="status" class="text-sm text-ink-2">{t('loading')}</p>
				{:else if overview}
					<NativeStatus status={overview.capabilities.status} error={overview.capabilities.error} />
					{#if overview.capabilities.data && Object.keys(overview.capabilities.data).length}
						<pre class="native-json mt-2">{json(overview.capabilities.data)}</pre>
					{:else if overview.capabilities.status === 'available'}<p class="text-sm text-ink-2 mt-2">{t('aodh.noCapabilities')}</p>{/if}
				{:else if overviewFailure}<NativeStatus status={overviewFailure} />{/if}
			</Card>
		</section>

		<section aria-label={t('aodh.alarms')} class="space-y-3">
			<div class="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
				<h2 class="text-sm font-semibold text-ink-0">{t('aodh.alarms')}</h2>
				<Field label={t('aodh.filter')} for="aodh-state-filter" class="w-full md:w-64">
					<SelectInput id="aodh-state-filter" bind:value={stateFilter} onchange={filterChanged}>
						<option value="">{t('aodh.allStates')}</option><option value="ok">{t('aodh.ok')}</option><option value="alarm">{t('aodh.alarm')}</option><option value="insufficient data">{t('aodh.insufficientData')}</option>
					</SelectInput>
				</Field>
			</div>
			<Card>
				<section aria-label={t('aodh.loadedCounts')}>
					<h3 class="text-sm font-medium text-ink-0">{t('aodh.loadedCounts')}</h3>
					<p class="text-xs text-ink-2 mt-1">{t('aodh.loadedCountsHelp')}</p>
					{#if counts}
						<dl class="mt-3 grid grid-cols-2 gap-3 md:grid-cols-5 tabular-nums">
							<div><dt class="text-xs text-ink-2">{t('aodh.loaded')}</dt><dd class="text-sm text-ink-0">{number(counts.loaded)}</dd></div>
							<div><dt class="text-xs text-ink-2">{t('aodh.ok')}</dt><dd class="text-sm text-ink-0">{number(counts.ok)}</dd></div>
							<div><dt class="text-xs text-ink-2">{t('aodh.alarm')}</dt><dd class="text-sm text-ink-0">{number(counts.alarm)}</dd></div>
							<div><dt class="text-xs text-ink-2">{t('aodh.insufficientData')}</dt><dd class="text-sm text-ink-0">{number(counts.insufficient)}</dd></div>
							<div><dt class="text-xs text-ink-2">{t('aodh.unknownState')}</dt><dd class="text-sm text-ink-0">{number(counts.unknown)}</dd></div>
						</dl>
					{:else}<p class="text-sm text-ink-2 mt-2">{t('aodh.countsUnknown')}</p>{/if}
				</section>
			</Card>
			{#if pageLoading}<p role="status" class="text-sm text-ink-2">{t('loading')}</p>
			{:else if pageFailure}<NativeStatus status={pageFailure} /><Button variant="secondary" onclick={() => void loadPage()}>{t('retry')}</Button>
			{:else if page}
				<NativeStatus status={page.status} error={page.error} />
				{#if page.items.length}
					{@const alarmItems = page.items}
					<ResponsiveTable>
						{#snippet cards()}
							{#each alarmItems as alarm (alarm.alarm_id)}
								<CompactResourceCard selected={selectedId === alarm.alarm_id}>
									<Button variant="link" ariaLabel={t('aodh.selectNamed', { name: alarm.name || alarm.alarm_id })} ariaPressed={selectedId === alarm.alarm_id} onclick={() => void selectAlarm(alarm.alarm_id)}>{alarm.name || alarm.alarm_id}</Button>
									<p>{t('state')}: {stateLabel(alarm.state)} · {t('aodh.severity')}: {reported(alarm.severity)}</p>
									{#snippet details()}<p>{t('type')}: {alarm.type}</p><p>{t('aodh.enabled')}: {reported(alarm.enabled)}</p>{/snippet}
								</CompactResourceCard>
							{/each}
						{/snippet}
					<TableShell density="compact">
						<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
						<table tabindex="0" aria-label={t('aodh.alarms')} class="focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent">
							<thead><tr><th scope="col">{t('name')}</th><th scope="col">{t('state')}</th><th scope="col">{t('type')}</th><th scope="col">{t('aodh.enabled')}</th><th scope="col">{t('aodh.severity')}</th></tr></thead>
							<tbody>{#each alarmItems as alarm (alarm.alarm_id)}
								<tr data-selected={selectedId === alarm.alarm_id}>
									<td><Button variant="link" ariaLabel={t('aodh.selectNamed', { name: alarm.name || alarm.alarm_id })} ariaPressed={selectedId === alarm.alarm_id} onclick={() => void selectAlarm(alarm.alarm_id)}>{alarm.name || alarm.alarm_id}</Button></td>
									<td>{stateLabel(alarm.state)}</td><td class="font-mono">{alarm.type}</td><td>{reported(alarm.enabled)}</td><td>{reported(alarm.severity)}</td>
								</tr>
							{/each}</tbody>
						</table>
					</TableShell>
					</ResponsiveTable>
				{:else if page.status === 'available'}<p role="status" class="text-sm text-ink-2">{t('aodh.emptyPage')}</p>{/if}
				{#if page.truncated}<Alert tone="warning">{t('truncated')}</Alert>{/if}
				{#if page.status !== 'available'}<Button variant="secondary" onclick={() => void loadPage()}>{t('retry')}</Button>{/if}
			{/if}
			<p class="text-xs text-ink-2">{t('aodh.paginationHelp')}</p>
			<div class="flex flex-wrap gap-2 items-center">
				<Button variant="secondary" disabled={pageLoading || pageIndex === 0} onclick={previousPage}>{t('previous')}</Button>
				<span class="text-xs text-ink-2 tabular-nums">{t('aodh.page')} {number(pageIndex + 1)}</span>
				<Button variant="secondary" disabled={pageLoading || !page?.items.length || !page.next_marker} onclick={nextPage}>{t('next')}</Button>
				{#if verifiedPage && page?.items.length === 0}<span class="text-xs text-ink-2">{t('aodh.endPage')}</span>{/if}
			</div>
		</section>

		<section aria-label={t('aodh.selectedAlarm')} class="space-y-3">
			<div class="flex flex-wrap items-center justify-between gap-2">
				<h2 class="text-sm font-semibold text-ink-0">{t('details')}</h2>
				{#if selectedId}<Button variant="secondary" onclick={clearSelection}>{t('close')}</Button>{/if}
			</div>
			{#if !selectedId}<p class="text-sm text-ink-2">{t('aodh.selectAlarm')}</p>
			{:else if detailLoading}<p role="status" class="text-sm text-ink-2">{t('loading')}</p>
			{:else}
				{#if detailFailure}<NativeStatus status={detailFailure} />{/if}
				{#if detail}<NativeStatus status={detail.status} error={detail.error} />{/if}
				<Button variant="secondary" onclick={() => selectedId && void selectAlarm(selectedId)}>{t('aodh.detailRetry')}</Button>
				{#if selectedAlarm}
					<Card>
						<div class="flex flex-wrap gap-3 items-start justify-between mb-3"><h3 class="text-sm font-semibold text-ink-0 break-all">{selectedAlarm.name || selectedAlarm.alarm_id}</h3><Button variant="secondary" href={`/admin/monitoring/aodh/settings?alarm=${encodeURIComponent(selectedAlarm.alarm_id)}`}>{t('aodh.edit')}</Button></div>
						<dl class="detail-fields grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
							<div><dt>{t('aodh.alarmId')}</dt><dd class="font-mono">{selectedAlarm.alarm_id}</dd></div>
							<div><dt>{t('type')}</dt><dd class="font-mono">{selectedAlarm.type}</dd></div>
							<div><dt>{t('state')}</dt><dd>{stateLabel(selectedAlarm.state)}</dd></div>
							<div><dt>{t('aodh.severity')}</dt><dd>{reported(selectedAlarm.severity)}</dd></div>
							<div><dt>{t('aodh.enabled')}</dt><dd>{reported(selectedAlarm.enabled)}</dd></div>
							<div><dt>{t('aodh.repeatActions')}</dt><dd>{reported(selectedAlarm.repeat_actions)}</dd></div>
							<div><dt>{t('aodh.descriptionLabel')}</dt><dd>{reported(selectedAlarm.description)}</dd></div>
							<div><dt>{t('aodh.stateReason')}</dt><dd>{reported(selectedAlarm.state_reason)}</dd></div>
							<div><dt>{t('aodh.stateTimestamp')}</dt><dd>{timestamp(selectedAlarm.state_timestamp)}</dd></div>
							<div><dt>{t('aodh.evaluateTimestamp')}</dt><dd>{timestamp(selectedAlarm.evaluate_timestamp)}</dd></div>
							<div><dt>{t('aodh.updatedTimestamp')}</dt><dd>{timestamp(selectedAlarm.timestamp)}</dd></div>
							<div><dt>{t('aodh.projectId')}</dt><dd class="font-mono">{reported(selectedAlarm.project_id)}</dd></div>
							<div><dt>{t('aodh.userId')}</dt><dd class="font-mono">{reported(selectedAlarm.user_id)}</dd></div>
						</dl>
						<h4 class="text-xs font-medium text-ink-1 mt-4">{t('aodh.rule')}</h4>
						<pre class="native-json mt-1">{json(ruleTypes.includes(selectedAlarm.type) ? selectedAlarm[`${selectedAlarm.type}_rule`] : null)}</pre>
						<h4 class="text-xs font-medium text-ink-1 mt-3">{t('aodh.timeConstraints')}</h4>
						<pre class="native-json mt-1">{json(selectedAlarm.time_constraints)}</pre>
						<p class="text-xs text-ink-2 mt-4">{t('aodh.actionPrivacy')}</p>
						{#each actionFields as field}
							<h4 class="text-xs font-medium text-ink-1 mt-3">{actionLabel(field)}</h4>
							{#if selectedAlarm[field]?.length}<ul class="space-y-1 mt-1">{#each selectedAlarm[field] ?? [] as url}<li><code class="text-xs text-ink-1 break-all whitespace-pre-wrap">{url}</code></li>{/each}</ul>
							{:else}<p class="text-xs text-ink-2 mt-1">{t('aodh.noActions')}</p>{/if}
						{/each}
					</Card>
				{:else if detail}<p class="text-sm text-ink-2">{t('aodh.missingDetail')}</p>{/if}
				{#if detail}
					<section aria-label={t('history')} class="space-y-2">
						<h3 class="text-sm font-semibold text-ink-0">{t('history')}</h3>
						<p class="text-xs text-ink-2">{t('aodh.historyBound')}</p>
						<NativeStatus status={detail.history.status} error={detail.history.error} />
						{#if detail.history.items.length}
							{@const historyEvents = detail.history.items}
							<ResponsiveTable>
								{#snippet cards()}
									{#each historyEvents as event}<CompactResourceCard><p class="font-medium">{reported(event.type)}</p><p>{timestamp(event.timestamp)}</p>{#snippet details()}<dl class="space-y-2"><div><dt>{t('aodh.eventId')}</dt><dd class="font-mono break-all">{reported(event.event_id)}</dd></div><div><dt>{t('aodh.userId')}</dt><dd class="font-mono break-all">{reported(event.user_id)}</dd></div><div><dt>{t('aodh.projectId')}</dt><dd class="font-mono break-all">{reported(event.project_id)}</dd></div></dl>{/snippet}</CompactResourceCard>{/each}
								{/snippet}
							<TableShell density="compact">
								<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
								<table tabindex="0" aria-label={t('history')} class="focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent">
									<thead><tr><th scope="col">{t('aodh.event')}</th><th scope="col">{t('aodh.timestamp')}</th><th scope="col">{t('aodh.eventId')}</th><th scope="col">{t('aodh.userId')}</th><th scope="col">{t('aodh.projectId')}</th></tr></thead>
									<tbody>{#each historyEvents as event}<tr><td>{reported(event.type)}</td><td>{timestamp(event.timestamp)}</td><td class="font-mono">{reported(event.event_id)}</td><td class="font-mono">{reported(event.user_id)}</td><td class="font-mono">{reported(event.project_id)}</td></tr>{/each}</tbody>
								</table>
							</TableShell>
							</ResponsiveTable>
						{:else if detail.history.status === 'available'}<p class="text-sm text-ink-2">{t('aodh.historyEmpty')}</p>{/if}
						{#if detail.history.truncated}<Alert tone="warning">{t('truncated')}</Alert>{/if}
					</section>
				{/if}
			{/if}
		</section>
	{/if}
</div>

<style>
	.native-json { max-height: 20rem; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; font-size: 0.75rem; color: var(--color-ink-1); }
	.detail-fields dt { font-size: 0.75rem; color: var(--color-ink-2); }
	.detail-fields dd { margin-top: 0.25rem; overflow-wrap: anywhere; color: var(--color-ink-0); }
</style>
