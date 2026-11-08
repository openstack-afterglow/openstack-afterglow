<script lang="ts">
	import type { Snippet } from 'svelte';
	import DetailHeader from '$lib/components/ui/DetailHeader.svelte';
	import ActionMenu from '$lib/components/ui/ActionMenu.svelte';
	import StatusChip from '$lib/components/ui/StatusChip.svelte';
	import { mobileViewport } from '$lib/utils/mobileViewport';
	import { useInstanceDetailController } from '$lib/stores/instanceDetailController.svelte';
	import { t } from '$lib/i18n/ns/instance';
	import RichText from '$lib/i18n/RichText.svelte';
	import { t as tc } from '$lib/i18n/ns/common';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import { AnimatedNumber, Button, ProgressTrack } from '$lib/components/ui';
	import WaygateManagedNote from './WaygateManagedNote.svelte';
	import { createdInstance } from '$lib/tutorial/createdInstance.svelte';

	interface Props {
		adminProjectId: string | null;
		canMutate: boolean;
		onOpenMigrateModal: (type: 'live' | 'cold') => void;
		onOpenPasswordModal: () => void;
		onOpenResizeModal: () => void;
		onOpenEvacuateModal: () => void;
		/** Mobile only: the detail owner's refresh control, shown in the name row. */
		refresh?: Snippet;
	}

	let { adminProjectId, canMutate, onOpenMigrateModal, onOpenPasswordModal, onOpenResizeModal, onOpenEvacuateModal, refresh }: Props = $props();

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
	const lockTitle = $derived(s.waygateLocked ? t('waygate.managedNote') : undefined);
	// Tutorial anchors exist only on the tut- instance the instance-detail-delete tour just created.
	const tourCreated = $derived(!!s.instance && createdInstance.id === s.instance.id && s.instance.name.startsWith('tut-'));

	// Mobile (<768px): the header keeps only the lifecycle primaries inline; every other action
	// moves into one overflow menu with the same guards as the tablet/desktop buttons.
	let overflowOpen = $state(false);
	function fromOverflow(run: () => unknown) {
		overflowOpen = false;
		void run();
	}
	const mobileStatus = $derived(s.instance?.status);
	const hasOverflowActions = $derived(
		(canMutate && s.canRename)
		|| mobileStatus === 'ACTIVE'
		|| (canMutate && (mobileStatus === 'SHUTOFF' || s.canChangePassword))
		|| (!!adminProjectId && canMutate)
	);
	const hasInlineActions = $derived(canMutate && (
		mobileStatus === 'ACTIVE' || mobileStatus === 'SHUTOFF' || mobileStatus === 'SHELVED_OFFLOADED'
		|| mobileStatus === 'SHELVED' || mobileStatus === 'VERIFY_RESIZE'
	));
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
		{#if s.passwordPrecheckLoading}<LoadingState variant="control" label="" />{t('header.checking')}{:else}{t('header.changePassword')}{/if}
	</Button>
{/snippet}

{#snippet consoleStatus()}
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
{/snippet}

{#snippet headerMeta()}
		{#if s.waygateLocked}
			<WaygateManagedNote class="max-w-xl" />
		{/if}
		{#if s.instance!.status === 'ERROR' && s.instance!.fault?.message && adminProjectId}
			<div class="p-3 rounded-lg bg-red-900/30 border border-red-800/40 text-red-300 text-sm max-w-xl">
				<div class="font-medium mb-1 text-xs text-red-400">{t('header.errorDetails')}</div>
				<div class="text-xs opacity-90 break-words">{s.instance!.fault!.message}</div>
			</div>
		{/if}
		{#if adminProjectId && s.instance!.status === 'MIGRATING' && s.migrationStatus?.migration}
			{@const mig = s.migrationStatus.migration}
			<div class="p-3 rounded-lg bg-surface-sunken border border-line-2 text-ink-1 text-sm max-w-xl">
				<LoadingState variant="inline" label={t('header.migrationInProgress')} />
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

{#if mobileViewport.current}
	<div class="mb-6 grid min-w-0 gap-3" data-testid="instance-mobile-header">
		<!-- The name owns the first row (up to two lines); the pill sits beside it and wraps below only when it does not fit. -->
		<div class="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
			<h2 class="min-w-0 line-clamp-2 break-words [overflow-wrap:anywhere] text-[length:var(--type-console-title)] font-bold text-ink-0" title={s.instance!.name}>{s.instance!.name}</h2>
			<StatusChip status={s.instance!.status} kind="server" class="shrink-0" />
		</div>
		{@render headerMeta()}
		{#if hasInlineActions || refresh || hasOverflowActions}
			<div class="flex min-w-0 items-center gap-2">
				{#if hasInlineActions}
				<div class="flex min-w-0 flex-wrap items-center gap-2" data-testid="instance-mobile-primary-actions">
					{#if s.instance!.status === 'ACTIVE'}
						<Button onclick={() => s.performAction('stop')} disabled={busy} variant="outline" size="sm">
							{#if s.actioning === 'stop'}<LoadingState variant="control" label={t('header.stopping')} />{:else}{t('header.stop')}{/if}
						</Button>
						<Button onclick={() => s.performAction('reboot')} disabled={busy} variant="outline" size="sm">
							{#if s.actioning === 'reboot'}<LoadingState variant="control" label={t('header.rebooting')} />{:else}{t('header.reboot')}{/if}
						</Button>
					{:else if s.instance!.status === 'SHUTOFF'}
						<Button onclick={() => s.performAction('start')} disabled={busy} variant="primary" size="sm">
							{#if s.actioning === 'start'}<LoadingState variant="control" label={t('header.starting')} />{:else}{t('header.start')}{/if}
						</Button>
						{#if s.deleting}<LoadingState variant="control" label={t('header.deleting')} />{:else if s.actioning === 'shelve'}<LoadingState variant="control" label={t('header.shelving')} />{/if}
					{:else if s.instance!.status === 'SHELVED_OFFLOADED' || s.instance!.status === 'SHELVED'}
						<Button onclick={() => s.performAction('unshelve')} disabled={busy} variant="primary" size="sm">
							{#if s.actioning === 'unshelve'}<LoadingState variant="control" label={t('header.unshelving')} />{:else}{t('header.unshelve')}{/if}
						</Button>
					{:else if s.instance!.status === 'VERIFY_RESIZE'}
						<Button onclick={s.confirmResize} disabled={busy} variant="primary" size="sm">
							{#if s.actioning === 'confirm-resize'}<LoadingState variant="control" label={t('header.confirming')} />{:else}{t('header.confirmResize')}{/if}
						</Button>
						<Button onclick={s.revertResize} disabled={busy} variant="outline" size="sm">
							{#if s.actioning === 'revert-resize'}<LoadingState variant="control" label={t('header.canceling')} />{:else}{t('header.revert')}{/if}
						</Button>
					{/if}
				</div>
				{/if}
				<div class="ml-auto flex shrink-0 items-center gap-1">
					{#if refresh}{@render refresh()}{/if}
					{#if hasOverflowActions}
						<ActionMenu
							open={overflowOpen}
							ariaLabel={t('rowActions.instanceActions', { name: s.instance!.name || s.instance!.id })}
							onopen={() => { overflowOpen = true; }}
							onclose={() => { overflowOpen = false; }}
						>
							{#if canMutate && s.canRename}
								<Button onclick={() => fromOverflow(s.openRename)} disabled={busy || s.renameLoading || s.waygateLocked} title={lockTitle} variant="ghost" size="sm" class="w-full justify-start">{t('rename.title')}</Button>
							{/if}
							{#if s.instance!.status === 'ACTIVE'}
								<Button onclick={() => fromOverflow(s.openConsole)} disabled={s.consoleOpening} ariaBusy={s.consoleOpening} variant="ghost" size="sm" class="w-full justify-start">{t('header.openConsole')}</Button>
							{/if}
							{#if canMutate && s.instance!.status === 'SHUTOFF'}
								<Button onclick={() => fromOverflow(() => s.performAction('shelve'))} disabled={busy || s.waygateLocked} title={lockTitle} variant="ghost" size="sm" class="w-full justify-start">{t('header.shelve')}</Button>
							{/if}
							{#if canMutate && (s.instance!.status === 'ACTIVE' || s.instance!.status === 'SHUTOFF')}
								<Button onclick={() => fromOverflow(onOpenResizeModal)} disabled={busy || s.waygateLocked} title={lockTitle} variant="ghost" size="sm" class="w-full justify-start">{t('header.resize')}</Button>
							{/if}
							{#if canMutate && s.canChangePassword}
								<Button
									onclick={() => fromOverflow(onOpenPasswordModal)}
									disabled={busy || s.instance?.status !== 'ACTIVE' || s.passwordPrecheckLoading || !s.passwordPrecheck?.supported}
									title={s.passwordPrecheckReason ?? (s.passwordPrecheckLoading ? t('header.checking') : s.passwordPrecheckError)}
									variant="ghost"
									size="sm"
									class="w-full justify-start"
									ariaBusy={s.passwordPrecheckLoading}
								>
									{#if s.passwordPrecheckLoading}<LoadingState variant="control" label="" />{t('header.checking')}{:else}{t('header.changePassword')}{/if}
								</Button>
							{/if}
							{#if adminProjectId && canMutate}
								{#if s.instance!.status === 'MIGRATING'}
									<Button onclick={() => fromOverflow(() => requestMigrationControl('complete'))} disabled={migrationRequest !== null} variant="ghost" size="sm" class="w-full justify-start">{t('header.forceComplete')}</Button>
									<Button onclick={() => fromOverflow(() => requestMigrationControl('abort'))} disabled={migrationRequest !== null} variant="ghost" size="sm" class="w-full justify-start">{t('header.abortMigration')}</Button>
								{:else}
									{#if s.instance!.status === 'ACTIVE'}
										<Button onclick={() => fromOverflow(() => onOpenMigrateModal('live'))} disabled={busy} variant="ghost" size="sm" class="w-full justify-start">{t('header.liveMigration')}</Button>
									{/if}
									{#if s.instance!.status === 'ACTIVE' || s.instance!.status === 'SHUTOFF'}
										<Button onclick={() => fromOverflow(() => onOpenMigrateModal('cold'))} disabled={busy} variant="ghost" size="sm" class="w-full justify-start">{t('header.coldMigration')}</Button>
									{/if}
								{/if}
								<Button onclick={() => fromOverflow(onOpenEvacuateModal)} disabled={busy} variant="ghost" size="sm" class="w-full justify-start">{t('header.evacuate')}</Button>
							{/if}
							{#if canMutate && s.instance!.status === 'SHUTOFF'}
								<Button onclick={() => fromOverflow(s.deleteInstance)} disabled={busy || s.waygateLocked} title={lockTitle} variant="danger-outline" size="sm" class="w-full justify-start">{t('header.delete')}</Button>
							{/if}
						</ActionMenu>
					{/if}
				</div>
			</div>
		{/if}
		{#if migrationRequest !== null}
			<LoadingState variant="control" label={`${t(migrationRequest === 'complete' ? 'header.forceComplete' : 'header.abortMigration')} · ${tc('state.processing')}`} />
		{/if}
		{@render consoleStatus()}
		{#if s.canChangePassword && !s.passwordPrecheckLoading && (s.passwordPrecheckReason || s.passwordPrecheckError)}
			<p class="max-w-md text-xs text-ink-2">{s.passwordPrecheckReason || s.passwordPrecheckError}</p>
		{/if}
	</div>
{:else}
<DetailHeader title={s.instance!.name} status={s.instance!.status} statusKind="server" size="lg" meta={headerMeta}>
	{#snippet actions()}
		<div class="flex flex-col gap-2 items-end">
			<div class="flex items-center gap-2 flex-wrap justify-end">
				{#if canMutate && s.canRename}
					<Button onclick={s.openRename} disabled={busy || s.renameLoading || s.waygateLocked} title={lockTitle} variant="outline" size="sm">{t('rename.title')}</Button>
				{/if}
				{#if s.instance!.status === 'ACTIVE'}
					<Button onclick={s.openConsole} disabled={s.consoleOpening} ariaBusy={s.consoleOpening} variant="outline" size="sm">
						{#if s.consoleOpening}
							<LoadingState variant="control" label="" />{t('header.consolePreparing')}
						{:else}
							{t('header.openConsole')}
						{/if}
					</Button>
					{#if canMutate}
						<Button onclick={() => s.performAction('stop')} disabled={busy} variant="outline" size="sm" dataTour={tourCreated ? 'instance-detail-stop' : undefined}>
							{#if s.actioning === 'stop'}<LoadingState variant="control" label={t('header.stopping')} />{:else}{t('header.stop')}{/if}
						</Button>
						<Button onclick={() => s.performAction('reboot')} disabled={busy} variant="outline" size="sm">
							{#if s.actioning === 'reboot'}<LoadingState variant="control" label={t('header.rebooting')} />{:else}{t('header.reboot')}{/if}
						</Button>
						<Button onclick={() => onOpenResizeModal()} disabled={busy || s.waygateLocked} title={lockTitle} variant="outline" size="sm">{t('header.resize')}</Button>
					{/if}
				{/if}
				{#if canMutate && s.instance!.status === 'SHUTOFF'}
					<Button onclick={() => s.performAction('start')} disabled={busy} variant="primary" size="sm">
						{#if s.actioning === 'start'}<LoadingState variant="control" label={t('header.starting')} />{:else}{t('header.start')}{/if}
					</Button>
					<Button onclick={() => s.performAction('shelve')} disabled={busy || s.waygateLocked} title={lockTitle} variant="outline" size="sm">
						{#if s.actioning === 'shelve'}<LoadingState variant="control" label={t('header.shelving')} />{:else}{t('header.shelve')}{/if}
					</Button>
					<Button onclick={s.deleteInstance} disabled={busy || s.waygateLocked} title={lockTitle} variant="danger-outline" size="sm" dataTour={tourCreated ? 'instance-detail-delete' : undefined}>
						{#if s.deleting}<LoadingState variant="control" label={t('header.deleting')} />{:else}{t('header.delete')}{/if}
					</Button>
					<Button onclick={() => onOpenResizeModal()} disabled={busy || s.waygateLocked} title={lockTitle} variant="outline" size="sm">{t('header.resize')}</Button>
				{/if}
				{#if canMutate && (s.instance!.status === 'SHELVED_OFFLOADED' || s.instance!.status === 'SHELVED')}
					<Button onclick={() => s.performAction('unshelve')} disabled={busy} variant="primary" size="sm">
						{#if s.actioning === 'unshelve'}<LoadingState variant="control" label={t('header.unshelving')} />{:else}{t('header.unshelve')}{/if}
					</Button>
				{/if}
				{#if canMutate && s.instance!.status === 'VERIFY_RESIZE'}
					<Button onclick={s.confirmResize} disabled={busy} variant="primary" size="sm">
						{#if s.actioning === 'confirm-resize'}<LoadingState variant="control" label={t('header.confirming')} />{:else}{t('header.confirmResize')}{/if}
					</Button>
					<Button onclick={s.revertResize} disabled={busy} variant="outline" size="sm">
						{#if s.actioning === 'revert-resize'}<LoadingState variant="control" label={t('header.canceling')} />{:else}{t('header.revert')}{/if}
					</Button>
				{/if}
			</div>
			{@render consoleStatus()}

			{#if adminProjectId && canMutate}
				<!-- 2행: 라이브 마이그레이션, 콜드 마이그레이션 -->
				<div class="flex items-center gap-2 flex-wrap justify-end">
					{#if s.instance!.status === 'MIGRATING'}
						<Button onclick={() => requestMigrationControl('complete')} disabled={migrationRequest !== null} variant="outline" size="sm">
							{#if migrationRequest === 'complete'}<LoadingState variant="control" label={`${t('header.forceComplete')} · ${tc('state.processing')}`} />{:else}{t('header.forceComplete')}{/if}
						</Button>
						<Button onclick={() => requestMigrationControl('abort')} disabled={migrationRequest !== null} variant="outline" size="sm">
							{#if migrationRequest === 'abort'}<LoadingState variant="control" label={`${t('header.abortMigration')} · ${tc('state.processing')}`} />{:else}{t('header.abortMigration')}{/if}
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
{/if}
