<script lang="ts">
	import { onDestroy } from 'svelte';
	import { get } from 'svelte/store';
	import { api, ApiError, getBaseUrl } from '$lib/api/client';
	import { siteConfig } from '$lib/config/site';
	import { auth, authReady, logoutInProgress, projectSwitching } from '$lib/stores/auth';
	import { adminInventoryScope } from '$lib/stores/adminInventoryScope';
	import { Alert, Button, Card, Field, SelectInput, TextInput } from '$lib/components/ui';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import { t } from '$lib/i18n/ns/admin-ops';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import { downloadBlobAs } from '$lib/utils/downloadBlob';
	import { experienceUuid, recentReplayQuery, recentReplayRows, replayCause, replayHttpStatus, replayLabel, replayQuery, replayRows, replaySource, replayStatus, replayValue, retainedReplayMessage, type ExperienceRecentQuery, type ExperienceRecentResponse, type ExperienceRecentSegment, type ExperienceReplayEvent, type ExperienceReplayQuery, type ExperienceReplayResponse } from './experienceReplay';

	let segmentId = $state('');
	let actionId = $state('');
	let anonymous = $state('exclude');
	let response = $state<ExperienceReplayResponse | null>(null);
	let applied = $state<ExperienceReplayQuery | null>(null);
	let loading = $state(false);
	let exporting = $state(false);
	let stale = $state(false);
	let invalid = $state(false);
	let error = $state<'denied' | 'unavailable' | 'sqlError' | 'failed' | null>(null);
	let exportError = $state(false);
	let exportComplete = $state(false);
	let generation = 0;
	let controller: AbortController | null = null;
	let owner: string | undefined;
	let recentUserId = $state('');
	let recentDays = $state('1');
	let recentResponse = $state<ExperienceRecentResponse | null>(null);
	let recentApplied = $state<ExperienceRecentQuery | null>(null);
	let recentLoading = $state(false);
	let recentError = $state<'denied' | 'unavailable' | 'sqlError' | 'failed' | null>(null);
	let recentSelected = $state(false);
	let recentGeneration = 0;
	let recentController: AbortController | null = null;
	const recentRows = $derived(recentResponse && recentApplied ? recentReplayRows(recentResponse, recentApplied) : []);
	const recentPartial = $derived(!!recentResponse && (recentResponse.coverage.partial || recentResponse.has_more || recentRows.length !== recentResponse.segments.length));
	const scoped = $derived(!!($adminInventoryScope.domainId || $adminInventoryScope.projectId));
	const permitted = $derived($authReady && !$logoutInProgress && !$projectSwitching && $auth.isSystemAdmin && !!$auth.token);
	const rows = $derived(response && applied ? replayRows(response, applied) : []);
	const projectionPartial = $derived(!!response && rows.length !== response.events.length);
	const dateFormat = $derived(new Intl.DateTimeFormat(intlLocale(), { dateStyle: 'medium', timeStyle: 'long' }));

	function invalidateRecent(resetFilters = false) {
		++recentGeneration;
		recentController?.abort(); recentController = null;
		recentResponse = null; recentApplied = null; recentLoading = false; recentError = null; recentSelected = false;
		if (resetFilters) { recentUserId = ''; recentDays = '1'; }
	}
	function invalidate(changedScope = false) {
		++generation;
		controller?.abort(); controller = null;
		stale = !!response || loading || exporting || stale;
		response = null; applied = null; loading = false; exporting = false;
		error = null; exportError = false; exportComplete = false; invalid = false;
		recentSelected = false;
		if (changedScope) { segmentId = ''; actionId = ''; anonymous = 'exclude'; invalidateRecent(true); }
	}
	function syncOwner() {
		const state = get(auth);
		const key = JSON.stringify([getBaseUrl(), state.sessionId, state.userId, state.identityDomainId, state.domainId, state.projectId,
			!!state.token, state.isSystemAdmin, state.isDomainManager, state.canWrite, [...(state.roles ?? [])].sort(),
			get(authReady), get(logoutInProgress), get(projectSwitching), get(adminInventoryScope)]);
		if (owner !== undefined && owner !== key) invalidate(true);
		owner = key;
	}
	const subscriptions = [auth.subscribe(syncOwner), authReady.subscribe(syncOwner), logoutInProgress.subscribe(syncOwner), projectSwitching.subscribe(syncOwner), adminInventoryScope.subscribe(syncOwner), siteConfig.subscribe(syncOwner)];
	function date(value: string | null): string {
		if (!value) return t('experience.unknown');
		const parsed = new Date(value);
		return Number.isNaN(parsed.getTime()) ? t('experience.unknown') : dateFormat.format(parsed);
	}
	function fields(row: ExperienceReplayEvent): [string, string | number | null | undefined][] {
		return [[t('experience.eventId'), row.event_id], [t('experience.pageView'), row.page_view_id], [t('experience.actionId'), row.action_id],
			[t('events.userId'), row.actor.user_id], [t('events.projectId'), row.actor.project_id], [t('events.route'), row.route],
			[t('events.control'), row.component], [t('events.action'), `${row.feature} / ${row.action}`], [t('experience.occurred'), date(row.occurred_at)],
			[t('experience.received'), date(row.received_at)], [t('experience.sequence'), row.client_seq], [t('experience.monotonic'), row.client_monotonic_ms],
			[t('events.requestId'), row.source === 'browser' ? row.payload.request_id : row.request_id], [t('experience.operation'), row.operation_id], [t('events.resourceId'), row.resource_ref],
			[t('experience.trace'), row.trace_id], [t('experience.span'), row.span_id], [t('experience.parentSpan'), row.parent_span_id],
			[t('experience.builds'), `${row.frontend_build} / ${row.backend_build ?? t('experience.unknown')}`], [t('experience.catalogRevision'), row.catalog_revision],
			[t('experience.redactionRevision'), row.redaction_revision], [t('events.status'), row.status]];
	}
	function currentQuery(): ExperienceReplayQuery {
		const scope = get(adminInventoryScope);
		return { segmentId: segmentId.trim(), actionId: actionId.trim(), domainId: scope.domainId, projectId: scope.projectId, includeAnonymous: anonymous === 'include' };
	}
	function retireOnRefusal(cause: unknown): boolean {
		if (!(cause instanceof ApiError) || ![401, 403, 404].includes(cause.status)) return false;
		invalidate();
		error = cause.status === 404 ? 'unavailable' : 'denied';
		invalidateRecent();
		return true;
	}
	async function lookupRecent(event?: SubmitEvent) {
		event?.preventDefault();
		if (!permitted || loading || exporting || recentLoading) return;
		const scope = get(adminInventoryScope);
		const days = Number(recentDays);
		if (![1, 7, 30].includes(days) || recentUserId.trim().length > 64) { recentError = 'failed'; return; }
		const query: ExperienceRecentQuery = { userId: recentUserId.trim(), days: days as 1 | 7 | 30,
			domainId: scope.domainId, projectId: scope.projectId, includeAnonymous: anonymous === 'include' };
		if (query.includeAnonymous && scoped) { recentError = 'denied'; return; }
		invalidateRecent();
		const requestGeneration = recentGeneration;
		const requestOwner = owner;
		const baseUrl = getBaseUrl();
		const abort = new AbortController(); recentController = abort;
		const owns = () => requestGeneration === recentGeneration && requestOwner === owner && baseUrl === getBaseUrl() && !abort.signal.aborted && permitted;
		recentLoading = true;
		try {
			const result = await api.get<ExperienceRecentResponse>(recentReplayQuery(query), $auth.token!, $auth.projectId ?? undefined,
				{ cache: 'no-store', signal: abort.signal, replayOnUnauthorized: false });
			if (!owns()) return;
			if (result.schema_version !== 2 || !Array.isArray(result.segments)) {
				invalidate(); invalidateRecent(); recentError = 'unavailable'; return;
			}
			recentResponse = result; recentApplied = query;
		} catch (cause) {
			if (owns()) {
				if (cause instanceof ApiError && [401, 403, 404].includes(cause.status)) {
					invalidate(); invalidateRecent(); recentError = cause.status === 404 ? 'unavailable' : 'denied';
				} else recentError = cause instanceof ApiError && cause.status === 503 ? 'sqlError' : 'failed';
			}
		} finally { if (owns()) { recentLoading = false; recentController = null; } }
	}
	function selectRecent(row: ExperienceRecentSegment) {
		if (!permitted || loading || exporting || recentLoading || !recentRows.includes(row) || !experienceUuid.test(row.segment_id)) return;
		invalidate();
		segmentId = row.segment_id; actionId = ''; recentSelected = true;
	}
	async function search(event?: SubmitEvent, more = false) {
		event?.preventDefault();
		if (!permitted || loading || exporting) return;
		const query = more && applied ? applied : currentQuery();
		if (!experienceUuid.test(query.segmentId) || (query.actionId && !experienceUuid.test(query.actionId))) { invalid = true; return; }
		if (query.includeAnonymous && scoped) { error = 'denied'; return; }
		const before = more && response?.events.length ? Math.min(...response.events.map(row => row.id)) : undefined;
		const previous = more ? response : null;
		if (more) {
			++generation; controller?.abort(); controller = null;
			error = null; exportError = false; exportComplete = false;
		} else invalidate();
		const requestGeneration = generation;
		const requestOwner = owner;
		const abort = new AbortController(); controller = abort;
		const owns = () => requestGeneration === generation && requestOwner === owner && !abort.signal.aborted && permitted;
		loading = true; stale = false;
		try {
			const result = await api.get<ExperienceReplayResponse>(replayQuery(query, false, before), $auth.token!, $auth.projectId ?? undefined,
				{ cache: 'no-store', signal: abort.signal, replayOnUnauthorized: false });
			if (!owns()) return;
			if (result.schema_version !== 2) { invalidate(); error = 'unavailable'; return; }
			response = previous ? { ...result, events: [...previous.events, ...result.events.filter(row => !previous.events.some(existing => existing.id === row.id))].sort((a, b) => b.id - a.id), catalogs: [...previous.catalogs, ...result.catalogs],
				coverage: { ...result.coverage, partial: previous.coverage.partial || result.coverage.partial, reasons: [...new Set([...previous.coverage.reasons, ...result.coverage.reasons])] } } : result;
			applied = query;
		} catch (cause) {
			if (owns() && !retireOnRefusal(cause)) error = cause instanceof ApiError && cause.status === 503 ? 'sqlError' : 'failed';
		} finally { if (owns()) { loading = false; controller = null; } }
	}
	async function exportJson() {
		if (!applied || !response || loading || exporting || !permitted) return;
		const query = { ...applied };
		const requestGeneration = generation;
		const requestOwner = owner;
		const abort = new AbortController(); controller = abort;
		const owns = () => requestGeneration === generation && requestOwner === owner && !abort.signal.aborted && permitted;
		exporting = true; exportError = false; exportComplete = false;
		try {
			const result = await api.get<ExperienceReplayResponse>(replayQuery(query, true), $auth.token!, $auth.projectId ?? undefined,
				{ cache: 'no-store', signal: abort.signal, replayOnUnauthorized: false });
			if (!owns()) return;
			if (result.schema_version !== 2) { invalidate(); error = 'unavailable'; return; }
			if (replayRows(result, query).length !== result.events.length) throw new Error('invalid_projection');
			// Only a local immutable JSON blob is downloaded. Event values never become a destination.
			downloadBlobAs(new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' }), 'afterglow-experience.json');
			exportComplete = true;
		} catch (cause) { if (owns() && !retireOnRefusal(cause)) exportError = true; }
		finally { if (owns()) { exporting = false; controller = null; } }
	}
	onDestroy(() => { ++generation; controller?.abort(); invalidateRecent(true); for (const unsubscribe of subscriptions) unsubscribe(); });
</script>

<section class="mb-6 min-w-0" aria-labelledby="experience-replay-title" data-experience-replay>
	<Card surface="base">
		<h2 id="experience-replay-title" class="text-base font-semibold text-ink-0">{t('experience.title')}</h2>
		<p class="mt-2 text-sm text-ink-2">{t('experience.notice')}</p>
		<div class="mt-6 min-w-0" data-experience-recent>
			<h3 class="text-sm font-semibold text-ink-0">{t('experience.recentTitle')}</h3>
			<p class="mt-2 text-sm text-ink-2">{t('experience.recentNotice')}</p>
			<form class="mt-4" onsubmit={lookupRecent} aria-label={t('experience.recentSearch')}>
				<div class="grid min-w-0 grid-cols-1 items-end gap-4 md:grid-cols-2">
					<Field label={t('experience.recentUserId')} for="experience-recent-user" help={t('experience.recentUserHelp')}>
						<TextInput id="experience-recent-user" bind:value={recentUserId} maxlength={64} autocomplete="off" oninput={() => invalidateRecent()} />
					</Field>
					<Field label={t('experience.recentDays')} for="experience-recent-days">
						<SelectInput id="experience-recent-days" bind:value={recentDays} onchange={() => invalidateRecent()}>
							<option value="1">{t('experience.recentDay1')}</option>
							<option value="7">{t('experience.recentDay7')}</option>
							<option value="30">{t('experience.recentDay30')}</option>
						</SelectInput>
					</Field>
				</div>
				<div class="mt-4"><Button type="submit" variant="secondary" class="max-w-full" disabled={!permitted || loading || exporting || recentLoading}><span class="min-w-0 whitespace-normal break-words">{t('experience.recentSearch')}</span></Button></div>
			</form>
			{#if recentLoading}<div class="mt-4"><LoadingState variant="section" label={t('experience.recentLoading')} /></div>{/if}
			{#if recentError}<div class="mt-4"><Alert tone="danger">{t(`experience.${recentError}`)}</Alert></div>{/if}
			{#if recentResponse}
				{#if recentPartial}<div class="mt-4"><Alert tone="warning">{t('experience.recentPartial')}</Alert></div>{/if}
				{#if !recentRows.length}<p class="mt-4 text-sm text-ink-2" role="status">{t('experience.recentEmpty')}</p>
				{:else}
					<ul class="mt-4 divide-y divide-line" aria-label={t('experience.recentTitle')}>
						{#each recentRows as row}
							<li class="min-w-0 py-4">
								<p class="break-all font-mono text-sm text-ink-0">{row.segment_id}</p>
								<dl class="mt-2 grid min-w-0 grid-cols-1 gap-3 text-sm md:grid-cols-2">
									<div class="min-w-0"><dt class="text-ink-2">{t('events.userId')}</dt><dd class="break-all text-ink-1">{row.user_id || t('experience.recentUnknownOwner')}</dd></div>
									<div class="min-w-0"><dt class="text-ink-2">{t('events.projectId')}</dt><dd class="break-all text-ink-1">{row.project_id || t('experience.unknown')}</dd></div>
									<div class="min-w-0"><dt class="text-ink-2">{t('experience.recentReceived')}</dt><dd class="tabular-nums text-ink-1">{date(row.last_received_at)}</dd></div>
									<div class="min-w-0"><dt class="text-ink-2">{t('experience.recentCount')}</dt><dd class="tabular-nums text-ink-1">{row.event_count}</dd></div>
								</dl>
								<div class="mt-3"><Button variant="secondary" class="max-w-full" onclick={() => selectRecent(row)} disabled={!permitted || loading || exporting || recentLoading} ariaLabel={t('experience.recentSelectCode', { code: row.segment_id })}><span class="min-w-0 whitespace-normal break-words">{t('experience.recentSelect')}</span></Button></div>
							</li>
						{/each}
					</ul>
				{/if}
			{:else if !recentLoading && !recentError}<p class="mt-4 text-sm text-ink-2">{t('experience.recentIdle')}</p>{/if}
			{#if recentSelected}<p class="mt-3 text-sm text-ink-2" role="status">{t('experience.recentSelected')}</p>{/if}
		</div>
		<form class="mt-4" onsubmit={search} aria-label={t('experience.search')}>
			<div class="grid min-w-0 grid-cols-1 gap-4 md:grid-cols-2">
				<Field label={t('experience.segmentId')} for="experience-segment" help={t('experience.uuidHelp')} error={invalid ? t('experience.invalid') : undefined}>
					<TextInput id="experience-segment" bind:value={segmentId} maxlength={36} autocomplete="off" ariaInvalid={invalid} oninput={() => invalidate()} />
				</Field>
				<Field label={t('experience.actionId')} for="experience-action" help={t('experience.optional')}>
					<TextInput id="experience-action" bind:value={actionId} maxlength={36} autocomplete="off" ariaInvalid={invalid} oninput={() => invalidate()} />
				</Field>
			</div>
			<div class="mt-4 grid grid-cols-1 items-end gap-4 md:grid-cols-2">
				<Field label={t('experience.anonymous')} for="experience-anonymous" help={t('experience.anonymousHelp')}>
					<SelectInput id="experience-anonymous" bind:value={anonymous} disabled={scoped} onchange={() => { invalidate(); invalidateRecent(); }}>
						<option value="exclude">{t('experience.excludeAnonymous')}</option><option value="include">{t('experience.includeAnonymous')}</option>
					</SelectInput>
				</Field>
				<div class="flex flex-wrap gap-2">
					<Button type="submit" disabled={!permitted || loading || exporting}>{t('experience.search')}</Button>
					<Button variant="secondary" onclick={exportJson} disabled={!response || !permitted || loading || exporting}>{exporting ? t('experience.exporting') : t('experience.export')}</Button>
				</div>
			</div>
		</form>
		<p class="mt-3 text-sm text-ink-2">{t('experience.exportNotice')}</p>
		{#if !permitted}<div class="mt-4"><Alert tone="warning">{t('experience.denied')}</Alert></div>{/if}
		{#if stale}<p class="mt-4 text-sm text-ink-2" role="status">{t('experience.stale')}</p>{/if}
		{#if loading}<div class="mt-4"><LoadingState variant="section" label={t('experience.loading')} /></div>{/if}
		{#if error}<div class="mt-4"><Alert tone="danger">{t(`experience.${error}`)}</Alert></div>{/if}
		{#if exportError}<div class="mt-4"><Alert tone="danger">{t('experience.exportFailed')}</Alert></div>{/if}
		{#if exportComplete}<p class="mt-4 text-sm text-ink-2" role="status">{t('experience.exportComplete')}</p>{/if}
		{#if response && applied}
			<div class="mt-6 space-y-3" data-experience-coverage>
				<Alert tone="warning" title={t('experience.partial')}>{t('experience.coverageNotice')}</Alert>
				{#if response.coverage.partial || response.has_more || projectionPartial}<p class="break-words text-sm text-ink-2">{t('experience.partialReasons')}: {response.coverage.reasons.map(reason => t(replayValue('reason', reason))).join(' · ') || t('experience.unknown')}</p>{/if}
				<p class="break-all text-sm text-ink-2">{t('experience.segmentId')}: <span class="font-mono">{applied.segmentId}</span></p>
				<p class="text-sm text-ink-2">{t('experience.orderNotice')}</p>
			</div>
			{#if !rows.length}<p class="mt-4 text-sm text-ink-2" role="status">{t('experience.empty')}</p>
			{:else}
				<ol class="mt-4 divide-y divide-line" aria-label={t('experience.timeline')}>
					{#each rows as row (row.id)}
						{@const restored = retainedReplayMessage(row, response.catalogs)}
						{@const cause = replayCause(row, rows)}
						{@const httpStatus = replayHttpStatus(row)}
						<li class="min-w-0 py-4" data-experience-event={row.event_type}>
							<h3 class="break-words text-sm font-semibold text-ink-0">{t(replayLabel(row))} · {row.event_type}</h3>
							<p class="mt-1 break-words text-sm text-ink-2">{t(replaySource(row.source))} · {t(replayStatus(row.status))} · {t(replayValue('stage', row.stage ?? row.payload.stage))}</p>
							{#if httpStatus != null}<p class="mt-1 text-sm tabular-nums text-ink-2">{t('events.httpStatus')}: {httpStatus}</p>{/if}
							{#if row.payload.state}<p class="mt-1 text-sm text-ink-2">{t('experience.viewState')}: {t(replayValue('state', row.payload.state))} · {row.payload.step == null ? t('experience.unknown') : t('experience.step', { step: row.payload.step })}</p>{/if}
							{#if row.payload.reason}<p class="mt-1 break-words text-sm text-ink-2">{t('experience.reason')}: {t(replayValue('reason', row.payload.reason))}</p>{/if}
							{#if row.event_type === 'view.exposure_changed'}<p class="mt-1 text-sm text-ink-2">{t('experience.exposure')}: {t(replayValue('visibility', row.payload.visibility))} · {t('experience.focus')}: {t(replayValue('focus', row.payload.focused))}</p>{/if}
							{#if row.event_type === 'message.presented'}
								<p class="mt-2 break-words text-sm text-ink-2">{t('experience.messageLocale')}: {row.payload.locale ?? t('experience.unknown')} · {t(replayValue('tone', row.payload.tone))}</p>
								<p class="mt-1 whitespace-pre-wrap break-words text-sm text-ink-1" data-experience-message>{row.payload.restoration === 'redacted' ? t('experience.redacted') : restored ?? t('experience.messageUnavailable')}</p>
							{/if}
							<p class="mt-2 break-all text-sm text-ink-2">{t('experience.cause')}: {cause ? cause.event_id : row.caused_by_event_id ? t('experience.causeUnavailable') : t('experience.causeNone')}</p>
							<details class="mt-2">
								<summary class="min-h-11 cursor-pointer py-2 text-sm text-ink-1">{t('experience.details')}</summary>
								<dl class="grid min-w-0 grid-cols-1 gap-3 text-sm md:grid-cols-2">
									{#each fields(row) as [label, value]}<div class="min-w-0"><dt class="text-ink-2">{label}</dt><dd class="mt-1 break-all text-ink-1">{value ?? t('experience.unknown')}</dd></div>{/each}
								</dl>
							</details>
						</li>
					{/each}
				</ol>
			{/if}
			{#if response.has_more}<Button variant="secondary" onclick={() => search(undefined, true)} disabled={loading || exporting || !response.events.length}>{t('experience.more')}</Button>{/if}
		{:else if !loading && !error && !stale}<p class="mt-4 text-sm text-ink-2">{t('experience.idle')}</p>{/if}
	</Card>
</section>
