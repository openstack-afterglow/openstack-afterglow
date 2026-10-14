<script lang="ts">
	import { onDestroy, untrack } from 'svelte';
	import { auth, canWrite } from '$lib/stores/auth';
	import { t } from '$lib/i18n/ns/volume';
	import { Alert, Button, Field, FormModal, SelectInput, TextInput } from '$lib/components/ui';
	import type { Volume } from '$lib/types/volume';
	import type { VolumeBackupPolicy, VolumeBackupPolicyInput } from '$lib/types/volumeBackupPolicy';
	import { policyInput } from '$lib/types/volumeBackupPolicy';

	let { volumes, policies, initialVolumeId = '', resume = false, onSave, onclose }: {
		volumes: Volume[];
		policies: VolumeBackupPolicy[];
		initialVolumeId?: string;
		resume?: boolean;
		onSave: (volumeId: string, input: VolumeBackupPolicyInput) => Promise<true | string>;
		onclose: () => void;
	} = $props();

	function defaults(): VolumeBackupPolicyInput {
		let timezone = 'UTC';
		try { timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'; } catch { /* UTC is a valid explicit fallback. */ }
		return { max_daily: 2, max_weekly: 2, max_monthly: 1, enabled: true, schedule_time: '03:00', timezone, weekly_day: 0, monthly_day: 1, force: false };
	}
	function loadSource(id: string) {
		const saved = policies.find((policy) => policy.volume_id === id && policy.project_id === $auth.projectId);
		return saved ? policyInput(saved) : defaults();
	}

	let source = $state(untrack(() => initialVolumeId));
	let form = $state(untrack(() => { const input = loadSource(initialVolumeId); return resume ? { ...input, enabled: true } : input; }));
	let daily = $state(untrack(() => String(form.max_daily)));
	let weekly = $state(untrack(() => String(form.max_weekly)));
	let monthly = $state(untrack(() => String(form.max_monthly)));
	let weeklyDay = $state(untrack(() => String(form.weekly_day)));
	let monthlyDay = $state(untrack(() => String(form.monthly_day)));
	let saving = $state(false);
	let error = $state('');
	let session = 0;
	const componentId = $props.id();
	onDestroy(() => { session++; });
	const days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'] as const;
	const selectedVolume = $derived(volumes.find((volume) => volume.id === source));
	const forceRequired = $derived(form.enabled && selectedVolume?.status === 'in-use');
	const ready = $derived($canWrite && !!selectedVolume && !saving && (!forceRequired || form.force));

	function changeSource() {
		session++;
		form = loadSource(source);
		daily = String(form.max_daily); weekly = String(form.max_weekly); monthly = String(form.max_monthly);
		weeklyDay = String(form.weekly_day); monthlyDay = String(form.monthly_day);
		error = '';
	}
	function close() { session++; onclose(); }

	async function submit() {
		if (!ready) return;
		const counts = [daily, weekly, monthly];
		const input: VolumeBackupPolicyInput = { ...form, max_daily: Number(daily), max_weekly: Number(weekly), max_monthly: Number(monthly), weekly_day: Number(weeklyDay), monthly_day: Number(monthlyDay) };
		let validZone = false;
		try { new Intl.DateTimeFormat('en', { timeZone: input.timezone }).format(); validZone = true; } catch { /* Invalid IANA input is reported with the other form errors. */ }
		if (!counts.every((value) => /^\d+$/.test(value) && Number(value) <= 30)
			|| !/^([01]\d|2[0-3]):[0-5]\d$/.test(input.schedule_time) || !validZone
			|| !Number.isInteger(input.weekly_day) || input.weekly_day < 0 || input.weekly_day > 6
			|| !/^\d+$/.test(monthlyDay) || input.monthly_day < 1 || input.monthly_day > 28
			|| (input.enabled && !counts.some((value) => Number(value) > 0))) {
			error = t('autoPolicy.invalid'); return;
		}
		const request = ++session;
		saving = true; error = '';
		try {
			const result = await onSave(source, input);
			if (request !== session) return;
			if (result === true) close(); else error = result;
		} finally { if (request === session) saving = false; }
	}
</script>

<form onsubmit={(event) => { event.preventDefault(); void submit(); }} aria-label={t('autoPolicy.settings')}>
<FormModal open={true} title={t('autoPolicy.settings')} onClose={close} submitting={saving}>
	<div class="space-y-4" data-testid="auto-backup-policy-editor">
		{#if !$canWrite}<Alert tone="info">{t('autoPolicy.reader')}</Alert>{/if}
		<Field label={t('autoPolicy.source')} for={`${componentId}-source`}>
			<SelectInput id={`${componentId}-source`} bind:value={source} onchange={changeSource} disabled={saving || !$canWrite}>
				<option value="">{t('autoPolicy.chooseSource')}</option>
				{#each volumes as volume}<option value={volume.id}>{volume.name || volume.id} · {volume.id}</option>{/each}
			</SelectInput>
		</Field>
		<Field label={t('autoPolicy.time')} for={`${componentId}-time`}><TextInput id={`${componentId}-time`} bind:value={form.schedule_time} placeholder="03:00" disabled={saving || !$canWrite} /></Field>
		<Field label={t('autoPolicy.timezone')} for={`${componentId}-zone`} help={t('autoPolicy.timezoneHelp')}><TextInput id={`${componentId}-zone`} bind:value={form.timezone} placeholder="Asia/Seoul" disabled={saving || !$canWrite} /></Field>
		<div class="grid grid-cols-1 gap-4 sm:grid-cols-3">
			<Field label={t('autoPolicy.daily')} for={`${componentId}-daily`}><TextInput id={`${componentId}-daily`} bind:value={daily} inputmode="numeric" disabled={saving || !$canWrite} /></Field>
			<Field label={t('autoPolicy.weekly')} for={`${componentId}-weekly`}><TextInput id={`${componentId}-weekly`} bind:value={weekly} inputmode="numeric" disabled={saving || !$canWrite} /></Field>
			<Field label={t('autoPolicy.monthly')} for={`${componentId}-monthly`}><TextInput id={`${componentId}-monthly`} bind:value={monthly} inputmode="numeric" disabled={saving || !$canWrite} /></Field>
		</div>
		<Field label={t('autoPolicy.weeklyDay')} for={`${componentId}-weekday`}>
			<SelectInput id={`${componentId}-weekday`} bind:value={weeklyDay} disabled={saving || !$canWrite}>{#each days as day, index}<option value={String(index)}>{t(`autoPolicy.${day}`)}</option>{/each}</SelectInput>
		</Field>
		<Field label={t('autoPolicy.monthlyDay')} for={`${componentId}-monthday`}><TextInput id={`${componentId}-monthday`} bind:value={monthlyDay} inputmode="numeric" disabled={saving || !$canWrite} /></Field>
		<p class="text-xs text-ink-2">{t('autoPolicy.calendarHelp')}</p>
		<label class="flex min-h-11 items-center gap-3 text-sm text-ink-1"><input type="checkbox" bind:checked={form.enabled} disabled={saving || !$canWrite} /><span>{t('autoPolicy.enabled')}</span></label>
		<Alert tone="warning"><p id={`${componentId}-risk`}>{t('autoPolicy.forceRisk')}</p><p id={`${componentId}-scope`} class="mt-2">{t('autoPolicy.forceScope')}</p></Alert>
		<label class="flex min-h-11 items-center gap-3 text-sm text-ink-1"><input type="checkbox" bind:checked={form.force} disabled={saving || !$canWrite} aria-describedby={`${componentId}-risk ${componentId}-scope`} /><span>{t('autoPolicy.force')}</span></label>
		{#if error}<Alert tone="danger">{error}</Alert>{/if}
	</div>
	{#snippet actions()}
		<div class="flex w-full flex-wrap justify-end gap-3">
			<Button variant="secondary" class="min-h-11 max-w-full" onclick={close} disabled={saving}><span class="whitespace-normal">{t('autoPolicy.cancel')}</span></Button>
			<Button variant="primary" type="submit" class="min-h-11 max-w-full" disabled={!ready} ariaBusy={saving}><span class="whitespace-normal">{t('autoPolicy.save')}</span></Button>
		</div>
	{/snippet}
</FormModal>
</form>
