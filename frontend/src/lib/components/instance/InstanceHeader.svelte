<script lang="ts">
	import DetailHeader from '$lib/components/ui/DetailHeader.svelte';
	import { useInstanceDetailController } from '$lib/stores/instanceDetailController.svelte';
	import { t } from '$lib/i18n/ns/instance';
	import RichText from '$lib/i18n/RichText.svelte';
	import { t as tc } from '$lib/i18n/ns/common';
	import { ActivityIndicator, AnimatedNumber, ProgressTrack } from '$lib/components/ui';

	interface Props {
		adminProjectId: string | null;
		canMutate: boolean;
		onOpenMigrateModal: (type: 'live' | 'cold') => void;
		onOpenPasswordModal: () => void;
		onOpenResizeModal: () => void;
		onOpenEvacuateModal: () => void;
	}

	let { adminProjectId, canMutate, onOpenMigrateModal, onOpenPasswordModal, onOpenResizeModal, onOpenEvacuateModal }: Props = $props();

	const s = useInstanceDetailController();
	let migrationRequest = $state<'complete' | 'abort' | null>(null);
	async function requestMigrationControl(kind: 'complete' | 'abort') {
		migrationRequest = kind;
		try {
			if (kind === 'complete') await s.forceCompleteMigration();
			else await s.abortMigration();
		} finally {
			migrationRequest = null;
		}
	}

	const btn = {
		base: 'text-sm px-3 py-1.5 rounded border transition-colors disabled:opacity-40 disabled:cursor-not-allowed',
		gray: 'text-ink-2 hover:text-ink-0 border-line-2 hover:border-line-2',
		green: 'text-green-400 hover:text-green-300 border-green-900 hover:border-green-700',
		yellow: 'text-yellow-400 hover:text-yellow-300 border-yellow-900 hover:border-yellow-700',
		blue: 'text-warm-text hover:text-warm-text-hover border-action-warm hover:border-action-warm',
		purple: 'text-purple-400 hover:text-purple-300 border-purple-900 hover:border-purple-700',
		cyan: 'text-cyan-400 hover:text-cyan-300 border-cyan-900 hover:border-cyan-700',
		teal: 'text-teal-400 hover:text-teal-300 border-teal-900 hover:border-teal-700',
		violet: 'text-violet-400 hover:text-violet-300 border-violet-900 hover:border-violet-700',
		amber: 'text-warm-text hover:text-warm-text-hover border-action-warm hover:border-action-warm',
		orange: 'text-orange-400 hover:text-orange-300 border-orange-900 hover:border-orange-700',
		red: 'text-red-400 hover:text-red-300 border-red-900 hover:border-red-700',
	};
</script>

