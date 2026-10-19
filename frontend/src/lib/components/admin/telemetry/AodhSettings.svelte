<script lang="ts">
	import { onMount } from 'svelte';
	import { ActivityIndicator, Alert, Button, Field, FormModal, PageHeader, SelectInput, TableShell, TextareaInput, TextInput } from '$lib/components/ui';
	import { adminTelemetryRequest, TelemetryError, type AlarmType, type AlarmWrite, type AodhDetail, type NativeAlarm, type NativePage } from '$lib/api/adminTelemetry';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { t } from '$lib/i18n/ns/admin-telemetry';
	import { createTelemetryContext, type TelemetryContext } from './context';
	import NativeStatus from './NativeStatus.svelte';

	const types: AlarmType[] = ['gnocchi_resources_threshold', 'gnocchi_aggregation_by_metrics_threshold', 'gnocchi_aggregation_by_resources_threshold', 'event', 'composite', 'loadbalancer_member_health', 'prometheus'];
	const schemes = new Set(['http:', 'https:', 'trust+http:', 'trust+https:', 'zaqar:', 'trust+zaqar:', 'trust+heat:', 'log:']);
	type Draft = {
		identity: number; name: string; description: string; type: AlarmType; enabled: boolean;
		repeat: boolean; severity: 'low' | 'moderate' | 'critical'; rules: Record<string, string>;
		constraints: string; alarmActions: string; okActions: string; insufficientActions: string;
		guided: boolean; metric: string; resourceType: string; resourceId: string; aggregation: string;
		operator: string; threshold: string; granularity: string; periods: string;
	};
	let context: TelemetryContext | undefined;
	let allowed = $state(false);
	let alarms = $state<NativePage<NativeAlarm> | null>(null);
	let selected = $state<string | null>(null);
	let draft = $state<Draft | null>(null);
	let open = $state(false);
	let loading = $state(false);
	let selecting = $state(false);
	let busy = $state(false);
	let error = $state<'failed' | 'invalid' | null>(null);
	let notice = $state<'saved' | 'deleted' | 'rereadComplete' | null>(null);
	let uncertain = $state<{ id: string | null } | null>(null);
	let marker = $state<string | null>(null);
	let listRequest = 0;
	let selectionRequest = 0;
	let identity = 0;
	let operation = 0;

	function clearPrivate() {
		++listRequest; ++selectionRequest; ++identity; ++operation;
		alarms = null; selected = null; draft = null; open = false; marker = null;
		loading = false; selecting = false; busy = false; error = null; notice = null; uncertain = null;
		allowed = false;
	}

	onMount(() => {
		let initial = true;
		function activate() {
			allowed = context?.allowed() ?? false;
			if (!allowed) return;
			void loadList(null);
			if (!initial) return;
			initial = false;
			const params = new URL(window.location.href).searchParams;
			const alarm = params.get('alarm');
			if (alarm && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(alarm)) void selectAlarm(alarm);
			else if (params.get('create') === '1') createAlarm();
		}
		context = createTelemetryContext(() => { clearPrivate(); queueMicrotask(activate); });
		activate();
		return () => { context?.dispose(); clearPrivate(); };
	});

	async function loadList(next: string | null, explicit = false) {
		const capture = context?.capture();
		if (!capture || busy) return;
		const request = ++listRequest;
		const mutation = operation;
		loading = true; error = null;
		try {
			const response = await adminTelemetryRequest<NativePage<NativeAlarm>>(`/aodh/alarms?limit=25${next ? `&marker=${encodeURIComponent(next)}` : ''}`, capture.authority);
			if (!capture.current() || request !== listRequest || operation !== mutation || busy) return;
			alarms = response; marker = next;
			if (explicit && response.status === 'available') {
				uncertain = null; closeDraft(); notice = 'rereadComplete';
			}
		} catch { if (capture.current() && request === listRequest) error = 'failed'; }
		finally { if (capture.current() && request === listRequest) loading = false; }
	}

	function makeDraft(alarm?: NativeAlarm): Draft {
		return {
			identity: ++identity, name: alarm?.name ?? '', description: alarm?.description ?? '',
			type: alarm?.type ?? 'gnocchi_resources_threshold', enabled: alarm?.enabled ?? true,
			repeat: alarm?.repeat_actions ?? false, severity: alarm?.severity ?? 'low',
			rules: Object.fromEntries(types.map(type => [type, JSON.stringify(alarm?.[`${type}_rule`] ?? {}, null, 2)])),
			constraints: JSON.stringify(alarm?.time_constraints ?? [], null, 2),
			alarmActions: (alarm?.alarm_actions ?? []).join('\n'), okActions: (alarm?.ok_actions ?? []).join('\n'),
			insufficientActions: (alarm?.insufficient_data_actions ?? []).join('\n'),
			guided: !alarm, metric: '', resourceType: 'instance', resourceId: '', aggregation: 'mean',
			operator: 'gt', threshold: '80', granularity: '60', periods: '1',
		};
	}

	function createAlarm() {
		if (!context?.allowed() || busy || uncertain) return;
		++selectionRequest; selected = null; draft = makeDraft(); open = true; error = null; notice = null;
	}
	function closeDraft() {
		++selectionRequest; ++identity; selected = null; draft = null; open = false; selecting = false;
	}
	async function selectAlarm(id: string, explicit = false) {
		const capture = context?.capture();
		if (!capture || busy) return;
		const request = ++selectionRequest;
		const mutation = operation;
		selected = id; draft = null; open = false; selecting = true; error = null; notice = null;
		try {
			const response = await adminTelemetryRequest<AodhDetail>(`/aodh/alarms/${encodeURIComponent(id)}`, capture.authority);
			if (!capture.current() || request !== selectionRequest || selected !== id || operation !== mutation || busy) return;
			if (!response.alarm || response.alarm.alarm_id !== id) { error = 'failed'; return; }
			if (!types.includes(response.alarm.type) || !response.alarm[`${response.alarm.type}_rule`]
				|| typeof response.alarm[`${response.alarm.type}_rule`] !== 'object'
				|| Array.isArray(response.alarm[`${response.alarm.type}_rule`])) { error = 'invalid'; return; }
			draft = makeDraft(response.alarm); open = true;
			if (explicit && uncertain?.id === id) { uncertain = null; notice = 'rereadComplete'; }
		} catch { if (capture.current() && request === selectionRequest) error = 'failed'; }
		finally { if (capture.current() && request === selectionRequest) selecting = false; }
	}

	function object(value: unknown): Record<string, unknown> {
		if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('shape');
		return value as Record<string, unknown>;
	}
	function guidedRule(value: Draft) {
		const threshold = Number(value.threshold), granularity = Number(value.granularity), periods = Number(value.periods);
		if (!value.threshold.trim() || !value.granularity.trim() || !value.periods.trim()
			|| ![threshold, granularity, periods].every(Number.isFinite)) throw new Error('shape');
		return { metric: value.metric, resource_type: value.resourceType, resource_id: value.resourceId,
			aggregation_method: value.aggregation, comparison_operator: value.operator, threshold, granularity, evaluation_periods: periods };
	}
	function advancedRule() {
		if (!draft) return;
		try { draft.rules[draft.type] = JSON.stringify(guidedRule(draft), null, 2); draft.guided = false; error = null; }
		catch { error = 'invalid'; }
	}
	function actionList(text: string) {
		const urls = text.split(/\r?\n/).map(url => url.trim()).filter(Boolean);
		for (const url of urls) {
			const parsed = new URL(url);
			if (!schemes.has(parsed.protocol) || !url.includes('://') || /\s/.test(url)
				|| (parsed.protocol.startsWith('trust+') && (parsed.username || parsed.password))
				|| (['http:', 'https:', 'trust+http:', 'trust+https:'].includes(parsed.protocol) && !parsed.hostname)) throw new Error('scheme');
		}
		return urls;
	}
	function payload(value: Draft): AlarmWrite {
		if (!value.name.trim()) throw new Error('name');
		const constraints: unknown = JSON.parse(value.constraints);
		if (!Array.isArray(constraints)) throw new Error('shape');
		const timeConstraints = constraints.map(object);
		return { name: value.name, description: value.description, type: value.type, enabled: value.enabled,
			repeat_actions: value.repeat, severity: value.severity, time_constraints: timeConstraints,
			alarm_actions: actionList(value.alarmActions), ok_actions: actionList(value.okActions),
			insufficient_data_actions: actionList(value.insufficientActions),
			[`${value.type}_rule`]: value.guided && value.type === 'gnocchi_resources_threshold' ? guidedRule(value) : object(JSON.parse(value.rules[value.type])),
		};
	}

	async function mutate(deleting = false) {
		const capture = context?.capture();
		if (!capture || !draft || busy || uncertain || (deleting && !selected)) return;
		const id = selected, draftId = draft.identity, snapshot = JSON.stringify(draft), selection = selectionRequest;
		let body: AlarmWrite | undefined;
		try { if (!deleting) body = payload(draft); } catch { error = 'invalid'; return; }
		const ticket = ++operation;
		busy = true; error = null; notice = null;
		const current = () => capture.current() && operation === ticket && selectionRequest === selection
			&& selected === id && draft?.identity === draftId && JSON.stringify(draft) === snapshot && !uncertain;
		try {
			const trust = body && [...body.alarm_actions, ...body.ok_actions, ...body.insufficient_data_actions].some(url => /^trust\+/i.test(url));
			if (deleting || trust) {
				const confirmed = await confirmDialog(deleting ? t('settings.deleteConfirm') : t('settings.trustConfirm'), {
					confirmLabel: t(deleting ? 'settings.delete' : 'settings.save'), confirmVariant: deleting ? 'danger' : 'primary',
				});
				if (!confirmed || !current()) return;
			}
			if (!current()) return;
			await adminTelemetryRequest<NativeAlarm | void>(`/aodh/alarms${id ? `/${encodeURIComponent(id)}` : ''}`, capture.authority,
				{ method: deleting ? 'DELETE' : id ? 'PUT' : 'POST', ...(body ? { body } : {}) });
			if (!current()) return;
			closeDraft(); notice = deleting ? 'deleted' : 'saved';
		} catch (failure) {
			if (!capture.current() || operation !== ticket) return;
			if (!(failure instanceof TelemetryError) || failure.uncertain || failure.code === 'telemetry_mutation_uncertain') uncertain = { id };
			else error = failure.status === 400 ? 'invalid' : 'failed';
		} finally {
			if (capture.current() && operation === ticket) {
				busy = false;
				if (!draft && !uncertain) void loadList(marker);
			}
		}
	}
