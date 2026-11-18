<script lang="ts">
	import { untrack } from 'svelte';
	import { ApiError } from '$lib/api/client';
	import { instanceRecoveryApi } from '$lib/api/instanceRecovery';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import Modal from '$lib/components/ui/Modal.svelte';
	import Pill from '$lib/components/ui/Pill.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import { t } from '$lib/i18n/ns/admin-compute';
	import RichText from '$lib/i18n/RichText.svelte';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import { auth } from '$lib/stores/auth';
	import type { RecoveryAnalysis, RecoveryObservation, RecoveryResult, RecoveryStep } from '$lib/types/adminInstance';

	interface Props {
		serverId: string;
		serverName: string;
		onClose: () => void;
		onRefresh?: () => void;
		onRecovered?: () => void;
	}

	let { serverId, serverName, onClose, onRefresh, onRecovered }: Props = $props();
	const uid = $props.id();
	const token = $derived($auth.token);
	const hasToken = $derived(Boolean(token));
	const projectId = $derived($auth.projectId ?? undefined);
	const userId = $derived($auth.userId);

	type Phase = 'loading' | 'analyzed' | 'executing' | 'done' | 'error';
	type Failure = 'analysis' | 'blocked' | 'inProgress' | 'planChanged' | 'serviceUnavailable' | 'unknown';
	const POLL_INTERVAL_MS = 4_000;
	const POLL_WINDOW_MS = 60_000;
	let open = $state(true);
	let phase = $state<Phase>('loading');
	let analysis = $state.raw<RecoveryAnalysis | null>(null);
	const targetName = $derived(analysis?.server.name || serverName || serverId);
	let result = $state.raw<RecoveryResult | null>(null);
	let observation = $state.raw<RecoveryObservation | null>(null);
	const latest = $derived(observation ?? result);
	const recovered = $derived(result?.observation_may_recover && latest?.recovered);
	let observing = $state(false);
	let failure = $state<Failure | null>(null);
	let failureDetail = $state('');
	let confirmation = $state('');
	let operation = $state.raw<AbortController | null>(null);

	const guestRestart = $derived(analysis?.steps.some(step => step.action === 'hard_reboot') ?? false);
	const dateFormat = $derived(new Intl.DateTimeFormat(intlLocale(), { dateStyle: 'medium', timeStyle: 'long' }));
	const failureLabels = $derived<Record<Failure, string>>({
		analysis: t('instances.recovery.analysisFailed'),
		blocked: t('instances.recovery.blocked'),
		inProgress: t('instances.recovery.inProgress'),
		planChanged: t('instances.recovery.planChanged'),
		serviceUnavailable: t('instances.recovery.serviceUnavailable'),
		unknown: t('instances.recovery.executeFailed'),
	});
	const scenarioLabels = $derived<Record<string, string>>({
		migration_failed_volume_stuck: t('instances.recovery.scenario.migrationVolume'),
		volume_stuck: t('instances.recovery.scenario.volume'),
		generic_error: t('instances.recovery.scenario.error'),
		live_migration_rolled_back: t('instances.recovery.scenario.liveRollback'),
		manual_review: t('instances.recovery.scenario.manual'),
	});
	const checkLabels = $derived<Record<string, string>>({
		is_error_state: t('instances.recovery.check.errorState'),
		volume_backed: t('instances.recovery.check.volumeBacked'),
		ports_healthy: t('instances.recovery.check.portsHealthy'),
		migrations_known: t('instances.recovery.check.migrationsKnown'),
		volumes_known: t('instances.recovery.check.volumesKnown'),
		no_task_in_progress: t('instances.recovery.check.noTask'),
		live_migration_source: t('instances.recovery.check.liveSource'),
		live_migration_rollback: t('instances.recovery.check.liveRollback'),
		live_migration_ports: t('instances.recovery.check.livePorts'),
		live_migration_volumes: t('instances.recovery.check.liveVolumes'),
		live_migration_placement: t('instances.recovery.check.livePlacement'),
		live_migration_power_state: t('instances.recovery.check.livePower'),
	});

	function stepLabel(step: RecoveryStep): string {
		switch (step.action) {
			case 'reset_volume_state':
				return step.params?.volume_id
					? t('instances.recovery.step.resetNamedVolume', { volume: step.params.volume_id })
					: t('instances.recovery.step.resetVolume');
			case 'reset_server_state': return t('instances.recovery.step.resetServer');
			case 'hard_reboot': return t('instances.recovery.step.hardRestart');
			default: return step.description;
		}
	}

	function novaTimestamp(value: string | null): string | null {
		if (!value?.includes('T')) return null;
		const timestamp = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(value) ? value : `${value}Z`;
		return Number.isFinite(Date.parse(timestamp)) ? timestamp : null;
	}

	function fail(kind: Failure, error?: unknown) {
		failure = kind;
		failureDetail = error instanceof ApiError ? error.message : '';
		phase = 'error';
	}

	async function load(id: string, requestToken: string, project: string | undefined, signal: AbortSignal) {
		try {
			const evidence = await instanceRecoveryApi.analyze(id, { token: requestToken, projectId: project, signal });
			if (signal.aborted) return;
			if (evidence.server.id !== id || (evidence.auto_executable && !evidence.plan_fingerprint)) {
				fail('analysis');
				return;
			}
			analysis = evidence;
			phase = 'analyzed';
		} catch (error) {
			if (!signal.aborted) fail('analysis', error);
		}
	}

	async function execute(event: SubmitEvent) {
		event.preventDefault();
		const signal = operation?.signal;
		if (phase !== 'analyzed' || analysis?.server.id !== serverId || !analysis.auto_executable || !analysis.plan_fingerprint
			|| confirmation !== targetName || !token || !signal || signal.aborted) return;
		phase = 'executing';
		try {
			const outcome = await instanceRecoveryApi.execute(serverId, { plan_fingerprint: analysis.plan_fingerprint }, { token, projectId, signal });
			if (signal.aborted) return;
			result = outcome;
			phase = 'done';
		} catch (error) {
			if (signal.aborted) return;
			if (error instanceof ApiError && error.status === 409) {
				fail(error.code === 'RECOVERY_IN_PROGRESS' ? 'inProgress'
					: error.code === 'RECOVERY_PLAN_CHANGED' ? 'planChanged' : 'blocked');
			} else if (error instanceof ApiError && error.status === 503) {
				fail('serviceUnavailable');
			} else {
				fail('unknown', error);
			}
		}
	}

	function close() {
		if (phase === 'executing') return;
		open = false;
		operation?.abort();
		onClose();
		// Refresh after closing so the result remains readable even if the parent re-renders.
		if (failure === 'unknown' || result?.executed || result?.steps.some(step => step.status && step.status !== 'skipped')) onRefresh?.();
		if (recovered) onRecovered?.();
	}

	$effect(() => {
		const id = serverId;
		const project = projectId;
		// Restart on ownership changes, not routine bearer rotation.
		userId;
		const requestToken = hasToken ? untrack(() => token) : null;
		const active = new AbortController();
		operation = active;
		analysis = null;
		result = null;
		observation = null;
		confirmation = '';
		failure = null;
		failureDetail = '';
		if (requestToken) {
			phase = 'loading';
			void load(id, requestToken, project, active.signal);
		} else {
			fail('analysis');
		}
		return () => active.abort();
	});

	$effect(() => {
		const outcome = result;
		if (!open || !operation || !outcome || outcome.observation_terminal
			|| !(outcome.unconfirmed_action || (outcome.executed && outcome.observation_timed_out))) return;

		const id = serverId;
		const project = projectId;
		const requestedAt = outcome.requested_at;
		const { unconfirmed_action: unconfirmedAction, observation_may_recover: mayRecover } = outcome;
		let accepted = outcome.observed_acceptance;
		const pollController = new AbortController();
		const signal = AbortSignal.any([pollController.signal, operation.signal]);
		let next: ReturnType<typeof setTimeout>;
		const deadline = setTimeout(stop, POLL_WINDOW_MS);
		observing = true;
		next = setTimeout(poll, POLL_INTERVAL_MS);
		return stop;

		function stop() {
			clearTimeout(next);
			clearTimeout(deadline);
			pollController.abort();
			observing = false;
		}

		async function poll() {
			const requestToken = token;
			if (signal.aborted || !requestToken) return;
			try {
				const observed = await instanceRecoveryApi.status(id, requestedAt, {
					token: requestToken, projectId: project, signal,
				}, { unconfirmedAction: accepted ? null : unconfirmedAction, mayRecover });
				if (signal.aborted) return;
				accepted ||= observed.observed_acceptance;
				if (observed.observed_status !== 'UNKNOWN') observation = observed;
				if (observed.observation_terminal) {
					stop();
					return;
				}
			} catch {
				// A failed read does not replace the last Nova observation.
			}
			if (!signal.aborted) next = setTimeout(poll, POLL_INTERVAL_MS);
		}
	});
