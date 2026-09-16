<script lang="ts">
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { useAdminVolumeDetailController } from '$lib/stores/adminVolumeDetailController.svelte';

	const s = useAdminVolumeDetailController();

	const confidenceLabel: Record<string, string> = {
		high: '높음',
		medium: '중간',
		low: '낮음',
	};

	const resultClass: Record<string, string> = {
		deleted: 'diagnostic-result-success',
		already_deleted: 'diagnostic-result-success',
		delete_submitted: 'diagnostic-result-warning',
		backend_residue: 'diagnostic-result-danger',
		backend_unverified: 'diagnostic-result-warning',
		blocked: 'diagnostic-result-warning',
		failed: 'diagnostic-result-danger',
	};

	const resultLabel: Record<string, string> = {
		deleted: '삭제 검증 완료',
		already_deleted: '이미 삭제됨',
		delete_submitted: '삭제 요청 제출됨',
		backend_residue: 'Ceph backend 잔여물 확인됨',
		backend_unverified: 'Ceph backend 검증 불가',
		blocked: '자동 복구 차단',
		failed: '자동 복구 실패',
	};

	async function runRecovery() {
		const diagnostic = s.deleteDiagnostic;
		const volume = s.volume;
		if (!diagnostic || !volume) return;
		const backendConfirmation = diagnostic.backend.mode === 'inspected'
			? '\n\nCeph RBD metadata를 검사했으며 삭제 후 backend 부재까지 확인합니다.'
			: '\n\nCeph RBD 검증이 설정되지 않았거나 불가능하면 성공으로 처리하지 않습니다.';
		const confirmed = await confirmDialog(
			`볼륨 "${volume.name || volume.id}" 삭제 복구를 실행하시겠습니까?\n\n진단: ${diagnostic.summary}\n\n스냅샷/백업 종속성은 자동 삭제하지 않습니다. 남아 있으면 복구가 차단됩니다.${backendConfirmation}`
		);
		if (!confirmed) return;
		await s.recoverDelete();
	}
</script>