</script>

<PageHeader breadcrumb={t('aodh.breadcrumb')} title={t('settings.title')} subtitle={t('settings.description')}>
	{#snippet actions()}
		<a class="dashboard-link" href="/admin/monitoring/aodh">{t('settings.dashboard')}</a>
		<Button variant="secondary" disabled={!allowed || busy || loading} onclick={() => loadList(null, true)}>{t('settings.refresh')}</Button>
		<Button variant="primary" disabled={!allowed || busy || !!uncertain} onclick={createAlarm}>{t('settings.create')}</Button>
	{/snippet}
</PageHeader>
<div class="settings-console">
	{#if !allowed}<Alert tone="warning">{t('settings.noAuthority')}</Alert>{/if}
	{#if error}<Alert tone="danger">{t(error === 'invalid' ? 'settings.invalid' : 'settings.failed')}</Alert>{/if}
	{#if notice}<p role="status" class="notice">{t(`settings.${notice}`)}</p>{/if}
	{#if uncertain}
		<Alert tone="warning">{t('settings.uncertain')}</Alert>
		{#if uncertain.id}<Button variant="secondary" disabled={busy || selecting} onclick={() => uncertain?.id && selectAlarm(uncertain.id, true)}>{t('settings.reread')}</Button>{/if}
	{/if}
	{#if loading || selecting}<ActivityIndicator label={t('settings.loading')} />{/if}
	{#if alarms}
		<NativeStatus status={alarms.status} error={alarms.error} />
		<div class="alarm-region" role="region" aria-label={t('settings.title')}>
		<TableShell density="compact">
			<table tabindex="0" aria-label={t('settings.title')}>
				<thead><tr><th>{t('settings.name')}</th><th>{t('settings.type')}</th><th>{t('settings.state')}</th><th>{t('settings.severity')}</th></tr></thead>
				<tbody>{#each alarms.items as alarm (alarm.alarm_id)}
					<tr data-selected={selected === alarm.alarm_id}><td><button class="alarm-select" disabled={busy} onclick={() => selectAlarm(alarm.alarm_id)}>{alarm.name}</button><div class="identifier">{alarm.alarm_id}</div></td><td>{alarm.type}</td><td>{alarm.state ?? t('settings.unknown')}</td><td>{alarm.severity ?? t('settings.unknown')}</td></tr>
				{:else}<tr><td colspan="4">{t(alarms.status === 'available' ? 'settings.empty' : 'settings.rowsUnknown')}</td></tr>{/each}</tbody>
			</table>
		</TableShell>
		</div>
		{#if alarms.truncated}<p class="support">{t('settings.truncated')}</p>{/if}
		<div class="paging"><Button variant="secondary" disabled={!marker || loading || busy} onclick={() => loadList(null)}>{t('settings.first')}</Button><Button variant="secondary" disabled={!alarms.next_marker || loading || busy} onclick={() => loadList(alarms?.next_marker ?? null)}>{t('settings.next')}</Button></div>
	{/if}
	<section class="delivery" aria-labelledby="delivery-title">
		<h2 id="delivery-title">{t('settings.deliveryTitle')}</h2>
		<p>{t('settings.actionsHelp')}</p><p>{t('settings.webhookHelp')}</p><p>{t('settings.trustHelp')}</p>
		<p>{t('settings.zaqarHelp')}</p><p>{t('settings.logHelp')}</p><p>{t('settings.heatHelp')}</p><p>{t('settings.catalogHelp')}</p>
		<pre>https://receiver.example.invalid/aodh
trust+https://receiver.example.invalid/heat-signal
trust+heat://
zaqar://?topic=ops&amp;subscriber=mailto%3A//ops%40example.invalid&amp;ttl=3600
trust+zaqar://?queue_name=ops
log://</pre>
	</section>
</div>
<FormModal bind:open title={t(selected ? 'settings.edit' : 'settings.create')} onClose={closeDraft} submitting={busy}>
	{#if draft}
		<div class="form-fields">
			{#if error}<Alert tone="danger">{t(error === 'invalid' ? 'settings.invalid' : 'settings.failed')}</Alert>{/if}
			{#if uncertain}<Alert tone="warning">{t('settings.uncertain')}</Alert>{/if}
			<fieldset disabled={busy || !!uncertain}>
				<Field label={t('settings.name')} for="aodh-name" required><TextInput id="aodh-name" bind:value={draft.name} /></Field>
				<Field label={t('settings.descriptionField')} for="aodh-description"><TextareaInput id="aodh-description" rows={2} bind:value={draft.description} /></Field>
				<div class="form-grid">
					<Field label={t('settings.type')} for="aodh-type"><SelectInput id="aodh-type" bind:value={draft.type}>{#each types as type}<option value={type}>{type}</option>{/each}</SelectInput></Field>
					<Field label={t('settings.severity')} for="aodh-severity"><SelectInput id="aodh-severity" bind:value={draft.severity}><option value="low">{t('settings.low')}</option><option value="moderate">{t('settings.moderate')}</option><option value="critical">{t('settings.critical')}</option></SelectInput></Field>
				</div>
				<div class="checks"><label><input type="checkbox" bind:checked={draft.enabled} /> {t('settings.enabled')}</label><label><input type="checkbox" bind:checked={draft.repeat} /> {t('settings.repeat')}</label></div>
				{#if draft.guided && draft.type === 'gnocchi_resources_threshold'}
					<h3>{t('settings.guided')}</h3>
					<div class="form-grid">
						<Field label={t('settings.metric')} for="aodh-metric"><TextInput id="aodh-metric" bind:value={draft.metric} /></Field>
						<Field label={t('settings.resourceType')} for="aodh-resource-type"><TextInput id="aodh-resource-type" bind:value={draft.resourceType} /></Field>
						<Field label={t('settings.aggregation')} for="aodh-aggregation"><TextInput id="aodh-aggregation" bind:value={draft.aggregation} /></Field>
						<Field label={t('settings.operator')} for="aodh-operator"><SelectInput id="aodh-operator" bind:value={draft.operator}>{#each ['gt', 'ge', 'eq', 'ne', 'le', 'lt'] as operator}<option value={operator}>{operator}</option>{/each}</SelectInput></Field>
						<Field label={t('settings.threshold')} for="aodh-threshold"><TextInput id="aodh-threshold" bind:value={draft.threshold} inputmode="decimal" /></Field>
						<Field label={t('settings.granularity')} for="aodh-granularity"><TextInput id="aodh-granularity" bind:value={draft.granularity} inputmode="decimal" /></Field>
						<Field label={t('settings.periods')} for="aodh-periods"><TextInput id="aodh-periods" bind:value={draft.periods} inputmode="numeric" /></Field>
					</div>
					<Field label={t('settings.resourceId')} for="aodh-resource-id" required><TextInput id="aodh-resource-id" bind:value={draft.resourceId} /></Field>
					<Button variant="secondary" onclick={advancedRule}>{t('settings.advanced')}</Button>
				{:else}
					<Field label={t('settings.rule')} for="aodh-rule" help={t('settings.ruleHelp')}><TextareaInput id="aodh-rule" rows={8} bind:value={draft.rules[draft.type]} /></Field>
				{/if}
				<Field label={t('settings.constraints')} for="aodh-constraints" help={t('settings.constraintsHelp')}><TextareaInput id="aodh-constraints" bind:value={draft.constraints} /></Field>
				<p class="support">{t('settings.actionsHelp')}</p><p class="support">{t('settings.trustHelp')}</p>
				<Field label={t('settings.alarmActions')} for="aodh-alarm-actions"><TextareaInput id="aodh-alarm-actions" rows={3} bind:value={draft.alarmActions} /></Field>
				<Field label={t('settings.okActions')} for="aodh-ok-actions"><TextareaInput id="aodh-ok-actions" rows={3} bind:value={draft.okActions} /></Field>
				<Field label={t('settings.insufficientActions')} for="aodh-insufficient-actions"><TextareaInput id="aodh-insufficient-actions" rows={3} bind:value={draft.insufficientActions} /></Field>
			</fieldset>
		</div>
	{/if}
	{#snippet actions()}
		<div class="modal-actions">
		<Button variant="secondary" disabled={busy} onclick={closeDraft}>{t('settings.cancel')}</Button>
		{#if uncertain}
			{#if uncertain.id}<Button variant="secondary" disabled={busy || selecting} onclick={() => uncertain?.id && selectAlarm(uncertain.id, true)}>{t('settings.reread')}</Button>{/if}
			<Button variant="secondary" disabled={busy || loading} onclick={() => loadList(null, true)}>{t('settings.refresh')}</Button>
		{/if}
		{#if selected}<Button variant="danger" disabled={busy || !!uncertain || !draft} onclick={() => mutate(true)}>{t('settings.delete')}</Button>{/if}
		<Button variant="primary" disabled={busy || !!uncertain || !draft} onclick={() => mutate()}>{t('settings.save')}</Button>
		</div>
	{/snippet}
</FormModal>

<style>
	.settings-console, .form-fields, fieldset { display: grid; gap: 1rem; min-width: 0; }
	fieldset { border: 0; padding: 0; margin: 0; }
	.form-grid { display: grid; grid-template-columns: minmax(0, 1fr); gap: 0.75rem; }
	.checks, .paging { display: flex; flex-wrap: wrap; gap: 1rem; align-items: center; }
	.modal-actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 0.5rem; min-width: 0; }
	.alarm-region { min-width: 0; overflow-x: auto; border-radius: var(--radius-lg); }
	.alarm-region :global(.table-shell) { min-width: max-content; overflow-x: visible; }
	.checks label { font-size: 0.8125rem; color: var(--color-ink-1); }
	.dashboard-link, .alarm-select { color: var(--color-accent); font-size: 0.8125rem; text-decoration: underline; text-underline-offset: 3px; }
	.alarm-select { cursor: pointer; text-align: left; }
	.identifier, pre { font-family: var(--font-mono); font-size: 0.75rem; }
	.identifier, .support, .delivery p { color: var(--color-ink-2); font-size: 0.75rem; line-height: 1.5; }
	.delivery { border-top: 1px solid var(--color-line); padding-top: 1rem; }
	h2, h3 { color: var(--color-ink-0); font-size: 0.875rem; font-weight: 600; margin: 0; }
	pre { color: var(--color-ink-1); white-space: pre-wrap; overflow-wrap: anywhere; }
	.notice { color: var(--color-ink-1); font-size: 0.8125rem; }
	@media (min-width: 768px) { .form-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
</style>