</script>

{#snippet timestamp(value: string | null)}
	{@const time = novaTimestamp(value)}
	{#if time}
		<time datetime={time}>{dateFormat.format(Date.parse(time))}</time>
	{:else}
		{t('instances.recovery.unavailable')}
	{/if}
{/snippet}

<Modal bind:open onClose={close} dismissible={phase !== 'executing'} labelledBy={`${uid}-title`}>
	<Card surface="modal" padding="none" class="w-[40rem] max-w-full">
		<header class="border-b border-line px-4 py-4 sm:px-6">
			<h2 id={`${uid}-title`} class="text-base font-semibold">{t('instances.recovery.title')}</h2>
			<p class="mt-1 break-all text-sm font-medium"><bdi>{targetName}</bdi></p>
			<p class="break-all font-mono text-xs text-ink-2">{serverId}</p>
		</header>

		<form onsubmit={execute}>
			<div class="max-h-[60dvh] space-y-5 overflow-y-auto overscroll-contain px-4 py-4 sm:px-6">
				{#if phase === 'loading'}
					<LoadingState variant="section" label={t('instances.recovery.analyzing')} />
				{/if}
				{#if failure}
					<Alert tone={failure === 'analysis' || failure === 'unknown' ? 'danger' : 'warning'}>
						<p>{failureLabels[failure]}</p>
						{#if failureDetail}<p class="mt-1 break-words">{failureDetail}</p>{/if}
					</Alert>
				{/if}

				{#if analysis}
					{@const fault = latest ? latest.observed_fault : analysis.server.fault}
					{@const migration = analysis.last_error_migration}
					{#if phase === 'done' && result && latest}
						{@const terminalError = latest.observation_terminal && latest.observed_status === 'ERROR'}
						{@const stillRebooting = latest.observed_status === 'ERROR' && latest.observed_task_state?.startsWith('reboot')
							&& (result.observation_timed_out || result.unconfirmed_action)}
						<Alert tone={recovered ? 'success' : terminalError || (!result.executed && !result.unconfirmed_action) ? 'danger' : 'warning'}>
							<p>{recovered ? t('instances.recovery.complete')
								: terminalError && (result.executed || result.unconfirmed_action) ? t('instances.recovery.endedInError')
								: result.unconfirmed_action ? t('instances.recovery.unconfirmedRequest')
								: !result.executed ? t('instances.recovery.failed')
								: stillRebooting ? t('instances.recovery.stillRebooting')
								: t('instances.recovery.acceptedUnconfirmed')}</p>
							{#if stillRebooting && result.unconfirmed_action}<p>{t('instances.recovery.stillRebooting')}</p>{/if}
							<p>{t('instances.recovery.observedStatus', { status: latest.observed_status })}</p>
							{#if latest.observed_task_state}
								<p class="break-words">{t('instances.recovery.observedTask', { task: latest.observed_task_state })}</p>
							{/if}
							{#if observing}<p>{t('instances.recovery.checkingStatus')}</p>{/if}
						</Alert>
						<h3 class="section-title">{t('instances.recovery.results')}</h3>
						<ol class="space-y-1">
							{#each result.steps as step, i (i)}
								<li class="flex flex-wrap items-baseline gap-x-2 text-sm">
									<span>{stepLabel(step)}</span>
									{#if step.status}
										<Pill tone={step.status === 'success' ? 'success' : step.status === 'failed' ? 'danger' : step.status === 'unconfirmed' ? 'warning' : 'neutral'} size="xs">
											{step.status === 'success' ? t('instances.recovery.step.accepted')
												: step.status === 'failed' ? t('instances.recovery.step.failed')
												: step.status === 'unconfirmed' ? t('instances.recovery.step.unconfirmed')
												: t('instances.recovery.step.skipped')}
										</Pill>
									{/if}
									{#if step.detail && (step.status === 'failed' || step.action === 'reset_volume_state')}
										<p class="w-full break-words text-xs text-ink-2">{step.detail}</p>
									{/if}
								</li>
							{/each}
						</ol>
					{:else if phase === 'analyzed' || phase === 'executing'}
						{#if analysis.auto_executable}
							<Alert tone={guestRestart ? 'warning' : 'info'} title={t('instances.recovery.executableTitle')}>
								{guestRestart ? t('instances.recovery.hardRestart') : t('instances.recovery.noRestart')}
							</Alert>
						{:else}
							<Alert tone="warning" title={t('instances.recovery.manualTitle')}>{t('instances.recovery.manualHelp')}</Alert>
						{/if}
					{/if}

					<div class="flex flex-wrap items-baseline gap-x-2 text-sm">
						<h3 class="section-title">{t('instances.recovery.scenarioLabel')}</h3>
						<p>{scenarioLabels[analysis.scenario] ?? analysis.scenario}</p>
					</div>

					<div class="grid gap-4 sm:grid-cols-2">
						<section class="evidence" aria-labelledby={`${uid}-fault`}>
							<h3 id={`${uid}-fault`} class="section-title">{t('instances.recovery.faultMessage')}</h3>
							{#if fault}
								<p class="break-words font-mono text-xs">{fault.message ?? t('instances.recovery.unavailable')}</p>
								<dl class="facts">
									{#if fault.code != null}
										<dt>{t('instances.recovery.faultCode')}</dt><dd>{fault.code}</dd>
									{/if}
									<dt>{t('instances.recovery.recordedAt')}</dt><dd>{@render timestamp(fault.created)}</dd>
								</dl>
							{:else}
								<p>{(latest?.observed_status ?? analysis.server.status) === 'UNKNOWN' ? t('instances.recovery.unavailable')
									: latest ? t('instances.recovery.noObservedFault') : t('instances.recovery.noFault')}</p>
							{/if}
						</section>
						<section class="evidence" aria-labelledby={`${uid}-migration`}>
							<h3 id={`${uid}-migration`} class="section-title">{t('instances.recovery.lastMigration')}</h3>
							{#if migration}
								<dl class="facts">
									<dt>{t('instances.recovery.migrationType')}</dt><dd>{migration.migration_type}</dd>
									<dt>{t('instances.recovery.source')}</dt><dd>{migration.source_compute ?? t('instances.recovery.unavailable')}</dd>
									<dt>{t('instances.recovery.destination')}</dt><dd>{migration.dest_compute ?? t('instances.recovery.unavailable')}</dd>
									<dt>{t('instances.recovery.startedAt')}</dt><dd>{@render timestamp(migration.created_at)}</dd>
									<dt>{t('instances.recovery.updatedAt')}</dt><dd>{@render timestamp(migration.updated_at)}</dd>
								</dl>
							{:else if analysis.checks.some(check => check.key === 'migrations_known' && !check.passed)}
								<p>{t('instances.recovery.unavailable')}</p>
							{:else}
								<p>{t('instances.recovery.noMigration')}</p>
							{/if}
						</section>
					</div>

					<section>
						<h3 class="section-title mb-2">{t('instances.recovery.safetyChecks')}</h3>
						<ul class="space-y-2">
							{#each analysis.checks as check (check.key)}
								<li class="flex flex-wrap items-baseline gap-x-2 text-sm">
									<span>{checkLabels[check.key] ?? check.label}</span>
									<Pill tone={check.passed ? 'success' : 'danger'} size="xs">
										{check.passed ? t('instances.recovery.check.passed') : t('instances.recovery.check.notPassed')}
									</Pill>
									{#if check.detail}<p class="w-full break-words text-xs text-ink-2">{check.detail}</p>{/if}
								</li>
							{/each}
						</ul>
					</section>

					{#if analysis.placement_note}
						{#snippet placementWarning(text: string)}<strong>{text}</strong>{/snippet}
						<Alert tone="warning">
							<RichText segments={t.rich('instances.recovery.placementNote', { note: analysis.placement_note })} tags={{ warning: placementWarning }} />
						</Alert>
					{/if}

					{#if analysis.auto_executable && analysis.plan_fingerprint && (phase === 'analyzed' || phase === 'executing')}
						<section>
							<h3 class="section-title mb-2">{t('instances.recovery.recommendedSteps')}</h3>
							<ol class="list-decimal space-y-1 pl-5 text-sm">
								{#each analysis.steps as step, i (i)}
									<li class="break-words">{stepLabel(step)}</li>
								{/each}
							</ol>
						</section>
						<Field for={`${uid}-confirmation`} label={t('instances.recovery.confirmLabel')} help={t('instances.recovery.confirm', { name: targetName })} required>
							<TextInput id={`${uid}-confirmation`} bind:value={confirmation} autocomplete="off" disabled={phase === 'executing'} required />
						</Field>
					{/if}
				{/if}
			</div>

			<footer class="flex flex-wrap items-center justify-end gap-2 border-t border-line px-4 py-3 sm:px-6">
				{#if phase === 'executing'}
					<LoadingState variant="inline" label={t('instances.recovery.executing')} />
				{/if}
				<Button variant="secondary" onclick={close} disabled={phase === 'executing'}>{t('instances.close')}</Button>
				{#if phase === 'analyzed' && analysis?.auto_executable && analysis.plan_fingerprint}
					<Button type="submit" variant="danger" disabled={confirmation !== targetName}>{t('instances.recovery.execute')}</Button>
				{/if}
			</footer>
		</form>
	</Card>
</Modal>

<style>
	.section-title { font-size: var(--type-support); font-weight: 600; }
	.evidence {
		display: grid;
		align-content: start;
		gap: 0.375rem;
		min-width: 0;
		border: 1px solid var(--color-line);
		border-radius: var(--radius-md);
		background: var(--color-surface-sunken);
		padding: 0.75rem;
		font-size: var(--type-support);
	}
	.facts {
		display: grid;
		grid-template-columns: minmax(0, 2fr) minmax(0, 3fr);
		gap: 0.25rem 0.5rem;
		overflow-wrap: anywhere;
	}
	.facts dt { color: var(--color-ink-2); }
</style>
