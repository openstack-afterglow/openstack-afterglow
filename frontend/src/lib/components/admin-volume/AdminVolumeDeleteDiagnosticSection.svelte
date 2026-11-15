<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-storage';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { useAdminVolumeDetailController } from '$lib/stores/adminVolumeDetailController.svelte';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import type { VolumeDeleteRecoveryMode } from '$lib/types/volume';

	const s = useAdminVolumeDetailController();
	let confirming = $state(false);
	const busy = $derived(confirming || s.recovering || s.diagnosticLoading);
	const allowed = $derived(!!s.deleteDiagnostic?.recovery_available && !s.diagnosticError
		&& s.deleteDiagnostic.root_cause_code !== 'creation_active_watcher');
	const canReset = $derived(allowed && (s.deleteDiagnostic?.root_cause_code === 'creation_stalled' || s.deleteDiagnostic?.status === 'error'));
	const creationStatus = $derived(s.deleteDiagnostic?.status === 'creating' || s.deleteDiagnostic?.status === 'downloading');

	const confidenceLabel = $derived<Record<string, string>>({
		high: t('diagnostic.confidenceHigh'),
		medium: t('diagnostic.confidenceMedium'),
		low: t('diagnostic.confidenceLow'),
	});

	const resultClass: Record<string, string> = {
		deleted: 'diagnostic-result-success',
		state_reset: 'diagnostic-result-success',
		already_deleted: 'diagnostic-result-success',
		delete_submitted: 'diagnostic-result-warning',
		backend_residue: 'diagnostic-result-danger',
		backend_unverified: 'diagnostic-result-warning',
		blocked: 'diagnostic-result-warning',
		failed: 'diagnostic-result-danger',
	};

	const resultLabel = $derived<Record<string, string>>({
		deleted: t('diagnostic.resultDeleted'),
		state_reset: t('diagnostic.resultStateReset'),
		already_deleted: t('diagnostic.resultAlreadyDeleted'),
		delete_submitted: t('diagnostic.resultSubmitted'),
		backend_residue: t('diagnostic.resultResidue'),
		backend_unverified: t('diagnostic.resultUnverified'),
		blocked: t('diagnostic.resultBlocked'),
		failed: t('diagnostic.resultFailed'),
	});

	async function runRecovery(mode: VolumeDeleteRecoveryMode) {
		const diagnostic = s.deleteDiagnostic;
		const volume = s.volume;
		if (busy || !allowed || !diagnostic?.status || !volume || (mode === 'recover' && !canReset)) return;
		confirming = true;
		try {
			const confirmed = await confirmDialog(t(mode === 'recover' ? 'diagnostic.resetConfirm' : 'diagnostic.forceDeleteConfirm', {
				name: volume.name || volume.id,
				id: volume.id,
				status: diagnostic.status,
				summary: diagnostic.summary,
			}), {
				confirmLabel: t(mode === 'recover' ? 'diagnostic.resetState' : 'diagnostic.forceDelete'),
				confirmVariant: 'danger',
			});
			if (!confirmed) return;
			await s.recoverDelete(mode, diagnostic);
		} finally {
			confirming = false;
		}
	}
</script>

