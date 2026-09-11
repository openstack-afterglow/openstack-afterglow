<script lang="ts">
	import DetailHeader from '$lib/components/ui/DetailHeader.svelte';
	import { useInstanceDetailController } from '$lib/stores/instanceDetailController.svelte';

	interface Props {
		adminProjectId: string | null;
		onOpenMigrateModal: (type: 'live' | 'cold') => void;
		onOpenPasswordModal: () => void;
		onOpenResizeModal: () => void;
		onOpenEvacuateModal: () => void;
	}

	let { adminProjectId, onOpenMigrateModal, onOpenPasswordModal, onOpenResizeModal, onOpenEvacuateModal }: Props = $props();

	const s = useInstanceDetailController();

	const btn = {
		base: 'text-sm px-3 py-1.5 rounded border transition-colors disabled:opacity-40 disabled:cursor-not-allowed',
		gray: 'text-ink-2 hover:text-ink-0 border-line-2 hover:border-line-2',
		green: 'text-green-400 hover:text-green-300 border-green-900 hover:border-green-700',
		yellow: 'text-yellow-400 hover:text-yellow-300 border-yellow-900 hover:border-yellow-700',
		blue: 'text-action-warm hover:text-action-warm-hover border-action-warm hover:border-action-warm',
		purple: 'text-purple-400 hover:text-purple-300 border-purple-900 hover:border-purple-700',
		cyan: 'text-cyan-400 hover:text-cyan-300 border-cyan-900 hover:border-cyan-700',
		teal: 'text-teal-400 hover:text-teal-300 border-teal-900 hover:border-teal-700',
		violet: 'text-violet-400 hover:text-violet-300 border-violet-900 hover:border-violet-700',
		amber: 'text-action-warm hover:text-action-warm-hover border-action-warm hover:border-action-warm',
		orange: 'text-orange-400 hover:text-orange-300 border-orange-900 hover:border-orange-700',
		red: 'text-red-400 hover:text-red-300 border-red-900 hover:border-red-700',
	};
</script>

