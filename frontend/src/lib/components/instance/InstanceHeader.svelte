<script lang="ts">
	import DetailHeader from '$lib/components/ui/DetailHeader.svelte';
	import { useInstanceDetailController } from '$lib/stores/instanceDetailController.svelte';
	import { t } from '$lib/i18n/ns/instance';
	import RichText from '$lib/i18n/RichText.svelte';
	import { t as tc } from '$lib/i18n/ns/common';
	import { ActivityIndicator, AnimatedNumber, Button, ProgressTrack } from '$lib/components/ui';

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

	const busy = $derived(!!s.actioning || s.deleting || s.resizeLoading);
</script>

{#snippet passwordAction()}
	<Button
		onclick={onOpenPasswordModal}
		disabled={busy || s.instance?.status !== 'ACTIVE' || s.passwordPrecheckLoading || !s.passwordPrecheck?.supported}
		title={s.passwordPrecheckReason ?? (s.passwordPrecheckLoading ? t('header.checking') : s.passwordPrecheckError)}
		variant="outline"
		size="sm"
		ariaBusy={s.passwordPrecheckLoading}
	>
		{#if s.passwordPrecheckLoading}<ActivityIndicator size="xs" />{t('header.checking')}{:else}{t('header.changePassword')}{/if}
	</Button>
{/snippet}

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
			<div class="flex items-center gap-2 flex-wrap justify-end">
				{#if canMutate && s.canRename}
					<Button onclick={s.openRename} disabled={busy || s.renameLoading} variant="outline" size="sm">{t('rename.title')}</Button>
				{/if}
				{#if s.instance!.status === 'ACTIVE'}
					<Button onclick={s.openConsole} disabled={s.consoleOpening} ariaBusy={s.consoleOpening} variant="outline" size="sm">
						{#if s.consoleOpening}
							<ActivityIndicator size="xs" />{t('header.consolePreparing')}
						{:else}
							{t('header.openConsole')}
						{/if}
					</Button>
					{#if canMutate}
						<Button onclick={() => s.performAction('stop')} disabled={busy} variant="outline" size="sm">
							{#if s.actioning === 'stop'}<ActivityIndicator size="xs" label={t('header.stopping')} />{:else}{t('header.stop')}{/if}
						</Button>
						<Button onclick={() => s.performAction('reboot')} disabled={busy} variant="outline" size="sm">
							{#if s.actioning === 'reboot'}<ActivityIndicator size="xs" label={t('header.rebooting')} />{:else}{t('header.reboot')}{/if}
						</Button>
					{/if}
				{/if}
				{#if canMutate && s.instance!.status === 'SHUTOFF'}
					<Button onclick={() => s.performAction('start')} disabled={busy} variant="primary" size="sm">
						{#if s.actioning === 'start'}<ActivityIndicator size="xs" label={t('header.starting')} />{:else}{t('header.start')}{/if}
					</Button>
					<Button onclick={() => s.performAction('shelve')} disabled={busy} variant="outline" size="sm">
						{#if s.actioning === 'shelve'}<ActivityIndicator size="xs" label={t('header.shelving')} />{:else}{t('header.shelve')}{/if}
					</Button>
					<Button onclick={s.deleteInstance} disabled={busy} variant="danger-outline" size="sm">
						{#if s.deleting}<ActivityIndicator size="xs" label={t('header.deleting')} />{:else}{t('header.delete')}{/if}
					</Button>
					<Button onclick={onOpenResizeModal} disabled={busy} variant="outline" size="sm">{t('header.resize')}</Button>
				{/if}
				{#if canMutate && (s.instance!.status === 'SHELVED_OFFLOADED' || s.instance!.status === 'SHELVED')}
					<Button onclick={() => s.performAction('unshelve')} disabled={busy} variant="primary" size="sm">
						{#if s.actioning === 'unshelve'}<ActivityIndicator size="xs" label={t('header.unshelving')} />{:else}{t('header.unshelve')}{/if}
					</Button>
				{/if}
				{#if canMutate && s.instance!.status === 'VERIFY_RESIZE'}
					<Button onclick={s.confirmResize} disabled={busy} variant="primary" size="sm">
						{#if s.actioning === 'confirm-resize'}<ActivityIndicator size="xs" label={t('header.confirming')} />{:else}{t('header.confirmResize')}{/if}
					</Button>
					<Button onclick={s.revertResize} disabled={busy} variant="outline" size="sm">
						{#if s.actioning === 'revert-resize'}<ActivityIndicator size="xs" label={t('header.canceling')} />{:else}{t('header.revert')}{/if}
					</Button>
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
						<Button onclick={() => requestMigrationControl('complete')} disabled={migrationRequest !== null} variant="outline" size="sm">
							{#if migrationRequest === 'complete'}<ActivityIndicator size="xs" label={`${t('header.forceComplete')} · ${tc('state.processing')}`} />{:else}{t('header.forceComplete')}{/if}
						</Button>
						<Button onclick={() => requestMigrationControl('abort')} disabled={migrationRequest !== null} variant="outline" size="sm">
							{#if migrationRequest === 'abort'}<ActivityIndicator size="xs" label={`${t('header.abortMigration')} · ${tc('state.processing')}`} />{:else}{t('header.abortMigration')}{/if}
						</Button>
					{:else}
						{#if s.instance!.status === 'ACTIVE'}
							<Button onclick={() => onOpenMigrateModal('live')} disabled={busy} variant="outline" size="sm">{t('header.liveMigration')}</Button>
						{/if}
						{#if s.instance!.status === 'ACTIVE' || s.instance!.status === 'SHUTOFF'}
							<Button onclick={() => onOpenMigrateModal('cold')} disabled={busy} variant="outline" size="sm">{t('header.coldMigration')}</Button>
						{/if}
					{/if}
				</div>

				<!-- Administrator recovery and password actions remain separate. -->
				<div class="flex items-center gap-2 flex-wrap justify-end">
					<Button onclick={onOpenEvacuateModal} disabled={busy} variant="outline" size="sm">{t('header.evacuate')}</Button>
					{#if s.canChangePassword}{@render passwordAction()}{/if}
				</div>
			{/if}
			{#if canMutate && !adminProjectId && s.canChangePassword}
				<div class="flex items-center gap-2 flex-wrap justify-end">
					{@render passwordAction()}
				</div>
			{/if}
			{#if s.canChangePassword && !s.passwordPrecheckLoading && (s.passwordPrecheckReason || s.passwordPrecheckError)}
				<p class="max-w-md text-xs text-ink-2">{s.passwordPrecheckReason || s.passwordPrecheckError}</p>
			{/if}
		</div>
	{/snippet}
</DetailHeader>