<div class="diagnostic-card rounded-xl p-4 space-y-4">
	<div class="flex flex-wrap items-start justify-between gap-3">
		<div class="min-w-0">
			<h3 class="text-sm font-semibold text-ink-0"><span aria-hidden="true">1. </span>{t('diagnostic.title')}</h3>
			<p class="diagnostic-muted text-xs mt-1">{t('diagnostic.description')}</p>
		</div>
		<Button variant="outline" disabled={busy} onclick={() => s.fetchDeleteDiagnostic({ refresh: true })}>
			{#if s.diagnosticLoading}<LoadingState variant="control" label="" />{/if}{s.diagnosticLoading ? t('diagnostic.running') : t('diagnostic.runAgain')}
		</Button>
	</div>

	{#if s.diagnosticError}
		<div class="diagnostic-error rounded border px-3 py-2 text-xs">{s.diagnosticError}</div>
	{/if}

	{#if s.diagnosticLoading && !s.deleteDiagnostic}
		<LoadingState variant="section" label={t('diagnostic.loading')} />
	{/if}

	{#if s.deleteDiagnostic}
		<div class="space-y-3 text-sm">
			<div class="grid grid-cols-1 md:grid-cols-3 gap-2 text-xs">
				<div class="diagnostic-stat rounded border p-3">
					<div class="diagnostic-muted">{t('diagnostic.causeCode')}</div>
					<div class="diagnostic-primary font-mono mt-1 break-all">{s.deleteDiagnostic.root_cause_code}</div>
				</div>
				<div class="diagnostic-stat rounded border p-3">
					<div class="diagnostic-muted">{t('diagnostic.confidence')}</div>
					<div class="diagnostic-primary mt-1">{confidenceLabel[s.deleteDiagnostic.confidence] ?? s.deleteDiagnostic.confidence}</div>
				</div>
				<div class="diagnostic-stat rounded border p-3">
					<div class="diagnostic-muted">{t('diagnostic.recovery')}</div>
					<div class={s.deleteDiagnostic.recovery_available ? 'diagnostic-success mt-1' : 'diagnostic-warning mt-1'}>
						{s.deleteDiagnostic.recovery_available ? t('diagnostic.available') : t('diagnostic.blocked')}
					</div>
				</div>
			</div>

			<div class="diagnostic-stat rounded border p-3 space-y-2">
				<p class="diagnostic-primary">{s.deleteDiagnostic.summary}</p>
				<p class="diagnostic-muted text-xs">{t('diagnostic.recommendedAction', { action: s.deleteDiagnostic.recommended_action })}</p>
			</div>

			{#if creationStatus}
				<p class="text-xs text-ink-2">{t('diagnostic.creationAge', {
					age: s.deleteDiagnostic.creation_age_seconds == null ? t('diagnostic.unknown') : new Intl.NumberFormat(intlLocale(), { maximumFractionDigits: 0 }).format(s.deleteDiagnostic.creation_age_seconds),
				})}</p>
				<p class="text-xs text-ink-2">{t('diagnostic.creationThreshold')}</p>
			{/if}
			{#if s.deleteDiagnostic.root_cause_code === 'creation_in_progress'}
				<Alert tone="info">{t('diagnostic.creationInProgress')}</Alert>
			{:else if s.deleteDiagnostic.root_cause_code === 'creation_stalled'}
				<Alert tone="warning">{t('diagnostic.creationStalled')}</Alert>
			{:else if s.deleteDiagnostic.root_cause_code === 'creation_active_watcher'}
				<Alert tone="warning">{t('diagnostic.creationActiveWatcher')}</Alert>
			{:else if s.deleteDiagnostic.root_cause_code === 'backend_lookup_unknown'}
				<Alert tone="warning">{t('diagnostic.backendUnknown')}</Alert>
			{/if}
			{#if s.deleteDiagnostic.owner_service_hint}
				<Alert tone="warning">{t('diagnostic.ownerWarning', { service: s.deleteDiagnostic.owner_service_hint === 'afterglow' ? 'Afterglow' : 'Palimpsest' })}</Alert>
			{/if}
			{#if s.deleteDiagnostic.backend.mode === 'unavailable'}
				<Alert tone="warning">{t('diagnostic.backendUnconfigured')}</Alert>
			{/if}

			{#if s.deleteDiagnostic.checks.length > 0}
				<div>
					<div class="diagnostic-muted text-xs mb-1">{t('diagnostic.safetyChecks')}</div>
					<ul class="diagnostic-primary space-y-1 text-xs">
						{#each s.deleteDiagnostic.checks as check}
							<li class="font-mono break-all">
								{check.name}: {check.state}{check.detail ? ` — ${check.detail}` : ''}
							</li>
						{/each}
					</ul>
				</div>
			{/if}

			<div class="diagnostic-stat rounded border p-3 space-y-1 text-xs">
				<div class="diagnostic-muted">{t('diagnostic.backend')}</div>
				<div class="diagnostic-primary font-mono break-all">
					{s.deleteDiagnostic.backend.mode} / {s.deleteDiagnostic.backend.classification}
				</div>
				{#if s.deleteDiagnostic.backend.pool || s.deleteDiagnostic.backend.image_name || s.deleteDiagnostic.backend.image_id}
					<div class="diagnostic-muted font-mono break-all">
						pool={s.deleteDiagnostic.backend.pool || t('diagnostic.unknown')}, image={s.deleteDiagnostic.backend.image_name || t('diagnostic.unknown')}, id={s.deleteDiagnostic.backend.image_id || t('diagnostic.unknown')}
					</div>
				{/if}
			</div>

			{#if s.deleteDiagnostic.evidence.length > 0}
				<div>
					<div class="diagnostic-muted text-xs mb-1">{t('diagnostic.evidence')}</div>
					<ul class="diagnostic-primary space-y-1 text-xs">
						{#each s.deleteDiagnostic.evidence as evidence}
							<li class="font-mono break-all">• {evidence}</li>
						{/each}
					</ul>
				</div>
			{/if}

			{#if s.deleteDiagnostic.dependencies.length > 0}
				<div>
					<div class="diagnostic-muted text-xs mb-1">{t('diagnostic.dependencies')}</div>
					<ul class="diagnostic-warning space-y-1 text-xs">
						{#each s.deleteDiagnostic.dependencies as dep}
							<li>{dep.kind} {dep.name || dep.id} — {dep.status || t('diagnostic.unknown')}</li>
						{/each}
					</ul>
				</div>
			{/if}

			{#if s.deleteDiagnostic.messages.length > 0}
				<div>
					<div class="diagnostic-muted text-xs mb-1">{t('diagnostic.cinderMessages')}</div>
					<ul class="diagnostic-primary space-y-1 text-xs">
						{#each s.deleteDiagnostic.messages as message}
							<li>
								<span>{message.user_message || message.event_id || t('diagnostic.message')}</span>
								{#if message.request_id}<span class="diagnostic-muted"> · {message.request_id}</span>{/if}
							</li>
						{/each}
					</ul>
				</div>
			{/if}

			<div class="space-y-3">
				<div class="space-y-1">
					<h4 class="text-xs font-semibold text-ink-0"><span aria-hidden="true">2. </span>{t('diagnostic.resetState')}</h4>
					<Button variant="outline" disabled={busy || !canReset} onclick={() => runRecovery('recover')}>{s.recovering ? t('diagnostic.recovering') : t('diagnostic.resetState')}</Button>
					<p class="text-xs text-ink-2">{t('diagnostic.resetHelp')}</p>
				</div>
				<div class="space-y-1">
					<h4 class="text-xs font-semibold text-ink-0"><span aria-hidden="true">3. </span>{t('diagnostic.forceDelete')}</h4>
					<Button variant="danger" disabled={busy || !allowed} onclick={() => runRecovery('force_delete')}>{s.recovering ? t('diagnostic.recovering') : t('diagnostic.forceDelete')}</Button>
					<p class="text-xs text-ink-2">{t('diagnostic.forceDeleteHelp')}</p>
				</div>
				{#if !allowed}<p class="text-xs text-state-warning-text">{t('diagnostic.actionBlocked')}</p>{/if}
			</div>
		</div>
	{/if}

	{#if s.recoveryResult}
		<div class="diagnostic-result rounded border px-3 py-3 text-sm space-y-2 {resultClass[s.recoveryResult.status] ?? 'diagnostic-result-neutral'}">
			<div class="font-medium">{resultLabel[s.recoveryResult.status] ?? s.recoveryResult.status}</div>
			{#if s.recoveryResult.steps.some(step => step.detail?.startsWith('creation_delete_state_changed:'))}
				<Alert tone="danger">{t('diagnostic.creationDeleteStateChanged', { status: s.recoveryResult.final_status || t('diagnostic.unknown') })}</Alert>
			{/if}
			{#if s.recoveryResult.status === 'state_reset'}
				<p class="text-xs">{t('diagnostic.stateResetNotice', { previous: s.recoveryResult.previous_status || t('diagnostic.unknown'), status: s.recoveryResult.final_status || t('diagnostic.unknown') })}</p>
			{:else if s.recoveryResult.status === 'delete_submitted'}
				<p class="text-xs">{t('diagnostic.submittedNotice', { status: s.recoveryResult.final_status || t('diagnostic.unknown') })}</p>
			{:else if s.recoveryResult.status === 'backend_residue'}
				<p class="text-xs">{t('diagnostic.residueNotice')}</p>
			{:else if s.recoveryResult.status === 'backend_unverified'}
				<p class="text-xs">{t('diagnostic.unverifiedNotice')}</p>
			{:else if s.recoveryResult.status === 'blocked'}
				<p class="text-xs">{s.recoveryResult.diagnostic.recommended_action}</p>
			{:else if s.recoveryResult.status === 'failed'}
				<p class="text-xs">{t('diagnostic.failedNotice')}</p>
			{:else}
				<p class="text-xs">verified_deleted={String(s.recoveryResult.verified_deleted)}</p>
			{/if}

			<p class="text-xs font-mono">backend_verification={s.recoveryResult.backend_verification}</p>
			<p class="text-xs font-mono">quota_verification={s.recoveryResult.quota_verification}</p>

			{#if s.recoveryResult.steps.length > 0}
				<ol class="space-y-1 text-xs">
					{#each s.recoveryResult.steps as step}
						<li class="font-mono break-all">{step.action}: {step.status}{step.detail ? ` — ${step.detail}` : ''}</li>
					{/each}
				</ol>
			{/if}
		</div>
	{/if}
</div>

<style>
	.diagnostic-card {
		border: 1px solid var(--color-line);
		background: var(--color-surface-raised);
	}

	.diagnostic-stat {
		border-color: var(--color-line);
		background: color-mix(in oklab, var(--color-surface-sunken) 55%, transparent);
	}

	.diagnostic-muted {
		color: var(--color-ink-2);
	}

	.diagnostic-primary {
		color: var(--color-ink-1);
	}

	.diagnostic-success {
		color: var(--color-state-success-text);
	}

	.diagnostic-warning {
		color: var(--color-state-warning-text);
	}

	.diagnostic-error,
	.diagnostic-result-danger {
		border-color: color-mix(in oklab, var(--color-state-danger) 32%, transparent);
		background: color-mix(in oklab, var(--color-state-danger) 12%, transparent);
		color: var(--color-state-danger-text);
	}


	.diagnostic-result {
		border-color: var(--diagnostic-result-tone, var(--color-line));
		background: color-mix(in oklab, var(--diagnostic-result-tone, var(--color-surface-sunken)) 12%, transparent);
		color: var(--diagnostic-result-tone, var(--color-ink-1));
	}

	.diagnostic-result-success {
		--diagnostic-result-tone: var(--color-state-success-text);
	}

	.diagnostic-result-warning {
		--diagnostic-result-tone: var(--color-state-warning-text);
	}

	.diagnostic-result-danger {
		--diagnostic-result-tone: var(--color-state-danger-text);
	}
</style>