<DetailHeader title={s.instance!.name} status={s.instance!.status} size="lg">
	{#snippet meta()}
		{#if s.instance!.status === 'ERROR' && s.instance!.fault?.message && adminProjectId}
			<div class="p-3 rounded-lg bg-red-900/30 border border-red-800/40 text-red-300 text-sm max-w-xl">
				<div class="font-medium mb-1 text-xs text-red-400">오류 상세 (관리자)</div>
				<div class="text-xs opacity-90 break-words">{s.instance!.fault!.message}</div>
			</div>
		{/if}
		{#if adminProjectId && s.instance!.status === 'MIGRATING' && s.migrationStatus?.migration}
			{@const mig = s.migrationStatus.migration}
			<div class="p-3 rounded-lg bg-cyan-900/20 border border-cyan-800/40 text-cyan-300 text-sm max-w-xl">
				<div class="font-medium mb-1 text-xs text-cyan-400">마이그레이션 진행 중</div>
				<div class="text-xs opacity-90">
					{mig.source ?? '?'} → {mig.dest ?? '?'}
					{#if mig.memory_percent !== null && mig.memory_percent !== undefined}
						· 메모리 {mig.memory_percent}%
					{/if}
				</div>
			</div>
		{/if}
		{#if adminProjectId && s.migrationStatus?.error && s.instance!.status !== 'ACTIVE'}
			<div class="p-3 rounded-lg bg-red-900/30 border border-red-800/40 text-red-300 text-sm max-w-xl">
				<div class="font-medium mb-1 text-xs text-red-400">마이그레이션 실패 (관리자)</div>
				<div class="text-xs opacity-90 break-words">{s.migrationStatus.error}</div>
			</div>
		{/if}
	{/snippet}
	{#snippet actions()}
		<div class="flex flex-col gap-2 items-end">
			<!-- 1행: 기본 동작 (콘솔 열기, 시작/중지, 재부팅, 보관) -->
			<div class="flex items-center gap-2 flex-wrap justify-end">
				{#if s.instance!.status === 'ACTIVE'}
					<button
						onclick={s.openConsole}
						disabled={s.consoleOpening}
						aria-busy={s.consoleOpening}
						aria-describedby={s.consoleOpening || s.consoleOpenError ? 'instance-console-status' : undefined}
						class="{btn.base} {btn.gray}"
					>
						{#if s.consoleOpening}
							<span class="inline-flex items-center gap-1.5">
								<span class="w-3 h-3 rounded-full border border-line-2 border-t-gray-200 animate-spin" aria-hidden="true"></span>
								콘솔 준비 중...
							</span>
						{:else}
							콘솔 열기
						{/if}
					</button>
					<button
						onclick={() => s.performAction('stop')}
						disabled={!!s.actioning}
						class="{btn.base} {btn.yellow}"
					>{s.actioning === 'stop' ? '정지 중...' : '정지'}</button>
					<button
						onclick={() => s.performAction('reboot')}
						disabled={!!s.actioning}
						class="{btn.base} {btn.blue}"
					>{s.actioning === 'reboot' ? '재부팅 중...' : '재부팅'}</button>
				{/if}
				{#if s.instance!.status === 'SHUTOFF'}
					<button
						onclick={() => s.performAction('start')}
						disabled={!!s.actioning}
						class="{btn.base} {btn.green}"
					>{s.actioning === 'start' ? '시작 중...' : '시작'}</button>
				{/if}
				{#if s.instance!.status === 'ACTIVE' || s.instance!.status === 'SHUTOFF'}
					<button
						onclick={() => s.performAction('shelve')}
						disabled={!!s.actioning}
						class="{btn.base} {btn.purple}"
					>{s.actioning === 'shelve' ? '보관 중...' : '보관'}</button>
				{/if}
				{#if s.instance!.status === 'SHELVED_OFFLOADED' || s.instance!.status === 'SHELVED'}
					<button
						onclick={() => s.performAction('unshelve')}
						disabled={!!s.actioning}
						class="{btn.base} {btn.green}"
					>{s.actioning === 'unshelve' ? '보관 해제 중...' : '보관 해제'}</button>
				{/if}
				{#if s.instance!.status === 'VERIFY_RESIZE'}
					<button
						onclick={s.confirmResize}
						disabled={!!s.actioning}
						class="{btn.base} {btn.orange}"
					>{s.actioning === 'confirm-resize' ? '확인 중...' : '리사이즈 확인'}</button>
					<button
						onclick={s.revertResize}
						disabled={!!s.actioning}
						class="{btn.base} {btn.yellow}"
					>{s.actioning === 'revert-resize' ? '취소 중...' : '되돌리기'}</button>
				{/if}
				{#if !adminProjectId}
					<button
						onclick={s.deleteInstance}
						disabled={s.deleting}
						class="{btn.base} {btn.red}"
					>{s.deleting ? '삭제 중...' : '삭제'}</button>
				{/if}
			</div>
			{#if s.consoleOpening || s.consoleOpenError}
				<div
					id="instance-console-status"
					role={s.consoleOpenError ? 'alert' : 'status'}
					aria-live={s.consoleOpenError ? 'assertive' : 'polite'}
					class="max-w-xl rounded-lg border px-3 py-2 text-xs {s.consoleOpenError ? 'bg-red-900/30 border-red-800/40 text-red-300' : 'bg-surface-selected/20 border-action-warm/40 text-action-warm'}"
				>
					{s.consoleOpenError || s.consoleOpenMessage}
				</div>
			{/if}

			{#if adminProjectId}
				<!-- 2행: 라이브 마이그레이션, 콜드 마이그레이션, 리사이즈 -->
				<div class="flex items-center gap-2 flex-wrap justify-end">
					{#if s.instance!.status === 'MIGRATING'}
						<button
							onclick={s.forceCompleteMigration}
							class="{btn.base} {btn.cyan}"
						>강제 완료</button>
						<button
							onclick={s.abortMigration}
							class="{btn.base} {btn.yellow}"
						>마이그레이션 중단</button>
					{:else}
						{#if s.instance!.status === 'ACTIVE'}
							<button
								onclick={() => onOpenMigrateModal('live')}
								disabled={!!s.actioning}
								class="{btn.base} {btn.cyan}"
							>라이브 마이그레이션</button>
						{/if}
						{#if s.instance!.status === 'ACTIVE' || s.instance!.status === 'SHUTOFF'}
							<button
								onclick={() => onOpenMigrateModal('cold')}
								disabled={!!s.actioning}
								class="{btn.base} {btn.teal}"
							>콜드 마이그레이션</button>
							<button
								onclick={onOpenResizeModal}
								disabled={!!s.actioning}
								class="{btn.base} {btn.violet}"
							>리사이즈</button>
						{/if}
					{/if}
				</div>

				<!-- 3행: 강제 이주, 비밀번호 변경, 삭제 -->
				<div class="flex items-center gap-2 flex-wrap justify-end">
					<button
						onclick={onOpenEvacuateModal}
						disabled={!!s.actioning}
						class="{btn.base} {btn.orange}"
					>강제 이주</button>
					<button
						onclick={onOpenPasswordModal}
						disabled={s.passwordPrecheckLoading || !s.passwordPrecheck?.supported}
						title={s.passwordPrecheck?.reason ?? (s.passwordPrecheckLoading ? '점검 중...' : '')}
						class="{btn.base} {btn.amber}"
					>{s.passwordPrecheckLoading ? '점검 중...' : '비밀번호 변경'}</button>
					<button
						onclick={s.deleteInstance}
						disabled={s.deleting}
						class="{btn.base} {btn.red}"
					>{s.deleting ? '삭제 중...' : '삭제'}</button>
				</div>
			{/if}
		</div>
	{/snippet}
</DetailHeader>