<div class="diagnostic-card rounded-xl p-4 space-y-4">
	<div class="flex items-start justify-between gap-3">
		<div>
			<h3 class="diagnostic-kicker text-xs uppercase tracking-wide">삭제 진단 및 자동 복구</h3>
			<p class="diagnostic-muted text-xs mt-1">Cinder 상태·종속성, Nova 연결, Ceph RBD metadata를 독립적으로 확인합니다.</p>
		</div>
		<button
			type="button"
			class="diagnostic-secondary-action px-3 py-1.5 rounded text-xs disabled:opacity-50"
			disabled={s.diagnosticLoading}
			onclick={() => s.fetchDeleteDiagnostic({ refresh: true })}
		>
			{s.diagnosticLoading ? '진단 중...' : '진단 다시 실행'}
		</button>
	</div>

	{#if s.diagnosticError}
		<div class="diagnostic-error rounded border px-3 py-2 text-xs">{s.diagnosticError}</div>
	{/if}

	{#if s.diagnosticLoading && !s.deleteDiagnostic}
		<div class="diagnostic-muted text-sm">삭제 진단을 불러오는 중...</div>
	{/if}

	{#if s.deleteDiagnostic}
		<div class="space-y-3 text-sm">
			<div class="grid grid-cols-1 md:grid-cols-3 gap-2 text-xs">
				<div class="diagnostic-stat rounded border p-3">
					<div class="diagnostic-muted">원인 코드</div>
					<div class="diagnostic-primary font-mono mt-1">{s.deleteDiagnostic.root_cause_code}</div>
				</div>
				<div class="diagnostic-stat rounded border p-3">
					<div class="diagnostic-muted">신뢰도</div>
					<div class="diagnostic-primary mt-1">{confidenceLabel[s.deleteDiagnostic.confidence] ?? s.deleteDiagnostic.confidence}</div>
				</div>
				<div class="diagnostic-stat rounded border p-3">
					<div class="diagnostic-muted">자동 복구</div>
					<div class={s.deleteDiagnostic.recovery_available ? 'diagnostic-success mt-1' : 'diagnostic-warning mt-1'}>
						{s.deleteDiagnostic.recovery_available ? '가능' : '차단/비대상'}
					</div>
				</div>
			</div>

			<div class="diagnostic-stat rounded border p-3 space-y-2">
				<p class="diagnostic-primary">{s.deleteDiagnostic.summary}</p>
				<p class="diagnostic-muted text-xs">권장 조치: {s.deleteDiagnostic.recommended_action}</p>
			</div>

			{#if s.deleteDiagnostic.checks.length > 0}
				<div>
					<div class="diagnostic-muted text-xs mb-1">안전 점검</div>
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
				<div class="diagnostic-muted">Ceph backend</div>
				<div class="diagnostic-primary font-mono break-all">
					{s.deleteDiagnostic.backend.mode} / {s.deleteDiagnostic.backend.classification}
				</div>
				{#if s.deleteDiagnostic.backend.pool || s.deleteDiagnostic.backend.image_name || s.deleteDiagnostic.backend.image_id}
					<div class="diagnostic-muted font-mono break-all">
						pool={s.deleteDiagnostic.backend.pool || 'unknown'}, image={s.deleteDiagnostic.backend.image_name || 'unknown'}, id={s.deleteDiagnostic.backend.image_id || 'unknown'}
					</div>
				{/if}
			</div>

			{#if s.deleteDiagnostic.evidence.length > 0}
				<div>
					<div class="diagnostic-muted text-xs mb-1">근거</div>
					<ul class="diagnostic-primary space-y-1 text-xs">
						{#each s.deleteDiagnostic.evidence as evidence}
							<li class="font-mono break-all">• {evidence}</li>
						{/each}
					</ul>
				</div>
			{/if}

			{#if s.deleteDiagnostic.dependencies.length > 0}
				<div>
					<div class="diagnostic-muted text-xs mb-1">종속 리소스</div>
					<ul class="diagnostic-warning space-y-1 text-xs">
						{#each s.deleteDiagnostic.dependencies as dep}
							<li>{dep.kind} {dep.name || dep.id} — {dep.status || 'unknown'}</li>
						{/each}
					</ul>
				</div>
			{/if}

			{#if s.deleteDiagnostic.messages.length > 0}
				<div>
					<div class="diagnostic-muted text-xs mb-1">Cinder messages</div>
					<ul class="diagnostic-primary space-y-1 text-xs">
						{#each s.deleteDiagnostic.messages as message}
							<li>
								<span>{message.user_message || message.event_id || 'message'}</span>
								{#if message.request_id}<span class="diagnostic-muted"> · {message.request_id}</span>{/if}
							</li>
						{/each}
					</ul>
				</div>
			{/if}

			{#if s.deleteDiagnostic.recovery_available}
				<button
					type="button"
					class="diagnostic-danger-action w-full px-4 py-2 rounded text-sm font-medium disabled:opacity-50"
					disabled={s.recovering}
					onclick={runRecovery}
				>
					{s.recovering ? '복구 중...' : '자동 복구 실행'}
				</button>
			{/if}
		</div>
	{/if}

	{#if s.recoveryResult}
		<div class="diagnostic-result rounded border px-3 py-3 text-sm space-y-2 {resultClass[s.recoveryResult.status] ?? 'diagnostic-result-neutral'}">
			<div class="font-medium">{resultLabel[s.recoveryResult.status] ?? s.recoveryResult.status}</div>
			{#if s.recoveryResult.status === 'delete_submitted'}
				<p class="text-xs">삭제 요청은 제출됐지만 제한 시간 안에 삭제 검증이 끝나지 않았습니다. verified_deleted=false, final_status={s.recoveryResult.final_status || 'unknown'}</p>
			{:else if s.recoveryResult.status === 'backend_residue'}
				<p class="text-xs">Cinder 레코드는 사라졌지만 Ceph RBD metadata 또는 data object가 남아 있습니다. 운영자 확인이 필요합니다.</p>
			{:else if s.recoveryResult.status === 'backend_unverified'}
				<p class="text-xs">Cinder 삭제 이후 Ceph backend 부재를 증명하지 못했습니다. 자동 성공으로 처리하지 않습니다.</p>
			{:else if s.recoveryResult.status === 'blocked'}
				<p class="text-xs">{s.recoveryResult.diagnostic.recommended_action}</p>
			{:else if s.recoveryResult.status === 'failed'}
				<p class="text-xs">실패한 단계의 detail을 확인하세요.</p>
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

	.diagnostic-kicker,
	.diagnostic-muted {
		color: var(--color-ink-2);
	}

	.diagnostic-primary {
		color: var(--color-ink-1);
	}

	.diagnostic-success {
		color: var(--color-state-success);
	}

	.diagnostic-warning {
		color: var(--color-state-warning);
	}

	.diagnostic-error,
	.diagnostic-result-danger {
		border-color: color-mix(in oklab, var(--color-state-danger) 32%, transparent);
		background: color-mix(in oklab, var(--color-state-danger) 12%, transparent);
		color: var(--color-state-danger);
	}

	.diagnostic-secondary-action {
		background: var(--color-surface-sunken);
		color: var(--color-ink-1);
	}

	.diagnostic-secondary-action:hover:not(:disabled) {
		background: color-mix(in oklab, var(--color-surface-sunken) 78%, var(--color-ink-0));
		color: var(--color-ink-0);
	}

	.diagnostic-danger-action {
		background: var(--color-state-danger);
		color: var(--color-action-on-accent);
	}

	.diagnostic-danger-action:hover:not(:disabled) {
		background: color-mix(in oklab, var(--color-state-danger) 88%, var(--color-ink-0));
	}

	.diagnostic-result {
		border-color: var(--diagnostic-result-tone, var(--color-line));
		background: color-mix(in oklab, var(--diagnostic-result-tone, var(--color-surface-sunken)) 12%, transparent);
		color: var(--diagnostic-result-tone, var(--color-ink-1));
	}

	.diagnostic-result-success {
		--diagnostic-result-tone: var(--color-state-success);
	}

	.diagnostic-result-warning {
		--diagnostic-result-tone: var(--color-state-warning);
	}

	.diagnostic-result-danger {
		--diagnostic-result-tone: var(--color-state-danger);
	}
</style>
