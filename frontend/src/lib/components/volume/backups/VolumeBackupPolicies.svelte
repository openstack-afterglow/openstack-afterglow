<script lang="ts">
	import { auth, canWrite, projectSwitching } from '$lib/stores/auth';
	import { t } from '$lib/i18n/ns/volume';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import { Alert, Button, Card, Pill } from '$lib/components/ui';
	import type { VolumeBackupPoliciesController } from '$lib/stores/volumeBackupPoliciesController.svelte';
	import VolumeBackupPolicyModal from './VolumeBackupPolicyModal.svelte';

	let { controller }: { controller: VolumeBackupPoliciesController } = $props();
	const days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'] as const;
	const mutationUnavailable = $derived(!$auth.projectId || !$auth.token || $projectSwitching || controller.loading || !!controller.error || controller.busy);
	const unavailable = $derived(mutationUnavailable || !!controller.volumesError);
	function date(value: string | null, fallback: 'autoPolicy.noNext' | 'autoPolicy.noRun', timezone: string) {
		if (!value) return t(fallback);
		const parsed = new Date(value);
		if (Number.isNaN(parsed.getTime())) return t('autoPolicy.invalidMetadata');
		try { return parsed.toLocaleString(intlLocale(), { timeZone: timezone, dateStyle: 'medium', timeStyle: 'long' }); }
		catch { return t('autoPolicy.invalidMetadata'); }
	}
</script>

<section aria-label={t('autoPolicy.title')} data-testid="auto-backup-policies" class="space-y-4">
	<Card>
		<div class="flex flex-wrap items-start justify-between gap-3">
			<div class="min-w-0 space-y-2"><h2 class="text-base font-semibold">{t('autoPolicy.title')}</h2><p class="text-sm text-ink-2">{t('autoPolicy.description')}</p></div>
			<Button variant="secondary" class="min-h-11 max-w-full" onclick={() => controller.open()} disabled={!$canWrite || unavailable}><span class="whitespace-normal">{t('autoPolicy.settings')}</span></Button>
		</div>
		{#if !$canWrite}<p class="mt-3 text-sm text-ink-2">{t('autoPolicy.reader')}</p>{/if}
	</Card>
	{#if controller.loading}<p role="status" class="text-sm text-ink-2">{t('autoPolicy.loading')}</p>{/if}
	{#if controller.error}<Alert tone="danger">{controller.error}</Alert>{/if}
	{#if controller.volumesError}<Alert tone="danger">{controller.volumesError}</Alert>{/if}
	{#if controller.error || controller.volumesError}<Button variant="secondary" class="min-h-11 max-w-full" onclick={controller.refresh} disabled={controller.loading}><span class="whitespace-normal">{t('autoPolicy.retry')}</span></Button>{/if}
	{#if controller.mutationError}<Alert tone="danger">{controller.mutationError}</Alert>{/if}
	{#if $auth.projectId && $auth.token && !$projectSwitching && !controller.loading && !controller.error && controller.policies.length === 0}<p class="text-sm text-ink-2">{t('autoPolicy.empty')}</p>{/if}
	{#each controller.policies as policy (policy.volume_id)}
		{@const name = controller.volumes.find((volume) => volume.id === policy.volume_id)?.name || policy.volume_id}
		{@const sourceUnavailable = policy.source_available === false || policy.source_available === null}
		<Card>
			<div class="flex flex-wrap items-center gap-3"><h3 class="min-w-0 break-all text-sm font-semibold">{name}</h3><Pill tone={policy.enabled ? 'success' : 'neutral'}>{t(policy.enabled ? 'autoPolicy.active' : 'autoPolicy.paused')}</Pill></div>
			<p class="mt-1 break-all font-mono text-xs text-ink-2">{policy.volume_id}</p>
			<p class="mt-3 text-sm">{t('autoPolicy.schedule', { time: policy.schedule_time, timezone: policy.timezone, day: t(`autoPolicy.${days[policy.weekly_day]}`), date: policy.monthly_day })}</p>
			<p class="mt-1 text-sm text-ink-2">{t('autoPolicy.retention', { daily: policy.max_daily, weekly: policy.max_weekly, monthly: policy.max_monthly })}</p>
			<dl class="mt-3 grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
				<div><dt class="text-ink-2">{t('autoPolicy.next')}</dt><dd>{date(policy.next_run_at, 'autoPolicy.noNext', policy.timezone)}{#if policy.next_tier} · {t(`autoPolicy.tier.${policy.next_tier}`)}{/if}</dd></div>
				<div><dt class="text-ink-2">{t('autoPolicy.last')}</dt><dd>{date(policy.last_run_at, 'autoPolicy.noRun', policy.timezone)}</dd></div>
				<div><dt class="text-ink-2">{t('autoPolicy.result')}</dt><dd>{t(`autoPolicy.status.${policy.last_status}`)}</dd></div>
				{#if policy.last_backup_id}<div class="min-w-0"><dt class="text-ink-2">{t('autoPolicy.backupId')}</dt><dd class="break-all font-mono text-xs">{policy.last_backup_id}</dd></div>{/if}
			</dl>
			{#if policy.last_error}<Alert tone="danger" class="mt-3">{policy.last_error}</Alert>{/if}
			{#if policy.source_error && policy.source_error !== policy.last_error}<Alert tone="danger" class="mt-3">{policy.source_error}</Alert>{/if}
			<p class="mt-3 text-sm text-ink-2">{t(policy.force ? 'autoPolicy.forceOn' : 'autoPolicy.forceOff')}</p>
			{#if policy.force}<Alert tone="warning" class="mt-3">{t('autoPolicy.forceRisk')}</Alert>{/if}
			<div class="mt-4 flex flex-wrap gap-2">
				<Button variant="secondary" size="sm" class="min-h-11 max-w-full" ariaLabel={t('autoPolicy.edit', { name })} onclick={() => controller.open(policy.volume_id)} disabled={!$canWrite || unavailable || sourceUnavailable}><span class="min-w-0 whitespace-normal break-all">{t('autoPolicy.edit', { name })}</span></Button>
				<Button variant="secondary" size="sm" class="min-h-11 max-w-full" ariaLabel={t(policy.enabled ? 'autoPolicy.pause' : 'autoPolicy.resume', { name })} onclick={() => controller.setEnabled(policy, !policy.enabled)} disabled={!$canWrite || unavailable || sourceUnavailable}><span class="min-w-0 whitespace-normal break-all">{t(policy.enabled ? 'autoPolicy.pause' : 'autoPolicy.resume', { name })}</span></Button>
				<Button variant="danger-outline" size="sm" class="min-h-11 max-w-full" ariaLabel={t('autoPolicy.remove', { name })} onclick={() => controller.remove(policy)} disabled={!$canWrite || mutationUnavailable}><span class="min-w-0 whitespace-normal break-all">{t('autoPolicy.remove', { name })}</span></Button>
			</div>
		</Card>
	{/each}
</section>
{#key controller.generation}
	{#if controller.editor !== null}
		<VolumeBackupPolicyModal volumes={controller.volumes} policies={controller.policies} initialVolumeId={controller.editor} resume={controller.resuming} onSave={controller.save} onclose={controller.close} />
	{/if}
{/key}
