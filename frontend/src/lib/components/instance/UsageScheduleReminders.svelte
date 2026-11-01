<script lang="ts">
	import { onMount } from 'svelte';
	import { get } from 'svelte/store';
	import { ApiError } from '$lib/api/client';
	import { loadUsageSchedules, type ScheduleError } from '$lib/api/usageSchedules';
	import { auth } from '$lib/stores/auth';
	import { authDisplayContext } from '$lib/stores/authDisplayContext';
	import { t } from '$lib/i18n/ns/usage-schedule';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import { Alert, Button, Card, SectionHeader } from '$lib/components/ui';
	import type { UsageScheduleInfo } from '$lib/types/instanceUsage';
	import { USAGE_STATES } from '$lib/types/instanceUsage';
	import { scheduleUrgency, validUsageSchedule } from '$lib/utils/instanceUsage';

	type Scope = { key: string; project: string | null; ready: boolean };

	let { class: className = '' }: { class?: string } = $props();
	let schedules = $state<UsageScheduleInfo[]>([]);
	let rowErrors = $state<ScheduleError[]>([]);
	let loading = $state(true);
	let loaded = $state(false);
	let error = $state('');
	let ready = $state(false);
	let now = $state(Date.now());
	let scope: Scope | null = null;
	let epoch = 0;
	let controller: AbortController | null = null;
	let disposed = false;
	const zone = Intl.DateTimeFormat().resolvedOptions().timeZone;
	const reminders = $derived(schedules.map(schedule => ({ schedule, urgency: scheduleUrgency(schedule, now) }))
		.filter(row => row.urgency !== null));

	function detailLink(id: string) {
		return `/dashboard/compute/instances/${encodeURIComponent(id)}#usage-schedule`;
	}
	function formatExpiry(value: string) {
		const date = new Date(value);
		if (!Number.isFinite(date.getTime())) return value;
		return new Intl.DateTimeFormat(intlLocale(), {
			year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit',
			hour12: false, timeZone: zone, timeZoneName: 'longOffset',
		}).format(date);
	}
	function stateLabel(state: UsageScheduleInfo['state']) {
		return USAGE_STATES.includes(state) ? t(`state.${state}`) : t('state.unknown');
	}
	async function refresh() {
		const owner = scope;
		if (!owner?.ready || controller || disposed) return;
		const requestEpoch = epoch;
		const request = new AbortController();
		controller = request;
		loading = true;
		error = '';
		try {
			const token = get(auth).token;
			if (!token || !owner.project) return;
			const result = await loadUsageSchedules(token, owner.project, request.signal);
			if (disposed || requestEpoch !== epoch) return;
			// Missing/invalid inventory is never a successful empty reminder list.
			if (!result || !Array.isArray(result.schedules) || !Array.isArray(result.errors)
				|| result.schedules.some(row => !row || typeof row.instance_id !== 'string' || !row.instance_id)
				|| result.errors.some(row => !row || typeof row.instance_id !== 'string' || !row.instance_id || typeof row.message !== 'string')) {
				throw new Error('Invalid usage schedule inventory');
			}
			schedules = result.schedules.filter(validUsageSchedule);
			rowErrors = [...result.errors, ...result.schedules.filter(row => !validUsageSchedule(row)).map(row => ({
				instance_id: row.instance_id, instance_name: row.instance_name || row.server_name, message: t('loadFailed'),
			}))];
			now = Date.now();
			loaded = true;
		} catch (cause) {
			if (!disposed && requestEpoch === epoch) error = cause instanceof ApiError ? cause.message : t('loadFailed');
		} finally {
			if (!disposed && requestEpoch === epoch) { loading = false; controller = null; }
		}
	}

	onMount(() => {
		// Store subscriptions invalidate synchronously, including same-tick A → B → A changes.
		const unsubscribe = authDisplayContext.subscribe(next => {
			if (next.key === scope?.key) return;
			epoch += 1;
			controller?.abort();
			controller = null;
			scope = next;
			ready = next.ready;
			schedules = []; rowErrors = []; error = ''; loading = true; loaded = false;
			void refresh();
		});
		const onFocus = () => { now = Date.now(); void refresh(); };
		window.addEventListener('focus', onFocus);
		const timer = window.setInterval(() => {
			now = Date.now();
			if (document.visibilityState === 'visible') void refresh();
		}, 60_000);
		return () => {
			disposed = true; epoch += 1; controller?.abort(); unsubscribe();
			window.removeEventListener('focus', onFocus);
			window.clearInterval(timer);
		};
	});
</script>

<Card padding="lg" class={className}>
	<section aria-label={t('reminders')} class="min-w-0 space-y-3">
		<SectionHeader title={t('reminders')}>
			{#snippet right()}
				<Button variant="outline" size="sm" class="min-h-11" disabled={!ready || loading} onclick={() => void refresh()}>{t('refresh')}</Button>
			{/snippet}
		</SectionHeader>
		{#if loading && !loaded}
			<LoadingState variant="section" label={t('loading')} />
		{/if}
		{#if error}
			<Alert tone="danger" title={t('loadFailed')}>
				{#if error !== t('loadFailed')}<p class="break-words">{error}</p>{/if}
			</Alert>
		{/if}
		{#if reminders.length > 0 || rowErrors.length > 0}
			<p class="text-xs text-ink-2">{t('timezone', { zone })}</p>
			<ul class="space-y-3">
				{#each rowErrors as row}
					<li>
						<Alert tone="danger" title={t('attention')}>
							<p class="font-medium break-words">{row.instance_name || row.instance_id}</p>
							<p class="text-xs break-all">{row.instance_id}</p>
							<p class="mt-1 break-words">{row.message}</p>
							<Button href={detailLink(row.instance_id)} variant="link" size="sm" class="mt-2 min-h-11 whitespace-normal text-left">{t('manage')}</Button>
						</Alert>
					</li>
				{/each}
				{#each reminders as { schedule, urgency }}
					<li>
						<Alert tone={urgency === 'expired' || urgency === 'attention' ? 'danger' : 'warning'} title={t(urgency!)}>
							<p class="font-medium break-words">{schedule.instance_name || schedule.server_name || schedule.instance_id}</p>
							<p class="text-xs break-all">{schedule.instance_id}</p>
							<p class="mt-1 tabular-nums break-words">{t('expires')}: <time datetime={schedule.expires_at} title={schedule.expires_at}>{formatExpiry(schedule.expires_at)}</time></p>
							<p class="break-words">{stateLabel(schedule.state)} · {t(schedule.expiry_action === 'delete' ? 'delete' : 'shelve')}</p>
							{#if schedule.last_error}<p class="mt-1 break-words">{schedule.last_error}</p>{/if}
							<Button href={detailLink(schedule.instance_id)} variant="link" size="sm" class="mt-2 min-h-11 whitespace-normal text-left">{t('manage')}</Button>
						</Alert>
					</li>
				{/each}
			</ul>
		{:else if loaded && !error}
			<p class="py-2 text-sm text-ink-2">{t('empty')}</p>
		{/if}
	</section>
</Card>
