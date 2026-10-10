<script lang="ts">
	import { untrack } from 'svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import StatusChip from '$lib/components/ui/StatusChip.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import TextareaInput from '$lib/components/ui/TextareaInput.svelte';
	import { t } from '$lib/i18n/ns/admin-compute';
	import {
		hasValidRemovalReview,
		isVerifiedRemoval,
		REMOVAL_CHECK_STATE_KEY,
		type RemovalApproval,
		type RemovalCheck,
		type RemovalInspection,
		type RemovalResult,
		type RemovalServer,
	} from './removal';

	interface Props {
		inspection?: RemovalInspection | null;
		result?: RemovalResult | null;
		invalidReason?: string;
		/** Parent increments this on host/project/status changes and every inspection attempt. */
		approvalRevision: number;
		pending?: boolean;
		onCheck: () => unknown;
		onRemove: (approval: RemovalApproval) => unknown;
	}

	let {
		inspection = null,
		result = null,
		invalidReason = '',
		approvalRevision,
		pending = false,
		onCheck,
		onRemove,
	}: Props = $props();

	const componentId = $props.id();
	const hostnameId = `${componentId}-hostname`;
	const reasonId = `${componentId}-reason`;
	let reviewedMetadata = $state(false);
	let computeStopped = $state(false);
	let confirmHostname = $state('');
	let reason = $state('');
	let localBusy = $state(false);
	let localError = $state<'' | 'hypervisors.removal.checkFailed' | 'hypervisors.removal.requestUnconfirmed'>('');
	let clock = $state(Date.now());
	let formRevision = $state<number | null>(null);
	let formInspection = $state.raw<RemovalInspection | null>(null);
	let invalidatedInspection = $state.raw<RemovalInspection | null>(null);
	let consumedToken = $state<string | null>(null);

	function resetApproval() {
		reviewedMetadata = false;
		computeStopped = false;
		confirmHostname = '';
		reason = '';
	}

	$effect(() => {
		// Read each parent fence even if its visible value does not affect eligibility.
		const nextInspection = inspection;
		const nextRevision = approvalRevision;
		void pending;
		void invalidReason;
		void result;
		untrack(() => {
			resetApproval();
			localError = '';
			formRevision = nextRevision;
			formInspection = nextInspection;
		});
	});

	$effect(() => {
		const expires = Date.parse(inspection?.expires_at ?? '');
		clock = Date.now();
		if (!Number.isFinite(expires) || expires <= Date.now()) return;
		const timer = setTimeout(() => {
			clock = Date.now();
			resetApproval();
		}, expires - Date.now());
		return () => clearTimeout(timer);
	});

	const report = $derived(inspection?.report ?? null);
	const busy = $derived(pending || localBusy);
	const currentForm = $derived(formRevision === approvalRevision && formInspection === inspection);
	const usableReview = $derived(
		currentForm && !invalidReason && !localError && inspection !== invalidatedInspection
		&& hasValidRemovalReview(inspection, clock) && inspection.review_token !== consumedToken,
	);
	const canSubmit = $derived(
		!busy && usableReview && reviewedMetadata && computeStopped
		&& confirmHostname === report?.hostname && reason.trim().length > 0,
	);
	const hostnameError = $derived(
		confirmHostname && confirmHostname !== report?.hostname ? t('hypervisors.removal.hostnameError') : '',
	);
	const reasonError = $derived(reason.length > 0 && !reason.trim() ? t('hypervisors.removal.reasonError') : '');

	async function refreshInspection() {
		if (busy) return;
		resetApproval();
		invalidatedInspection = inspection;
		localError = '';
		localBusy = true;
		try {
			await onCheck();
		} catch {
			localError = 'hypervisors.removal.checkFailed';
		} finally {
			localBusy = false;
		}
	}

	async function submitApproval(event: SubmitEvent) {
		event.preventDefault();
		const current = inspection;
		// Effects and expiry timers may not have run yet. Recheck the live props and wall clock.
		if (busy || !currentForm || invalidReason || localError || current === invalidatedInspection
			|| !hasValidRemovalReview(current, Date.now()) || current.review_token === consumedToken) {
			clock = Date.now();
			resetApproval();
			return;
		}
		if (!reviewedMetadata || !computeStopped || confirmHostname !== current.report.hostname || !reason.trim()) return;
		const approval: RemovalApproval = {
			review_token: current.review_token,
			confirm_hostname: confirmHostname,
			reason: reason.trim(),
			reviewed_metadata: true,
			compute_stopped: true,
		};
		// A failed or unverified request must also get a new one-use review token.
		consumedToken = current.review_token;
		resetApproval();
		localBusy = true;
		try {
			await onRemove(approval);
		} catch {
			localError = 'hypervisors.removal.requestUnconfirmed';
		} finally {
			localBusy = false;
		}
	}
