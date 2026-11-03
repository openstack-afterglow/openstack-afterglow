<script lang="ts">
	import { untrack } from 'svelte';
	import type { AnnouncementAdmin } from '$lib/types/announcements';
	import { emailApi, mailDispatchFailure, type MailOperation } from '$lib/api/email';
	import { createEmailOwner } from '$lib/utils/emailOwner';
	import { auth, authReady, logoutInProgress, projectSwitching } from '$lib/stores/auth';
	import { t } from '$lib/i18n/ns/admin-email';
	import { Alert, Button } from '$lib/components/ui';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import MailOperationResult from './MailOperationResult.svelte';
	let { announcement, disabled = false, onbusy = (_busy: boolean) => {} }: { announcement: AnnouncementAdmin; disabled?: boolean; onbusy?: (busy: boolean) => void } = $props();
	let busy = $state(false), attempted = $state(''), error = $state(''), operation = $state<MailOperation | null>(null);
	let epoch = 0;
	function clear() { epoch++; busy = false; attempted = ''; error = ''; operation = null; onbusy(false); }
	const owner = createEmailOwner(clear);
	$effect(() => { const target = [announcement.id, announcement.updated_at]; untrack(() => { void target; clear(); }); });
	const blocked = $derived(disabled || busy || !!attempted || !announcement.is_active || (!!announcement.ends_at && new Date(announcement.ends_at).getTime() <= Date.now()) || !$auth.token || !$auth.isSystemAdmin || !$authReady || $logoutInProgress || $projectSwitching);
	async function send() {
		if (blocked) return;
		const scope = owner.capture(); if (!scope) return;
		const ticket = epoch, id = announcement.id;
		const current = () => scope.current() && ticket === epoch && announcement.id === id;
		busy = true; onbusy(true);
		const confirmed = await confirmDialog(`${announcement.title}\n\n${t('schedule')}`);
		if (!current()) return;
		if (!confirmed) { busy = false; onbusy(false); return; }
		attempted = crypto.randomUUID(); const operationId = attempted; error = '';
		try { const result = await emailApi.announcement(id, operationId, scope); if (current()) operation = result; }
		catch (e) {
			if (current()) {
				const failure = mailDispatchFailure(e);
				error = `${t(failure.message)}${failure.code ? ` (${failure.code})` : ''}`;
				if (failure.status === 'rejected') attempted = '';
			}
		}
		finally { if (current()) { busy = false; onbusy(false); } }
	}
</script>
<div class="min-w-0 space-y-2" data-announcement-email={announcement.id}>
	<Button variant="secondary" size="sm" disabled={blocked} ariaBusy={busy} onclick={send}>{t('sendAnnouncement')}</Button>
	{#if error}<Alert tone="warning">{error}</Alert>{/if}
	{#if operation}<details class="text-sm"><summary class="min-h-11 cursor-pointer text-ink-1">{t('history')}</summary><MailOperationResult {operation} /></details>{:else if attempted}<p class="text-xs font-mono [overflow-wrap:anywhere]">{t('operation', { id: attempted })}</p>{/if}
</div>
