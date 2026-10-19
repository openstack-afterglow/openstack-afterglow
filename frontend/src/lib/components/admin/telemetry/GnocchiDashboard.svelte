<script lang="ts">
	import { onMount } from 'svelte';
	import { Alert, Button, Card, Field, PageHeader, PageShell, SelectInput, TableShell, TextInput } from '$lib/components/ui';
	import { adminTelemetryRequest, TelemetryError } from '$lib/api/adminTelemetry';
	import type {
		GnocchiOverview, MetricMeasures, NativeMetric, NativePage, NativeResource, NativeSection, TelemetryStatus,
	} from '$lib/api/adminTelemetry';
	import { t } from '$lib/i18n/ns/admin-telemetry';
	import NativeStatus from './NativeStatus.svelte';
	import { createTelemetryContext, type TelemetryContext } from './context';

	let context: TelemetryContext | undefined;
	let allowed = $state(false);
	let overview = $state<GnocchiOverview | null>(null);
	let overviewLoading = $state(false);
	let overviewFailure = $state<TelemetryStatus | null>(null);
	let resources = $state<NativePage<NativeResource> | null>(null);
	let resourcesLoading = $state(false);
	let metrics = $state<NativePage<NativeMetric> | null>(null);
	let metricsLoading = $state(false);
	let resourceType = $state('generic');
	let resourceMarkers = $state<(string | null)[]>([null]);
	let metricMarkers = $state<(string | null)[]>([null]);
	let selectedResource = $state<NativeResource | null>(null);
	let selectedMetric = $state<NativeMetric | null>(null);
	let measures = $state<MetricMeasures | null>(null);
	let measuresLoading = $state(false);
	let hours = $state('1');
	let aggregation = $state('mean');
	let granularity = $state('');
	let overviewGeneration = 0;
	let resourceGeneration = 0;
	let metricGeneration = 0;
	let measuresGeneration = 0;
	let contextGeneration = 0;
	const standardAggregations = ['mean', 'min', 'max', 'sum', 'std', 'count', 'median', 'first', 'last', '95pct'];
	const types = $derived([...new Set(['generic', ...(overview?.resource_types.data ?? []).map(item => typeof item === 'string' ? item : item.name)])]);
	const aggregations = $derived([...new Set([...standardAggregations,
		...(overview?.archive_policies.data ?? []).flatMap(policy => policy.aggregation_methods ?? [])])]);
	const validRange = $derived(Number.isInteger(Number(hours)) && Number(hours) >= 1 && Number(hours) <= 168
		&& (granularity.trim() === '' || (Number.isFinite(Number(granularity)) && Number(granularity) > 0)));

	function failure(error: unknown): TelemetryStatus {
		if (error instanceof TelemetryError) {
			if (error.status === 403) return 'forbidden';
			if (error.status === 404) return 'not_found';
			if (error.code === 'telemetry_not_configured') return 'not_configured';
		}
		return 'unavailable';
	}
	function pageFailure<T>(error: unknown): NativePage<T> {
		return { status: failure(error), error: 'telemetry_read_failed', items: [], next_marker: null, truncated: false };
	}
	function scrollTable(event: KeyboardEvent) {
		if (event.target !== event.currentTarget || event.altKey || event.ctrlKey || event.metaKey) return;
		const viewport = (event.currentTarget as HTMLElement).firstElementChild as HTMLElement | null;
		if (!viewport || viewport.scrollWidth <= viewport.clientWidth) return;
		if (event.key === 'ArrowLeft') viewport.scrollLeft -= 80;
		else if (event.key === 'ArrowRight') viewport.scrollLeft += 80;
		else if (event.key === 'Home') viewport.scrollLeft = 0;
		else if (event.key === 'End') viewport.scrollLeft = viewport.scrollWidth - viewport.clientWidth;
		else return;
		event.preventDefault();
	}
	function raw(value: unknown): string {
		if (value === null || value === undefined) return t('gnocchi.notReported');
		if (typeof value === 'object') return JSON.stringify(value);
		return String(value);
	}
	function policyName(metric: NativeMetric): string {
		const policy = metric.archive_policy;
		return raw(metric.archive_policy_name ?? (policy && typeof policy === 'object' && 'name' in policy ? policy.name : null));
	}
	function diagnosticRows(value: unknown, path = ''): { path: string; value: unknown }[] {
		if (value !== null && typeof value === 'object') {
			return Object.entries(value).flatMap(([key, child]) => diagnosticRows(child, path ? `${path}.${key}` : key));
		}
		return [{ path, value }];
	}
	function clearMeasures() {
		++measuresGeneration;
		measures = null;
		measuresLoading = false;
	}
	function clearMetric() { clearMeasures(); selectedMetric = null; }
	function reset() {
		++overviewGeneration; ++resourceGeneration; ++metricGeneration;
		overview = null; overviewFailure = null; overviewLoading = false;
		resources = null; resourcesLoading = false; metrics = null; metricsLoading = false;
		resourceMarkers = [null]; metricMarkers = [null]; resourceType = 'generic';
		selectedResource = null; clearMetric();
		hours = '1'; aggregation = 'mean'; granularity = '';
	}
	async function loadOverview() {
		const ticket = context?.capture();
		if (!ticket) return;
		const generation = ++overviewGeneration;
		overview = null; overviewFailure = null; overviewLoading = true;
		try {
			const result = await adminTelemetryRequest<GnocchiOverview>('/gnocchi', ticket.authority);
			if (ticket.current() && generation === overviewGeneration) overview = result;
		} catch (error) {
			if (ticket.current() && generation === overviewGeneration) overviewFailure = failure(error);
		} finally {
			if (ticket.current() && generation === overviewGeneration) overviewLoading = false;
		}
	}
	async function loadResources() {
		const ticket = context?.capture();
		if (!ticket) return;
		const generation = ++resourceGeneration;
		const type = resourceType;
		const marker = resourceMarkers.at(-1);
		resources = null; resourcesLoading = true; selectedResource = null;
		const params = new URLSearchParams({ type, limit: '25' });
		if (marker) params.set('marker', marker);
		const current = () => ticket.current() && generation === resourceGeneration && type === resourceType && marker === resourceMarkers.at(-1);
		try {
			const result = await adminTelemetryRequest<NativePage<NativeResource>>(`/gnocchi/resources?${params}`, ticket.authority);
			if (current()) resources = result;
		} catch (error) { if (current()) resources = pageFailure(error); }
		finally { if (current()) resourcesLoading = false; }
	}
	async function loadMetrics() {
		const ticket = context?.capture();
		if (!ticket) return;
		const generation = ++metricGeneration;
		const marker = metricMarkers.at(-1);
		metrics = null; metricsLoading = true;
		const params = new URLSearchParams({ limit: '25' });
		if (marker) params.set('marker', marker);
		const current = () => ticket.current() && generation === metricGeneration && marker === metricMarkers.at(-1);
		try {
			const result = await adminTelemetryRequest<NativePage<NativeMetric>>(`/gnocchi/metrics?${params}`, ticket.authority);
			if (current()) metrics = result;
		} catch (error) { if (current()) metrics = pageFailure(error); }
		finally { if (current()) metricsLoading = false; }
	}
	function refresh() {
		reset();
		void loadOverview(); void loadResources(); void loadMetrics();
	}
	function changeType(event: Event) {
		resourceType = (event.currentTarget as HTMLSelectElement).value;
		resourceMarkers = [null]; selectedResource = null; clearMetric();
		void loadResources();
	}
	function pageResources(direction: 'next' | 'previous') {
		if (direction === 'next') {
			if (!resources?.next_marker) return;
			resourceMarkers = [...resourceMarkers, resources.next_marker];
		} else resourceMarkers = resourceMarkers.slice(0, -1);
		clearMetric(); void loadResources();
	}
	function pageMetrics(direction: 'next' | 'previous') {
		if (direction === 'next') {
			if (!metrics?.next_marker) return;
			metricMarkers = [...metricMarkers, metrics.next_marker];
		} else metricMarkers = metricMarkers.slice(0, -1);
		clearMetric(); void loadMetrics();
	}
	function selectResource(resource: NativeResource) { selectedResource = resource; clearMetric(); }
	function selectMetric(metric: NativeMetric) { clearMeasures(); selectedMetric = metric; void loadMeasures(); }
	async function loadMeasures() {
		const ticket = context?.capture();
		if (!ticket || !selectedMetric || !validRange) return;
		const generation = ++measuresGeneration;
		const id = selectedMetric.id;
		const range = `${hours}/${aggregation}/${granularity}`;
		measures = null; measuresLoading = true;
		const params = new URLSearchParams({ hours: String(Number(hours)), aggregation });
		if (granularity.trim()) params.set('granularity', String(Number(granularity)));
		const current = () => ticket.current() && generation === measuresGeneration && id === selectedMetric?.id && range === `${hours}/${aggregation}/${granularity}`;
		try {
			const result = await adminTelemetryRequest<MetricMeasures>(`/gnocchi/metrics/${encodeURIComponent(id)}/measures?${params}`, ticket.authority);
			if (current()) measures = result;
		} catch (error) {
			if (current()) measures = { status: failure(error), error: 'telemetry_read_failed', metric: null, measures: [], truncated: false };
		} finally { if (current()) measuresLoading = false; }
	}
	onMount(() => {
		context = createTelemetryContext(() => {
			const generation = ++contextGeneration;
			reset(); allowed = context?.allowed() ?? false;
			queueMicrotask(() => {
				if (generation !== contextGeneration || !context?.allowed()) return;
				allowed = true; refresh();
			});
		});
		allowed = context.allowed();
		if (allowed) refresh();
		return () => { ++contextGeneration; reset(); context?.dispose(); };
	});
