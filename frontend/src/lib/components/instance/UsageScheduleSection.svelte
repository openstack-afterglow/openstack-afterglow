<script lang="ts">
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import { onMount } from 'svelte';
	import { Alert, Button, Pill } from '$lib/components/ui';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import { t } from '$lib/i18n/ns/usage-schedule';
	import { createInstanceUsageController } from '$lib/stores/instanceUsageController.svelte';
	import { calendarMonthAfter, fromLocalDateTime, toLocalDateTime, usageDraftError } from '$lib/utils/instanceUsage';
	import UsageScheduleFields from './UsageScheduleFields.svelte';

	let { instanceId, projectId, adminMode = false, canWrite = false, onUpdated }: {
		instanceId: string;
		projectId: string | undefined;
		adminMode?: boolean;
		canWrite?: boolean;
		onUpdated?: () => void;
	} = $props();
	let section: HTMLElement;
	onMount(() => {
		// Native ownership loads after route-level hash scrolling has already run.
		if (window.location.hash === '#usage-schedule') section.scrollIntoView({ block: 'start', behavior: 'instant' });
	});

	const controller = createInstanceUsageController({
		instanceId: () => instanceId, projectId: () => projectId,
		adminMode: () => adminMode, canWrite: () => canWrite, onUpdated: () => onUpdated?.(),
	});
	const locked = $derived(!!controller.schedule && !['active', 'blocked', 'complete'].includes(controller.schedule.state));
	const draftError = $derived(usageDraftError(controller.draft, controller.schedule?.expires_at));
	const resumeError = $derived.by(() => {
		if (!controller.schedule || !['blocked', 'complete'].includes(controller.schedule.state)) return null;
		const expires = fromLocalDateTime(controller.draft.expiresLocal);
		if (!expires || Date.parse(expires) <= Date.now()) return 'pastDate';
		return Date.parse(expires) <= Date.parse(controller.schedule.expires_at) ? 'shorterDate' : null;
	});

	function formatDate(value: string) {
		return new Intl.DateTimeFormat(intlLocale(), {
			year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', timeZoneName: 'short',
		}).format(new Date(value));
	}

	function extendDraft() {
		if (!controller.editable) return;
		const expires = fromLocalDateTime(controller.draft.expiresLocal);
		if (!expires) return;
		controller.draft = { ...controller.draft, expiresLocal: toLocalDateTime(calendarMonthAfter(new Date(expires)).toISOString()) };
	}
</script>

<section bind:this={section} id="usage-schedule" aria-labelledby="usage-schedule-title" aria-busy={controller.loading || controller.saving}
	class="usage-schedule mb-4 min-w-0 scroll-mt-4 rounded-lg border border-line bg-surface-base p-4 md:p-6">
	<div class="mb-4 flex min-w-0 flex-wrap items-start justify-between gap-3">
		<h2 id="usage-schedule-title" class="min-w-0 break-words text-[15px] font-semibold text-ink-0">{t('title')}</h2>
		<Button variant="secondary" size="sm" class="min-h-11 max-w-full whitespace-normal" disabled={controller.loading || controller.saving}
			onclick={() => void controller.refresh()}>{t('refresh')}</Button>
	</div>

	<div class="min-w-0 space-y-4 break-words [overflow-wrap:anywhere]">
		{#if controller.loading}<LoadingState variant="inline" label={t('loading')} />{/if}
		{#if controller.error}<Alert tone="danger">{controller.error}</Alert>{/if}
		{#if controller.saved}<Alert tone="success">{t('saved')}</Alert>{/if}

		{#if controller.schedule}
			{@const schedule = controller.schedule}
			<div class="flex min-w-0 flex-wrap items-center gap-2">
				<Pill tone={locked || schedule.last_error || schedule.state === 'blocked' ? 'danger' : schedule.state === 'complete' ? 'neutral' : 'info'}
					class="max-w-full whitespace-normal text-xs">{t(`state.${schedule.state}`)}</Pill>
				<p class="min-w-0 text-sm text-ink-2">{t(schedule.source === 'adopted' ? 'sourceAdopted' : 'sourceCreated')}</p>
			</div>
			<dl class="grid min-w-0 grid-cols-1 gap-4 text-sm md:grid-cols-2">
				<div class="min-w-0"><dt class="mb-1 text-xs text-ink-2">{t('starts')}</dt>
					<dd class="tabular-nums text-ink-0"><time datetime={schedule.starts_at}>{formatDate(schedule.starts_at)}</time></dd></div>
				<div class="min-w-0"><dt class="mb-1 text-xs text-ink-2">{t('expires')}</dt>
					<dd class="tabular-nums text-ink-0"><time datetime={schedule.expires_at}>{formatDate(schedule.expires_at)}</time></dd></div>
				<div class="min-w-0"><dt class="mb-1 text-xs text-ink-2">{t('action')}</dt>
					<dd class="text-ink-0">{t(schedule.expiry_action === 'delete' ? 'delete' : 'shelve')}</dd></div>
				{#if schedule.reason}<div class="min-w-0"><dt class="mb-1 text-xs text-ink-2">{t('lastReason')}</dt>
					<dd class="whitespace-pre-wrap text-ink-0">{schedule.reason}</dd></div>{/if}
			</dl>
			{#if schedule.delete_volumes}<Alert tone="warning">{t('deleteVolumes')}<br />{t('destructive')}</Alert>
			{:else}<p class="text-sm text-ink-2">{t('retain')}</p>{/if}
			{#if schedule.expiry_action === 'delete'}<p class="text-xs leading-relaxed text-ink-2">{t('storageScope')}</p>{/if}
			<p class="text-sm text-ink-2">{t('noResume')}</p>
			{#if schedule.last_error}<Alert tone="danger">{schedule.last_error}</Alert>{/if}
			{#if locked}<Alert tone="danger">{t('locked')}</Alert>{/if}
			{#if !canWrite}
				<p class="text-sm text-ink-2">{t('readonly')}</p>
			{:else}
				<form class="min-w-0 space-y-4 border-t border-line pt-4" aria-label={t('edit')}
					onsubmit={(event) => { event.preventDefault(); void controller.save(); }}>
					<UsageScheduleFields value={controller.draft} onchange={(value) => { controller.draft = value; }}
						disabled={!controller.editable} currentExpiry={schedule.expires_at} idPrefix="usage-schedule-edit" />
					{#if resumeError && !draftError}<Alert tone="danger">{t(resumeError)}</Alert>{/if}
					<div class="flex min-w-0 flex-wrap gap-2">
						<Button variant="secondary" class="min-h-11 max-w-full whitespace-normal" disabled={!controller.editable}
							onclick={extendDraft}>{t('extend')}</Button>
						<Button type="submit" class="min-h-11 max-w-full whitespace-normal" disabled={!controller.editable || !!draftError || !!resumeError}
							ariaBusy={controller.saving}>{#if controller.saving}<LoadingState variant="control" label="" />{/if}{t(controller.saving ? 'saving' : 'save')}</Button>
					</div>
				</form>
			{/if}
		{:else if !controller.loading && !controller.error}
			<p class="text-sm leading-relaxed text-ink-2">{t('none')}</p>
		{/if}
	</div>
</section>

<style>
	.usage-schedule :global(.btn) {
		min-height: 2.75rem;
		max-width: 100%;
		white-space: normal;
	}
	.usage-schedule :global(.pill) {
		max-width: 100%;
		white-space: normal;
		font-size: 0.75rem;
	}
</style>
