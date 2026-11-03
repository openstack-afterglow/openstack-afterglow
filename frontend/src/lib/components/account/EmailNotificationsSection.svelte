<script lang="ts">
	import { emailApi, type MailPreferences } from '$lib/api/email';
	import { createEmailOwner } from '$lib/utils/emailOwner';
	import { auth, authReady, logoutInProgress, projectSwitching } from '$lib/stores/auth';
	import { t } from '$lib/i18n/ns/admin-email';
	import { Alert, Button, Card } from '$lib/components/ui';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	let value = $state<MailPreferences>({ announcements: true, resource_alerts: false });
	let loaded = $state(false), busy = $state(false), error = $state(''), saved = $state(false);
	const blocked = $derived(!loaded || busy || !$auth.token || !$authReady || $logoutInProgress || $projectSwitching);
	const owner = createEmailOwner(() => {
		value = { announcements: true, resource_alerts: false }; loaded = false; busy = false; error = ''; saved = false;
		void load();
	}, false);
	async function load() {
		const scope = owner.capture(); if (!scope || busy) return;
		busy = true; loaded = false; error = ''; saved = false;
		try { const result = await emailApi.preferences(scope); if (scope.current()) { value = result; loaded = true; } }
		catch { if (scope.current()) error = t('failed'); }
		finally { if (scope.current()) busy = false; }
	}
	async function save() {
		if (blocked) return;
		const scope = owner.capture(); if (!scope) return;
		busy = true; error = ''; saved = false;
		try { const result = await emailApi.savePreferences({ ...value }, scope); if (scope.current()) { value = result; saved = true; } }
		catch { if (scope.current()) { error = t('failed'); loaded = false; } }
		finally { if (scope.current()) busy = false; }
	}
</script>
<Card class="p-5 space-y-4">
	<h3 class="text-sm font-semibold text-ink-0">{t('preferences')}</h3>
	<p class="text-sm text-ink-2">{t('preferencesHelp')}</p>
	{#if busy}<LoadingState variant="inline" label={t('loading')} />{/if}
	{#if error}<Alert tone="danger">{error}</Alert>{/if}
	{#if saved}<Alert tone="success">{t('preferenceSaved')}</Alert>{/if}
	<label class="flex min-h-11 items-center gap-3 text-sm"><input id="email-preference-announcements" type="checkbox" bind:checked={value.announcements} disabled={blocked} />{t('announcements')}</label>
	<label class="flex min-h-11 items-center gap-3 text-sm"><input id="email-preference-resource-alerts" type="checkbox" bind:checked={value.resource_alerts} disabled={blocked} />{t('resourceAlerts')}</label>
	<div class="flex flex-wrap gap-3"><Button variant="secondary" disabled={blocked} onclick={save}>{t('save')}</Button><Button variant="secondary" disabled={busy || !$auth.token || !$authReady || $logoutInProgress || $projectSwitching} onclick={load}>{t('refresh')}</Button></div>
</Card>
