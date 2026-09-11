<script lang="ts">
	import { auth } from '$lib/stores/auth';
	import { api } from '$lib/api/client';
	import type { RecoveryAnalysis, RecoveryResult } from '$lib/types/adminInstance';

	interface Props {
		serverId: string;
		serverName: string;
		onClose: () => void;
		onRecovered?: () => void;
	}

	let { serverId, serverName, onClose, onRecovered }: Props = $props();

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	type Phase = 'loading' | 'analyzed' | 'executing' | 'done' | 'error';
	let phase = $state<Phase>('loading');
	let analysis = $state<RecoveryAnalysis | null>(null);
	let result = $state<RecoveryResult | null>(null);
	let errorMsg = $state('');
	let confirmed = $state(false);

	const scenarioLabels: Record<string, string> = {
		migration_failed_volume_stuck: '마이그레이션 실패 + 볼륨 고착',
		volume_stuck: '볼륨 고착',
		generic_error: '일반 ERROR',
		manual_review: '수동 점검 필요',
	};

	async function load() {
		phase = 'loading';
		try {
			analysis = await api.get<RecoveryAnalysis>(
				`/api/v1/admin/instances/${serverId}/recovery-analysis`,
				token,
				projectId
			);
			phase = 'analyzed';
		} catch (e: unknown) {
			errorMsg = e instanceof Error ? e.message : '복구 분석 중 오류가 발생했습니다';
			phase = 'error';
		}
	}

	async function execute() {
		if (!confirmed || !analysis?.auto_executable) return;
		phase = 'executing';
		try {
			result = await api.post<RecoveryResult>(
				`/api/v1/admin/instances/${serverId}/recover`,
				{},
				token,
				projectId
			);
			phase = 'done';
			if (result?.executed && onRecovered) onRecovered();
		} catch (e: unknown) {
			errorMsg = e instanceof Error ? e.message : '복구 실행 중 오류가 발생했습니다';
			phase = 'error';
		}
	}

	$effect(() => { load(); });
</script>

<!-- 모달 오버레이 -->
<div
	class="fixed inset-0 z-50 flex items-center justify-center bg-surface-scrim/60 backdrop-blur-sm p-4"
	role="dialog"
	aria-modal="true"
	aria-label="인스턴스 복구"