</script>

{#snippet nativeDiagnostics(label: string, section: NativeSection)}
	<section aria-label={label} class="space-y-3 min-w-0">
		<h2 class="text-sm font-semibold text-ink-0">{label}</h2>
		<NativeStatus status={section.status} error={section.error} />
		{#if section.data === null}
			<p class="text-sm text-ink-2">{t('gnocchi.noSectionData')}</p>
		{:else if diagnosticRows(section.data).length === 0}
			<p class="text-sm text-ink-2">{t('gnocchi.emptySection')}</p>
		{:else}
			<div role="region" aria-label={label} tabindex="0" onkeydown={scrollTable}><TableShell density="compact"><table>
				<caption class="sr-only">{label}</caption>
				<thead><tr><th scope="col">{t('gnocchi.field')}</th><th scope="col">{t('gnocchi.value')}</th></tr></thead>
				<tbody>{#each diagnosticRows(section.data) as row}<tr><th scope="row" class="break-all">{row.path}</th><td class="tabular-nums break-all">{raw(row.value)}</td></tr>{/each}</tbody>
			</table></TableShell></div>
		{/if}
	</section>
{/snippet}

<PageShell>
	<PageHeader breadcrumb={t('gnocchi.breadcrumb')} title={t('gnocchi.title')} subtitle={t('gnocchi.subtitle')}>
		{#snippet actions()}
			<Button variant="secondary" disabled={!allowed} onclick={refresh}>{t('refresh')}</Button>
			<Button variant="link" href="/admin/monitoring/aodh">{t('gnocchi.aodh')}</Button>
		{/snippet}
	</PageHeader>
	{#if !allowed}
		<Alert tone="neutral">{t('gnocchi.accessRequired')}</Alert>
	{:else}
		<div class="space-y-6">
			<Alert tone="info">{t('gnocchi.processingHelp')}</Alert>
			{#if overviewLoading}<p role="status" class="text-sm text-ink-2">{t('loading')}</p>{/if}
			{#if overviewFailure}<NativeStatus status={overviewFailure} /><Button variant="secondary" onclick={loadOverview}>{t('retry')}</Button>{/if}
			{#if overview}
				<NativeStatus status={overview.status} error={overview.error} />
				<p class="text-xs text-ink-2">{t('checkedAt')}: <time datetime={overview.checked_at}>{overview.checked_at}</time></p>
				<div class="grid min-w-0 gap-4 lg:grid-cols-2">
					<Card>{@render nativeDiagnostics(t('gnocchi.capabilities'), overview.capabilities)}</Card>
					<Card>{@render nativeDiagnostics(t('gnocchi.processing'), overview.processing)}</Card>
				</div>
				<section aria-label={t('gnocchi.archivePolicies')} class="space-y-3">
					<h2 class="text-sm font-semibold text-ink-0">{t('gnocchi.archivePolicies')}</h2>
					<NativeStatus status={overview.archive_policies.status} error={overview.archive_policies.error} />
					{#if overview.archive_policies.data?.length}
						<div role="region" aria-label={t('gnocchi.archivePolicies')} tabindex="0" onkeydown={scrollTable}><TableShell density="compact"><table>
							<caption class="sr-only">{t('gnocchi.archivePolicies')}</caption>
							<thead><tr><th scope="col">{t('name')}</th><th scope="col">{t('gnocchi.backWindow')}</th><th scope="col">{t('gnocchi.aggregationMethods')}</th><th scope="col">{t('gnocchi.definition')}</th></tr></thead>
							<tbody>{#each overview.archive_policies.data as policy}<tr><th scope="row">{policy.name}</th><td>{raw(policy.back_window)}</td><td>{policy.aggregation_methods?.join(', ') ?? t('gnocchi.notReported')}</td><td>{#each policy.definition ?? [] as tier}<div class="tabular-nums">{raw(tier.granularity)} / {raw(tier.points)} / {raw(tier.timespan)}</div>{:else}{t('gnocchi.notReported')}{/each}</td></tr>{/each}</tbody>
						</table></TableShell></div>
					{:else}<p class="text-sm text-ink-2">{t(overview.archive_policies.status === 'available' && overview.archive_policies.data !== null ? 'gnocchi.emptySection' : 'gnocchi.noSectionData')}</p>{/if}
				</section>
				<section aria-label={t('gnocchi.archivePolicyRules')} class="space-y-3">
					<h2 class="text-sm font-semibold text-ink-0">{t('gnocchi.archivePolicyRules')}</h2>
					<NativeStatus status={overview.archive_policy_rules.status} error={overview.archive_policy_rules.error} />
					{#if overview.archive_policy_rules.data?.length}
						<div role="region" aria-label={t('gnocchi.archivePolicyRules')} tabindex="0" onkeydown={scrollTable}><TableShell density="compact"><table>
							<caption class="sr-only">{t('gnocchi.archivePolicyRules')}</caption>
							<thead><tr><th scope="col">{t('name')}</th><th scope="col">{t('gnocchi.pattern')}</th><th scope="col">{t('gnocchi.archivePolicy')}</th></tr></thead>
							<tbody>{#each overview.archive_policy_rules.data as rule}<tr><th scope="row">{rule.name}</th><td>{raw(rule.metric_pattern)}</td><td>{raw(rule.archive_policy_name)}</td></tr>{/each}</tbody>
						</table></TableShell></div>
					{:else}<p class="text-sm text-ink-2">{t(overview.archive_policy_rules.status === 'available' && overview.archive_policy_rules.data !== null ? 'gnocchi.emptySection' : 'gnocchi.noSectionData')}</p>{/if}
				</section>
				<section aria-label={t('gnocchi.resourceTypes')} class="space-y-3">
					<h2 class="text-sm font-semibold text-ink-0">{t('gnocchi.resourceTypes')}</h2>
					<NativeStatus status={overview.resource_types.status} error={overview.resource_types.error} />
					{#if overview.resource_types.data?.length}<ul class="flex flex-wrap gap-3 text-sm text-ink-1">{#each overview.resource_types.data as type}<li>{typeof type === 'string' ? type : type.name}</li>{/each}</ul>
					{:else}<p class="text-sm text-ink-2">{t(overview.resource_types.status === 'available' && overview.resource_types.data !== null ? 'gnocchi.emptySection' : 'gnocchi.noSectionData')}</p>{/if}
				</section>
			{/if}

			<section aria-label={t('gnocchi.resources')} class="space-y-3">
				<h2 class="text-sm font-semibold text-ink-0">{t('gnocchi.resources')}</h2>
				<p class="text-sm text-ink-2">{t('gnocchi.resourceHelp')}</p>
				<div class="flex flex-wrap items-end gap-3">
					<Field for="gnocchi-resource-type" label={t('gnocchi.resourceType')} class="w-full md:w-64"><SelectInput id="gnocchi-resource-type" value={resourceType} onchange={changeType}>{#each types as type}<option value={type}>{type}</option>{/each}</SelectInput></Field>
					<Button variant="secondary" onclick={() => { clearMetric(); void loadResources(); }}>{t('refresh')}</Button>
				</div>
				{#if resourcesLoading}<p role="status" class="text-sm text-ink-2">{t('loading')}</p>{/if}
				{#if resources}
					<NativeStatus status={resources.status} error={resources.error} />
					{#if resources.status === 'available' || (resources.status === 'partial' && resources.items.length > 0)}<p class="text-xs text-ink-2">{t('gnocchi.loadedPage', { page: resourceMarkers.length, count: resources.items.length })}</p>{/if}
					{#if resources.items.length}
						<div role="region" aria-label={t('gnocchi.resources')} tabindex="0" onkeydown={scrollTable}><TableShell density="compact"><table>
							<caption class="sr-only">{t('gnocchi.resources')}</caption>
							<thead><tr><th scope="col">{t('gnocchi.id')}</th><th scope="col">{t('type')}</th><th scope="col">{t('gnocchi.project')}</th><th scope="col">{t('gnocchi.started')}</th><th scope="col">{t('gnocchi.ended')}</th></tr></thead>
							<tbody>{#each resources.items as resource}<tr data-selected={selectedResource?.id === resource.id}><td><Button variant="link" ariaPressed={selectedResource?.id === resource.id} onclick={() => selectResource(resource)}>{resource.id}</Button></td><td>{raw(resource.type)}</td><td class="font-mono">{raw(resource.project_id)}</td><td>{raw(resource.started_at)}</td><td>{raw(resource.ended_at)}</td></tr>{/each}</tbody>
						</table></TableShell></div>
					{:else}<p class="text-sm text-ink-2">{t(resources.status === 'available' ? 'gnocchi.emptyPage' : 'gnocchi.unverifiedPage')}</p>{/if}
					{#if resources.truncated}<Alert tone="warning">{t('gnocchi.pageTruncated')}</Alert>{/if}
				{/if}
				<div class="flex flex-wrap gap-2" role="group" aria-label={t('gnocchi.resources')}>
					<Button variant="secondary" disabled={resourceMarkers.length <= 1} onclick={() => pageResources('previous')}>{t('previous')}</Button>
					<Button variant="secondary" disabled={resourcesLoading || !resources?.next_marker} onclick={() => pageResources('next')}>{t('next')}</Button>
				</div>
				<p class="text-xs text-ink-2">{t('gnocchi.pagingHelp')}</p>
				<Card><h3 class="mb-3 text-sm font-semibold text-ink-0">{t('gnocchi.resourceMetrics')}</h3>
					{#if selectedResource}<p class="mb-2 break-all font-mono text-xs text-ink-2">{selectedResource.id}</p><div class="flex flex-wrap gap-2">{#each Object.entries(selectedResource.metrics ?? {}) as [name, id]}<Button variant="link" ariaPressed={selectedMetric?.id === id} onclick={() => selectMetric({ id, name, resource_id: selectedResource!.id })}>{name} · {id}</Button>{:else}<p class="text-sm text-ink-2">{t('gnocchi.noResourceMetrics')}</p>{/each}</div>
					{:else}<p class="text-sm text-ink-2">{t('gnocchi.selectResource')}</p>{/if}
				</Card>
			</section>

			<section aria-label={t('gnocchi.metrics')} class="space-y-3">
				<div class="flex flex-wrap items-center gap-3"><h2 class="mr-auto text-sm font-semibold text-ink-0">{t('gnocchi.metrics')}</h2><Button variant="secondary" onclick={() => { clearMetric(); void loadMetrics(); }}>{t('refresh')}</Button></div>
				<p class="text-sm text-ink-2">{t('gnocchi.metricHelp')}</p>
				{#if metricsLoading}<p role="status" class="text-sm text-ink-2">{t('loading')}</p>{/if}
				{#if metrics}
					<NativeStatus status={metrics.status} error={metrics.error} />
					{#if metrics.status === 'available' || (metrics.status === 'partial' && metrics.items.length > 0)}<p class="text-xs text-ink-2">{t('gnocchi.loadedPage', { page: metricMarkers.length, count: metrics.items.length })}</p>{/if}
					{#if metrics.items.length}
						<div role="region" aria-label={t('gnocchi.metrics')} tabindex="0" onkeydown={scrollTable}><TableShell density="compact"><table>
							<caption class="sr-only">{t('gnocchi.metrics')}</caption>
							<thead><tr><th scope="col">{t('gnocchi.id')}</th><th scope="col">{t('name')}</th><th scope="col">{t('unit')}</th><th scope="col">{t('gnocchi.resourceId')}</th><th scope="col">{t('gnocchi.archivePolicy')}</th></tr></thead>
							<tbody>{#each metrics.items as metric}<tr data-selected={selectedMetric?.id === metric.id}><td><Button variant="link" ariaPressed={selectedMetric?.id === metric.id} onclick={() => selectMetric(metric)}>{metric.id}</Button></td><td>{raw(metric.name)}</td><td>{metric.unit ?? t('gnocchi.unitUnknown')}</td><td class="font-mono">{raw(metric.resource_id)}</td><td>{policyName(metric)}</td></tr>{/each}</tbody>
						</table></TableShell></div>
					{:else}<p class="text-sm text-ink-2">{t(metrics.status === 'available' ? 'gnocchi.emptyPage' : 'gnocchi.unverifiedPage')}</p>{/if}
					{#if metrics.truncated}<Alert tone="warning">{t('gnocchi.pageTruncated')}</Alert>{/if}
				{/if}
				<div class="flex flex-wrap gap-2" role="group" aria-label={t('gnocchi.metrics')}>
					<Button variant="secondary" disabled={metricMarkers.length <= 1} onclick={() => pageMetrics('previous')}>{t('previous')}</Button>
					<Button variant="secondary" disabled={metricsLoading || !metrics?.next_marker} onclick={() => pageMetrics('next')}>{t('next')}</Button>
				</div>
				<p class="text-xs text-ink-2">{t('gnocchi.pagingHelp')}</p>
			</section>

			<section aria-label={t('gnocchi.measures')} class="space-y-3">
				<h2 class="text-sm font-semibold text-ink-0">{t('gnocchi.measures')}</h2>
				<p class="text-sm text-ink-2">{t('gnocchi.measuresHelp')}</p>
				{#if selectedMetric}
					<p class="break-all text-sm text-ink-1">{selectedMetric.name ?? t('gnocchi.notReported')} · <span class="font-mono">{selectedMetric.id}</span></p>
					<div class="grid gap-3 md:grid-cols-3">
						<Field for="gnocchi-hours" label={t('gnocchi.hours')}><TextInput id="gnocchi-hours" value={hours} inputmode="numeric" ariaInvalid={!validRange} oninput={event => { hours = (event.currentTarget as HTMLInputElement).value; clearMeasures(); }} /></Field>
						<Field for="gnocchi-aggregation" label={t('gnocchi.aggregation')}><SelectInput id="gnocchi-aggregation" value={aggregation} onchange={event => { aggregation = (event.currentTarget as HTMLSelectElement).value; clearMeasures(); }}>{#each aggregations as method}<option value={method}>{method}</option>{/each}</SelectInput></Field>
						<Field for="gnocchi-granularity" label={t('gnocchi.granularity')} help={t('gnocchi.granularityHelp')}><TextInput id="gnocchi-granularity" value={granularity} inputmode="decimal" ariaInvalid={!validRange} oninput={event => { granularity = (event.currentTarget as HTMLInputElement).value; clearMeasures(); }} /></Field>
					</div>
					{#if !validRange}<Alert tone="warning">{t('gnocchi.invalidRange')}</Alert>{/if}
					<Button variant="secondary" disabled={!validRange || measuresLoading} onclick={loadMeasures}>{t('gnocchi.readMeasures')}</Button>
					{#if measuresLoading}<p role="status" class="text-sm text-ink-2">{t('loading')}</p>
					{:else if !measures}<p class="text-sm text-ink-2">{t('gnocchi.pendingMeasures')}</p>{/if}
					{#if measures}
						<NativeStatus status={measures.status} error={measures.error} />
						<p class="text-sm text-ink-1">{t('unit')}: {measures.metric?.unit ?? selectedMetric.unit ?? t('gnocchi.unitUnknown')}</p>
						{#if measures.metric}
							<dl class="grid gap-2 text-sm text-ink-1 md:grid-cols-2">
								<div><dt class="text-xs text-ink-2">{t('name')}</dt><dd class="break-all">{raw(measures.metric.name)}</dd></div>
								<div><dt class="text-xs text-ink-2">{t('gnocchi.id')}</dt><dd class="break-all font-mono">{measures.metric.id}</dd></div>
								<div><dt class="text-xs text-ink-2">{t('gnocchi.resourceId')}</dt><dd class="break-all font-mono">{raw(measures.metric.resource_id)}</dd></div>
								<div><dt class="text-xs text-ink-2">{t('gnocchi.archivePolicy')}</dt><dd class="break-all">{raw(measures.metric.archive_policy_name ?? measures.metric.archive_policy)}</dd></div>
							</dl>
						{/if}
						{#if measures.measures.length}
							<p class="text-xs text-ink-2">{t('gnocchi.sampleCount', { count: measures.measures.length })}</p>
							<div role="region" aria-label={t('gnocchi.measures')} tabindex="0" onkeydown={scrollTable}><TableShell density="compact"><table>
								<caption class="sr-only">{t('gnocchi.measures')} · {selectedMetric.id}</caption>
								<thead><tr><th scope="col">{t('gnocchi.timestamp')}</th><th scope="col">{t('gnocchi.nativeGrain')}</th><th scope="col">{t('gnocchi.value')}</th><th scope="col">{t('unit')}</th></tr></thead>
								<tbody>{#each measures.measures as sample}<tr><td><time datetime={sample.timestamp}>{sample.timestamp}</time></td><td class="tabular-nums">{String(sample.granularity)}</td><td class="tabular-nums">{String(sample.value)}</td><td>{measures.metric?.unit ?? selectedMetric.unit ?? t('gnocchi.unitUnknown')}</td></tr>{/each}</tbody>
							</table></TableShell></div>
						{:else}<p class="text-sm text-ink-2">{t(measures.status === 'available' && !measures.truncated ? 'gnocchi.noData' : 'gnocchi.noVerifiedSamples')}</p>{/if}
						{#if measures.truncated}<Alert tone="warning">{t('gnocchi.samplesTruncated')}</Alert>{/if}
					{/if}
				{:else}<p class="text-sm text-ink-2">{t('gnocchi.selectMetric')}</p>{/if}
			</section>
		</div>
	{/if}
</PageShell>