</script>

{#snippet metadata(label: string, value: string | number | boolean | null)}
	<div class="min-w-0 space-y-1">
		<dt class="text-ink-2">{label}</dt>
		<dd class="min-w-0 whitespace-pre-wrap text-ink-0">{value === null ? t('hypervisors.removal.unavailable') : String(value)}</dd>
	</div>
{/snippet}

{#snippet checkList(checks: RemovalCheck[], label: string)}
	<section aria-label={label} class="space-y-2">
		<h4 class="text-sm font-semibold">{label}</h4>
		<ul class="space-y-2">
			{#each checks as check}
				<li class="space-y-1 border-l border-line pl-3" aria-label={`${check.label} (${check.code}): ${t(REMOVAL_CHECK_STATE_KEY[check.state])} (${check.state})`}>
					<p class="font-medium">{check.label}</p>
					<StatusChip status={check.state} />
					<p class="text-ink-2">{t('hypervisors.removal.code')}: <code>{check.code}</code> · {t('hypervisors.removal.state')}: {t(REMOVAL_CHECK_STATE_KEY[check.state])} ({check.state})</p>
					<p class="whitespace-pre-wrap">{check.detail || t('hypervisors.removal.detailMissing')}</p>
				</li>
			{:else}
				<li class="text-ink-2">{t('hypervisors.removal.checksMissing')}</li>
			{/each}
		</ul>
	</section>
{/snippet}

{#snippet serverList(servers: RemovalServer[], label: string)}
	<section aria-label={label} class="space-y-2">
		<h4 class="text-sm font-semibold">{label} · {t('hypervisors.removal.count', { count: servers.length })}</h4>
		<ul class="space-y-3">
			{#each servers as server}
				<li class="space-y-2 border-l border-line pl-3" aria-label={`${server.name || t('hypervisors.removal.unnamed')} (${server.id})`}>
					<dl class="space-y-2">
						{@render metadata(t('hypervisors.removal.name'), server.name || t('hypervisors.removal.unnamed'))}
						{@render metadata(t('hypervisors.removal.serverId'), server.id)}
						{@render metadata(t('hypervisors.removal.projectId'), server.project_id)}
						{@render metadata(t('hypervisors.removal.status'), server.status)}
						{@render metadata(t('hypervisors.removal.createdAt'), server.created_at)}
					</dl>
				</li>
			{:else}
				<li class="text-ink-2">{t('hypervisors.removal.serversEmpty')}</li>
			{/each}
		</ul>
	</section>
{/snippet}

{#snippet allocationValue(value: unknown)}
	{#if value === null}
		<code>null</code>
	{:else if Array.isArray(value)}
		{#if value.length === 0}
			<code>[]</code>
		{:else}
			<ol class="space-y-1 border-l border-line pl-3">
				{#each value as item, index}
					<li><span class="text-ink-2">[{index}]</span> {@render allocationValue(item)}</li>
				{/each}
			</ol>
		{/if}
	{:else if typeof value === 'object'}
		{#if Object.keys(value).length === 0}
			<code>{'{}'}</code>
		{:else}
			<dl class="space-y-2 border-l border-line pl-3">
				{#each Object.entries(value) as [key, item]}
					<div class="min-w-0">
						<dt class="font-mono text-ink-2">{key}</dt>
						<dd class="min-w-0">{@render allocationValue(item)}</dd>
					</div>
				{/each}
			</dl>
		{/if}
	{:else}
		<code class="whitespace-pre-wrap">{JSON.stringify(value) ?? String(value)}</code>
	{/if}
{/snippet}

<section aria-label={t('hypervisors.removal.title')} class="removal-review min-w-0 space-y-4 text-xs text-ink-0" aria-busy={busy}>
	<div class="space-y-3">
		<h3 class="text-sm font-semibold">{t('hypervisors.removal.title')}</h3>
		<Alert tone="warning" title={t('hypervisors.removal.scopeTitle')}>
			{t('hypervisors.removal.scopeWarning')}
		</Alert>
		<Button variant="secondary" size="sm" class="w-full whitespace-normal" ariaLabel={t('hypervisors.removal.refresh')} disabled={busy} onclick={refreshInspection}>{t('hypervisors.removal.refresh')}</Button>
		{#if busy}<p role="status">{t('hypervisors.removal.busy')}</p>{/if}
		{#if invalidReason}<Alert tone="warning">{invalidReason}</Alert>{/if}
		{#if localError}<Alert tone="danger">{t(localError)}</Alert>{/if}
	</div>

	{#if report}
		<Card surface="base" padding="sm" class="min-w-0">
			<section aria-label={t('hypervisors.removal.reportTitle')} class="space-y-4">
				<h4 class="text-sm font-semibold">{t('hypervisors.removal.reportTitle')}</h4>
				<dl class="space-y-2">
					{@render metadata(t('hypervisors.removal.hypervisorId'), report.hypervisor_id)}
					{@render metadata(t('hypervisors.removal.hostname'), report.hostname)}
					{@render metadata(t('hypervisors.removal.checkedAt'), report.checked_at)}
					{@render metadata(t('hypervisors.removal.eligible'), report.eligible)}
					{@render metadata(t('hypervisors.removal.expiresAt'), inspection?.expires_at ?? null)}
				</dl>
				<Alert tone={report.eligible ? 'info' : 'warning'} title={report.eligible ? t('hypervisors.removal.eligibleTitle') : t('hypervisors.removal.ineligibleTitle')}>
					{report.eligible ? t('hypervisors.removal.eligibleHelp') : t('hypervisors.removal.ineligibleHelp')}
				</Alert>
				{@render checkList(report.checks, t('hypervisors.removal.conditions'))}
			</section>
		</Card>

		<Card surface="base" padding="sm" class="min-w-0">
			<section aria-label={t('hypervisors.removal.serviceTitle')} class="space-y-3">
				<h4 class="text-sm font-semibold">{t('hypervisors.removal.serviceTitle')}</h4>
				<div class="flex min-w-0 flex-wrap gap-2"><StatusChip status={report.service.status} /><StatusChip status={report.service.state} /></div>
				<dl class="space-y-2">
					{@render metadata(t('hypervisors.removal.serviceUuid'), report.service.id)}
					{@render metadata(t('hypervisors.removal.serviceHost'), report.service.host)}
					{@render metadata(t('hypervisors.removal.binary'), report.service.binary)}
					{@render metadata(t('hypervisors.removal.schedulingStatus'), report.service.status)}
					{@render metadata(t('hypervisors.removal.serviceState'), report.service.state)}
					{@render metadata(t('hypervisors.removal.forcedDown'), report.service.forced_down)}
					{@render metadata(t('hypervisors.removal.disabledReason'), report.service.disabled_reason)}
					{@render metadata(t('hypervisors.removal.zone'), report.service.zone)}
					{@render metadata(t('hypervisors.removal.serviceUpdatedAt'), report.service.updated_at)}
				</dl>
				<p class="text-ink-2">{t('hypervisors.removal.heartbeatWarning')}</p>
				<section aria-label={t('hypervisors.removal.uptimeTitle')} class="space-y-2">
					<h5 class="font-semibold">{report.uptime.source === 'last_observed' ? t('hypervisors.removal.lastObservedUptime') : report.uptime.status === 'available' ? t('hypervisors.removal.currentUptime') : t('hypervisors.removal.uptimeUnavailable')}</h5>
					<dl class="space-y-2">
						{@render metadata(t('hypervisors.removal.uptimeStatus'), report.uptime.status)}
						{@render metadata(t('hypervisors.removal.source'), report.uptime.source ?? (report.uptime.status === 'available' ? 'live' : 'unavailable'))}
						{@render metadata(t('hypervisors.removal.uptimeValue'), report.uptime.value)}
						{@render metadata(t('hypervisors.removal.hostTime'), report.uptime.host_time)}
						{@render metadata(t('hypervisors.removal.observedAt'), report.uptime.observed_at ?? null)}
					</dl>
					{#if report.uptime.source === 'last_observed'}
						<Alert tone="warning" title={t('hypervisors.removal.storedObservationTitle')}>{t('hypervisors.removal.storedObservationWarning')}</Alert>
					{:else}
						<p class="text-ink-2">{report.uptime.status === 'unavailable' ? t('hypervisors.removal.noUptimeHelp') : t('hypervisors.removal.liveUptimeHelp')}</p>
					{/if}
				</section>
			</section>
		</Card>

		<Card surface="base" padding="sm" class="min-w-0">
			<section aria-label={t('hypervisors.removal.currentServersTitle')} class="space-y-3">
				<p class="text-ink-2">{t('hypervisors.removal.currentServersHelp')}</p>
				{@render serverList(report.servers, t('hypervisors.removal.currentServers'))}
			</section>
		</Card>

		<Card surface="base" padding="sm" class="min-w-0">
			<section aria-label={t('hypervisors.removal.historyTitle')} class="space-y-4">
				<h4 class="text-sm font-semibold">{t('hypervisors.removal.historyTitle')}</h4>
				<Alert tone="warning" title={t('hypervisors.removal.historyWarningTitle')}>
					{t('hypervisors.removal.historyWarning')}
				</Alert>
				<p class="whitespace-pre-wrap"><span class="text-ink-2">{t('hypervisors.removal.historyNote')}: </span>{report.history.note || t('hypervisors.removal.noteMissing')}</p>
				{@render serverList(report.history.deleted_servers, t('hypervisors.removal.deletedServers'))}
				<section aria-label={t('hypervisors.removal.migrations')} class="space-y-2">
					<h5 class="text-sm font-semibold">{t('hypervisors.removal.migrations')} · {t('hypervisors.removal.count', { count: report.history.migrations.length })}</h5>
					<ul class="space-y-3">
						{#each report.history.migrations as migration}
							<li class="border-l border-line pl-3" aria-label={t('hypervisors.removal.migrationLabel', { id: migration.uuid || migration.id })}>
								<dl class="space-y-2">
									{@render metadata(t('hypervisors.removal.migrationId'), migration.id)}
									{@render metadata(t('hypervisors.removal.migrationUuid'), migration.uuid || t('hypervisors.removal.migrationUuidMissing'))}
									{@render metadata(t('hypervisors.removal.instanceUuid'), migration.instance_uuid)}
									{@render metadata(t('hypervisors.removal.sourceCompute'), migration.source_compute)}
									{@render metadata(t('hypervisors.removal.destCompute'), migration.dest_compute)}
									{@render metadata(t('hypervisors.removal.status'), migration.status)}
									{@render metadata(t('hypervisors.removal.migrationType'), migration.migration_type)}
									{@render metadata(t('hypervisors.removal.createdAt'), migration.created_at)}
									{@render metadata(t('hypervisors.removal.updatedAt'), migration.updated_at)}
								</dl>
							</li>
						{:else}
							<li class="text-ink-2">{t('hypervisors.removal.migrationsEmpty')}</li>
						{/each}
					</ul>
				</section>
			</section>
		</Card>

		<Card surface="base" padding="sm" class="min-w-0">
			<section aria-label={t('hypervisors.removal.placementTitle')} class="space-y-3">
				<h4 class="text-sm font-semibold">{t('hypervisors.removal.placementTitle')} · {t('hypervisors.removal.count', { count: report.placement.providers.length })}</h4>
				<p class="text-ink-2">{t('hypervisors.removal.placementHelp')}</p>
				<ul class="space-y-4">
					{#each report.placement.providers as provider}
						<li class="space-y-3 border-l border-line pl-3" aria-label={t('hypervisors.removal.providerLabel', { uuid: provider.uuid })}>
							<dl class="space-y-2">
								{@render metadata(t('hypervisors.removal.providerUuid'), provider.uuid)}
								{@render metadata(t('hypervisors.removal.providerName'), provider.name)}
								{@render metadata(t('hypervisors.removal.parentProviderUuid'), provider.parent_provider_uuid ?? t('hypervisors.removal.rootProvider'))}
								{@render metadata(t('hypervisors.removal.generation'), provider.generation)}
							</dl>
							<div role="region" aria-label={t('hypervisors.removal.allocationsLabel', { uuid: provider.uuid })} class="min-w-0 space-y-3">
								{#each Object.entries(provider.allocations) as [consumer, allocation]}
									<div class="min-w-0 space-y-2">
										<p class="font-medium">{t('hypervisors.removal.consumerUuid')}: <code>{consumer}</code></p>
										{@render allocationValue(allocation)}
									</div>
								{:else}
									<p class="text-ink-2">{t('hypervisors.removal.allocationsEmpty')}</p>
								{/each}
							</div>
						</li>
					{:else}
						<li class="text-ink-2">{t('hypervisors.removal.providersEmpty')}</li>
					{/each}
				</ul>
			</section>
		</Card>

		<Card surface="base" padding="sm" class="min-w-0">
			<form aria-label={t('hypervisors.removal.approvalTitle')} onsubmit={submitApproval} class="space-y-4">
				<h4 class="text-sm font-semibold">{t('hypervisors.removal.approvalTitle')}</h4>
				<p class="text-ink-2">{t('hypervisors.removal.approvalHelp')}</p>
				{#if inspection?.review_token === consumedToken && consumedToken}
					<Alert tone="warning">{t('hypervisors.removal.approvalConsumed')}</Alert>
				{:else if !hasValidRemovalReview(inspection, clock)}
					<Alert tone="warning">{t('hypervisors.removal.approvalUnavailable')}</Alert>
				{:else if inspection === invalidatedInspection}
					<Alert tone="warning">{t('hypervisors.removal.approvalInvalidated')}</Alert>
				{/if}
				<label class="flex items-start gap-2">
					<input type="checkbox" required bind:checked={reviewedMetadata} disabled={busy || !usableReview} />
					<span>{t('hypervisors.removal.reviewedMetadata')}</span>
				</label>
				<label class="flex items-start gap-2">
					<input type="checkbox" required bind:checked={computeStopped} disabled={busy || !usableReview} />
					<span>{t('hypervisors.removal.computeStopped')}</span>
				</label>
				<Field label={t('hypervisors.removal.exactHostname')} for={hostnameId} required help={t('hypervisors.removal.hostnameHelp', { hostname: report.hostname })} error={hostnameError} class="min-w-0">
					<TextInput id={hostnameId} required bind:value={confirmHostname} disabled={busy || !usableReview} ariaInvalid={!!hostnameError} />
				</Field>
				<Field label={t('hypervisors.removal.reason')} for={reasonId} required help={t('hypervisors.removal.reasonHelp')} error={reasonError}>
					<TextareaInput id={reasonId} rows={3} required bind:value={reason} disabled={busy || !usableReview} ariaInvalid={!!reasonError} />
				</Field>
				<Button type="submit" variant="danger" size="sm" class="w-full whitespace-normal" ariaLabel={t('hypervisors.removal.remove')} disabled={!canSubmit}>{t('hypervisors.removal.remove')}</Button>
			</form>
		</Card>
	{:else}
		<p class="text-ink-2">{t('hypervisors.removal.noReport')}</p>
	{/if}

	{#if result}
		<Card surface="base" padding="sm" class="min-w-0">
			<section aria-label={t('hypervisors.removal.resultTitle')} class="space-y-3">
				<h4 class="text-sm font-semibold">{t('hypervisors.removal.resultTitle')}</h4>
				<Alert tone={isVerifiedRemoval(result) ? 'success' : 'warning'} title={isVerifiedRemoval(result) ? t('hypervisors.removal.verifiedTitle') : t('hypervisors.removal.unverifiedTitle')}>
					{isVerifiedRemoval(result) ? t('hypervisors.removal.verifiedHelp') : t('hypervisors.removal.unverifiedHelp')}
				</Alert>
				<dl class="space-y-2">
					{@render metadata(t('hypervisors.removal.resultStatus'), result.status)}
					{@render metadata(t('hypervisors.removal.verified'), result.verified)}
					{@render metadata(t('hypervisors.removal.hypervisorId'), result.hypervisor_id)}
					{@render metadata(t('hypervisors.removal.hostname'), result.hostname)}
					{@render metadata(t('hypervisors.removal.resultServiceUuid'), result.service_id)}
					{@render metadata(t('hypervisors.removal.resultDetail'), result.detail)}
				</dl>
				{@render checkList(result.checks, t('hypervisors.removal.verificationChecks'))}
			</section>
		</Card>
	{/if}
</section>

<style>
	.removal-review {
		overflow-wrap: anywhere;
	}
	input[type='checkbox'] {
		flex-shrink: 0;
		margin-top: 0.125rem;
		accent-color: var(--color-state-danger);
	}
	input[type='checkbox']:focus-visible {
		outline: 2px solid var(--color-line-2);
		outline-offset: 2px;
	}
</style>