>
	<div class="bg-surface-base border border-line-2 rounded-xl w-full max-w-2xl max-h-[90vh] overflow-y-auto shadow-[var(--shadow-restraint)]">
		<!-- 헤더 -->
		<div class="flex items-center justify-between px-6 py-4 border-b border-line">
			<div>
				<h2 class="text-ink-0 font-semibold text-base">인스턴스 복구 분석</h2>
				<p class="text-ink-2 text-xs mt-0.5 font-mono">{serverName} · {serverId.slice(0, 8)}</p>
			</div>
			<button onclick={onClose} class="text-ink-3 hover:text-ink-2 transition-colors text-lg leading-none">✕</button>
		</div>

		<div class="px-6 py-5 space-y-5">

			<!-- 로딩 -->
			{#if phase === 'loading'}
				<div class="flex items-center gap-3 text-ink-2 text-sm py-8 justify-center">
					<svg class="animate-spin w-5 h-5 text-action-warm" fill="none" viewBox="0 0 24 24">
						<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
						<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"/>
					</svg>
					복구 가능 여부 분석 중…
				</div>

			<!-- 오류 -->
			{:else if phase === 'error'}
				<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm">
					{errorMsg}
				</div>

			<!-- 분석 완료 / 실행 중 / 실행 완료 -->
			{:else if analysis}

				<!-- fault 메시지 -->
				{#if analysis.server.fault?.message}
					<div class="bg-surface-sunken border border-line-2 rounded-lg px-4 py-3">
						<div class="text-xs text-ink-2 mb-1 font-medium">FAULT 메시지</div>
						<div class="text-red-300 text-xs font-mono break-all leading-relaxed">{analysis.server.fault.message}</div>
					</div>
				{/if}

				<!-- 안전 검사 체크리스트 -->
				<div>
					<div class="text-xs font-medium text-ink-2 uppercase tracking-wide mb-2">안전 검사</div>
					<div class="space-y-1.5">
						{#each analysis.checks as check (check.key)}
							<div class="flex items-start gap-2.5 text-sm">
								{#if check.passed}
									<span class="mt-0.5 text-green-400 shrink-0 text-base leading-none">✓</span>
								{:else}
									<span class="mt-0.5 text-red-400 shrink-0 text-base leading-none">✗</span>
								{/if}
								<div>
									<span class={check.passed ? 'text-ink-1' : 'text-red-300 font-medium'}>{check.label}</span>
									{#if check.detail}
										<div class="text-ink-3 text-xs mt-0.5">{check.detail}</div>
									{/if}
								</div>
							</div>
						{/each}
					</div>
				</div>

				<!-- 시나리오 -->
				<div class="bg-surface-sunken border border-line-2 rounded-lg px-4 py-3">
					<div class="flex items-center gap-2 mb-1">
						<span class="text-xs text-ink-2 uppercase tracking-wide font-medium">시나리오</span>
						<span class="text-xs px-1.5 py-0.5 rounded bg-surface-selected text-ink-2 font-mono">{scenarioLabels[analysis.scenario] ?? analysis.scenario}</span>
					</div>
					<p class="text-ink-2 text-sm leading-relaxed">{analysis.scenario_description}</p>
				</div>

				<!-- 권장 단계 (실행 전) -->
				{#if phase === 'analyzed' || phase === 'executing'}
					<div>
						<div class="text-xs font-medium text-ink-2 uppercase tracking-wide mb-2">권장 복구 단계</div>
						<div class="space-y-1.5">
							{#each analysis.steps as step, i (i)}
								{#if step.action !== 'manual'}
									<div class="flex items-start gap-2.5 text-sm">
										<span class="shrink-0 w-5 h-5 rounded-full bg-surface-selected text-ink-2 text-xs flex items-center justify-center font-medium">{i + 1}</span>
										<span class="text-ink-2">{step.description}</span>
									</div>
								{:else}
									<div class="text-action-warm text-sm">{step.description}</div>
								{/if}
							{/each}
						</div>
					</div>
				{/if}

				<!-- 실행 결과 -->
				{#if phase === 'done' && result}
					<div>
						<div class="text-xs font-medium text-ink-2 uppercase tracking-wide mb-2">실행 결과</div>
						<div class="space-y-1.5">
							{#each result.steps as step, i (i)}
								<div class="flex items-start gap-2.5 text-sm">
									{#if step.status === 'success'}
										<span class="mt-0.5 text-green-400 shrink-0 text-base leading-none">✓</span>
									{:else if step.status === 'failed'}
										<span class="mt-0.5 text-red-400 shrink-0 text-base leading-none">✗</span>
									{:else}
										<span class="mt-0.5 text-ink-3 shrink-0 text-base leading-none">—</span>
									{/if}
									<div>
										<span class={step.status === 'failed' ? 'text-red-300' : step.status === 'skipped' ? 'text-ink-3' : 'text-ink-1'}>
											{step.description}
										</span>
										{#if step.detail}
											<div class="text-ink-3 text-xs mt-0.5">{step.detail}</div>
										{/if}
									</div>
								</div>
							{/each}
						</div>
						{#if result.executed}
							<div class="mt-3 bg-green-900/30 border border-green-700/50 text-green-300 rounded-lg px-4 py-2.5 text-sm">
								복구가 완료되었습니다. 인스턴스 상태를 확인하세요.
							</div>
						{:else}
							<div class="mt-3 bg-red-900/30 border border-red-700/50 text-red-300 rounded-lg px-4 py-2.5 text-sm">
								복구 중 오류가 발생했습니다. 위 결과를 확인하세요.
							</div>
						{/if}
					</div>
				{/if}

				<!-- placement 안내 -->
				{#if analysis.placement_note}
					<div class="bg-surface-selected/20 border border-action-warm/40 text-action-warm rounded-lg px-4 py-3 text-xs leading-relaxed">
						<span class="font-medium">Placement 주의:</span> {analysis.placement_note}
					</div>
				{/if}

				<!-- 수동 점검 안내 -->
				{#if !analysis.auto_executable && phase === 'analyzed'}
					<div class="bg-surface-sunken border border-action-warm/40 text-action-warm rounded-lg px-4 py-3 text-sm">
						<div class="font-medium mb-1">수동 점검이 필요합니다</div>
						<div class="text-xs text-action-warm/70">
							위 안전 검사를 통과하지 못해 자동 복구를 실행할 수 없습니다.
							실패한 항목을 확인하고 직접 복구하세요.
						</div>
					</div>
				{/if}

			{/if}
		</div>

		<!-- 푸터 버튼 -->
		<div class="flex items-center justify-between px-6 py-4 border-t border-line gap-4">
			{#if phase === 'analyzed' && analysis?.auto_executable}
				<label class="flex items-center gap-2 text-sm text-ink-2 cursor-pointer select-none">
					<input type="checkbox" bind:checked={confirmed} class="rounded border-line-2 bg-surface-sunken text-red-500 focus:ring-red-500 focus:ring-1" />
					<span>프로덕션 인스턴스 상태를 강제 변경합니다. 이 작업은 되돌리기 어렵습니다.</span>
				</label>
				<button
					onclick={execute}
					disabled={!confirmed}
					class="shrink-0 px-4 py-2 bg-red-700 hover:bg-red-600 disabled:opacity-40 disabled:cursor-not-allowed text-ink-0 text-sm font-medium rounded-lg transition-colors"
				>
					복구 실행
				</button>
			{:else if phase === 'executing'}
				<div class="flex items-center gap-2 text-ink-2 text-sm">
					<svg class="animate-spin w-4 h-4 text-action-warm" fill="none" viewBox="0 0 24 24">
						<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
						<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"/>
					</svg>
					복구 실행 중…
				</div>
				<div></div>
			{:else}
				<div></div>
				<button onclick={onClose} class="px-4 py-2 bg-surface-selected hover:bg-surface-selected text-ink-0 text-sm font-medium rounded-lg transition-colors">
					닫기
				</button>
			{/if}
		</div>
	</div>
</div>