<DetailHeader title={s.instance!.name} status={s.instance!.status} size="lg">
	{#snippet meta()}
		{#if s.instance!.status === 'ERROR' && s.instance!.fault?.message && adminProjectId}
			<div class="p-3 rounded-lg bg-red-900/30 border border-red-800/40 text-red-300 text-sm max-w-xl">
				<div class="font-medium mb-1 text-xs text-red-400">{t('header.errorDetails')}</div>
				<div class="text-xs opacity-90 break-words">{s.instance!.fault!.message}</div>
			</div>
		{/if}
		{#if adminProjectId && s.instance!.status === 'MIGRATING' && s.migrationStatus?.migration}
			{@const mig = s.migrationStatus.migration}
			<div class="p-3 rounded-lg bg-surface-sunken border border-line-2 text-ink-1 text-sm max-w-xl">
				<ActivityIndicator variant="pulse" label={t('header.migrationInProgress')} />
				<div class="text-xs opacity-90">
					{mig.source ?? '?'} → {mig.dest ?? '?'}
					{#if mig.memory_percent !== null && mig.memory_percent !== undefined}
						{#snippet memoryPercent(text: string)}<AnimatedNumber value={mig.memory_percent!} format={(value) => String(value === mig.memory_percent ? value : Number(value.toFixed(3)))} />{/snippet}
						<RichText segments={t.rich('header.migrationMemory', { percent: mig.memory_percent })} tags={{ percent: memoryPercent }} />
					{/if}
				</div>
				<ProgressTrack value={mig.memory_percent ?? null} label={t('header.migrationInProgress')} active />
			</div>
		{/if}
		{#if adminProjectId && s.migrationStatus?.error && s.instance!.status !== 'ACTIVE'}
			<div class="p-3 rounded-lg bg-red-900/30 border border-red-800/40 text-red-300 text-sm max-w-xl">
				<div class="font-medium mb-1 text-xs text-red-400">{t('header.migrationFailed')}</div>
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
							<span class="inline-flex items-center gap-1.5"><ActivityIndicator size="xs" />{t('header.consolePreparing')}</span>
						{:else}
							{t('header.openConsole')}
						{/if}
					</button>
					{#if canMutate}
						<button
							onclick={() => s.performAction('stop')}
							disabled={!!s.actioning}
							class="{btn.base} {btn.yellow}"
						>{#if s.actioning === 'stop'}<ActivityIndicator size="xs" label={t('header.stopping')} />{:else}{t('header.stop')}{/if}</button>
						<button
							onclick={() => s.performAction('reboot')}
							disabled={!!s.actioning}
							class="{btn.base} {btn.blue}"
						>{#if s.actioning === 'reboot'}<ActivityIndicator size="xs" label={t('header.rebooting')} />{:else}{t('header.reboot')}{/if}</button>
					{/if}
				{/if}
				{#if canMutate && s.instance!.status === 'SHUTOFF'}
					<button
						onclick={() => s.performAction('start')}
						disabled={!!s.actioning}
						class="{btn.base} {btn.green}"
					>{#if s.actioning === 'start'}<ActivityIndicator size="xs" label={t('header.starting')} />{:else}{t('header.start')}{/if}</button>
				{/if}
				{#if canMutate && (s.instance!.status === 'ACTIVE' || s.instance!.status === 'SHUTOFF')}
					<button
						onclick={() => s.performAction('shelve')}
						disabled={!!s.actioning}
						class="{btn.base} {btn.purple}"
					>{#if s.actioning === 'shelve'}<ActivityIndicator size="xs" label={t('header.shelving')} />{:else}{t('header.shelve')}{/if}</button>
				{/if}
				{#if canMutate && (s.instance!.status === 'SHELVED_OFFLOADED' || s.instance!.status === 'SHELVED')}
					<button
						onclick={() => s.performAction('unshelve')}
						disabled={!!s.actioning}
						class="{btn.base} {btn.green}"
					>{#if s.actioning === 'unshelve'}<ActivityIndicator size="xs" label={t('header.unshelving')} />{:else}{t('header.unshelve')}{/if}</button>
				{/if}
				{#if canMutate && s.instance!.status === 'VERIFY_RESIZE'}
					<button
						onclick={s.confirmResize}
						disabled={!!s.actioning}
						class="{btn.base} {btn.orange}"
					>{#if s.actioning === 'confirm-resize'}<ActivityIndicator size="xs" label={t('header.confirming')} />{:else}{t('header.confirmResize')}{/if}</button>
					<button
						onclick={s.revertResize}
						disabled={!!s.actioning}
						class="{btn.base} {btn.yellow}"
					>{#if s.actioning === 'revert-resize'}<ActivityIndicator size="xs" label={t('header.canceling')} />{:else}{t('header.revert')}{/if}</button>
				{/if}
				{#if canMutate && !adminProjectId}
					<button
						onclick={s.deleteInstance}
						disabled={s.deleting}
						class="{btn.base} {btn.red}"
					>{#if s.deleting}<ActivityIndicator size="xs" label={t('header.deleting')} />{:else}{t('header.delete')}{/if}</button>
				{/if}
			</div>
			{#if s.consoleOpening || s.consoleOpenError}
				<div
					id="instance-console-status"
					role={s.consoleOpenError ? 'alert' : 'status'}
					aria-live={s.consoleOpenError ? 'assertive' : 'polite'}
					class="max-w-xl rounded-lg border px-3 py-2 text-xs {s.consoleOpenError ? 'bg-red-900/30 border-red-800/40 text-red-300' : 'bg-surface-selected/20 border-action-warm/40 text-warm-text'}"
				>
					{s.consoleOpenError || s.consoleOpenMessage}
				</div>
			{/if}

			{#if adminProjectId && canMutate}
				<!-- 2행: 라이브 마이그레이션, 콜드 마이그레이션 -->
				<div class="flex items-center gap-2 flex-wrap justify-end">
					{#if s.instance!.status === 'MIGRATING'}
						<button
							onclick={() => requestMigrationControl('complete')}
							disabled={migrationRequest !== null}
							class="{btn.base} {btn.cyan}"
						>{#if migrationRequest === 'complete'}<ActivityIndicator size="xs" label={`${t('header.forceComplete')} · ${tc('state.processing')}`} />{:else}{t('header.forceComplete')}{/if}</button>
						<button
							onclick={() => requestMigrationControl('abort')}
							disabled={migrationRequest !== null}
							class="{btn.base} {btn.yellow}"
						>{#if migrationRequest === 'abort'}<ActivityIndicator size="xs" label={`${t('header.abortMigration')} · ${tc('state.processing')}`} />{:else}{t('header.abortMigration')}{/if}</button>
					{:else}
						{#if s.instance!.status === 'ACTIVE'}
							<button
								onclick={() => onOpenMigrateModal('live')}
								disabled={!!s.actioning}
								class="{btn.base} {btn.cyan}"
							>{t('header.liveMigration')}</button>
						{/if}
						{#if s.instance!.status === 'ACTIVE' || s.instance!.status === 'SHUTOFF'}
							<button
								onclick={() => onOpenMigrateModal('cold')}
								disabled={!!s.actioning}
								class="{btn.base} {btn.teal}"
							>{t('header.coldMigration')}</button>
						{/if}
					{/if}
				</div>

				<!-- 3행: 강제 이주, 비밀번호 변경, 삭제 -->
				<div class="flex items-center gap-2 flex-wrap justify-end">
					<button
						onclick={onOpenEvacuateModal}
						disabled={!!s.actioning}
						class="{btn.base} {btn.orange}"
					>{t('header.evacuate')}</button>
					<button
						onclick={onOpenPasswordModal}
						disabled={s.passwordPrecheckLoading || !s.passwordPrecheck?.supported}
						title={s.passwordPrecheck?.reason ?? (s.passwordPrecheckLoading ? t('header.checking') : '')}
						class="{btn.base} {btn.amber}"
					>{#if s.passwordPrecheckLoading}<ActivityIndicator size="xs" label={t('header.checking')} />{:else}{t('header.changePassword')}{/if}</button>
					<button
						onclick={s.deleteInstance}
						disabled={s.deleting}
						class="{btn.base} {btn.red}"
					>{#if s.deleting}<ActivityIndicator size="xs" label={t('header.deleting')} />{:else}{t('header.delete')}{/if}</button>
				</div>
			{/if}
			{#if canMutate && (s.instance!.status === 'ACTIVE' || s.instance!.status === 'SHUTOFF')}
				<div class="flex items-center gap-2 flex-wrap justify-end">
					<button onclick={() => onOpenResizeModal()} disabled={!!s.actioning} class="{btn.base} {btn.violet}">{t('header.resize')}</button>
				</div>
			{/if}
		</div>
	{/snippet}
</DetailHeader>
