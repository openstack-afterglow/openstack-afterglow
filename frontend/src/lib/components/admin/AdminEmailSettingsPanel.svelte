<script lang="ts">
	import { emailApi, mailError, mailDispatchFailure, secretUpdate, type MailSettings, type MailSettingsUpdate, type MailOperation, type MailConnectionCheck, type SecretAction } from '$lib/api/email';
	import { createEmailOwner } from '$lib/utils/emailOwner';
	import { auth, authReady, logoutInProgress, projectSwitching } from '$lib/stores/auth';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { t } from '$lib/i18n/ns/admin-email';
	import { Alert, Button, Card, Field, TextInput, SelectInput } from '$lib/components/ui';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import MailDeliveryHistory from './MailDeliveryHistory.svelte';
	import MailOperationResult from './MailOperationResult.svelte';
	let saved = $state<MailSettings | null>(null);
	let draft = $state<MailSettings | null>(null);
	let passwords = $state({ smtp: '', imap: '' });
	let actions = $state<Record<'smtp' | 'imap', SecretAction>>({ smtp: 'keep', imap: 'keep' });
	let reconfirm = $state({ smtp: false, imap: false });
	let busy = $state(false), receiptBusy = $state(false), loading = $state(false), uncertain = $state(false);
	let error = $state(''), notice = $state(''), checkError = $state(''), testError = $state('');
	let check = $state<MailConnectionCheck | null>(null);
	let operation = $state<MailOperation | null>(null), attemptedOperation = $state('');
	let recipient = $state('');
	const transports = ['smtp', 'imap'] as const;
	const blocked = $derived(busy || receiptBusy || loading || !$authReady || !$auth.token || !$auth.isSystemAdmin || $logoutInProgress || $projectSwitching);
	const owner = createEmailOwner(() => {
		saved = null; draft = null; clearSecrets(); busy = false; loading = false; receiptBusy = false; uncertain = false;
		error = ''; notice = ''; checkError = ''; testError = ''; check = null; operation = null; attemptedOperation = ''; recipient = '';
		void load();
	});
	function clearSecrets() { passwords = { smtp: '', imap: '' }; actions = { smtp: 'keep', imap: 'keep' }; reconfirm = { smtp: false, imap: false }; }
	function apply(result: MailSettings) { saved = result; draft = structuredClone(result); clearSecrets(); uncertain = false; }
	async function load() {
		const scope = owner.capture(); if (!scope || loading || busy || receiptBusy) return;
		loading = true; error = ''; notice = ''; clearSecrets();
		try { const result = await emailApi.settings(scope); if (scope.current()) apply(result); }
		catch { if (scope.current()) { error = t('failed'); uncertain = true; } }
		finally { if (scope.current()) loading = false; }
	}
	async function save(event: SubmitEvent) {
		event.preventDefault(); if (blocked || uncertain || !draft || !saved) return;
		const scope = owner.capture(); if (!scope) return;
		const { password_configured: _smtpSecret, ...smtp } = draft.smtp;
		const { password_configured: _imapSecret, ...imap } = draft.imap;
		const payload: MailSettingsUpdate = { revision: saved.revision,
			smtp: { ...smtp, ...secretUpdate(actions.smtp, passwords.smtp, reconfirm.smtp) },
			imap: { ...imap, ...secretUpdate(actions.imap, passwords.imap, reconfirm.imap) },
			notifications: { ...draft.notifications } };
		clearSecrets(); busy = true; error = ''; notice = '';
		try { const result = await emailApi.save(payload, scope); if (scope.current()) { apply(result); notice = t('saved'); } }
		catch (e) { if (scope.current()) { error = t(mailError(e)); uncertain = true; } }
		finally { if (scope.current()) busy = false; }
	}
	async function reset() {
		if (blocked || uncertain || !saved) return;
		const scope = owner.capture(); if (!scope) return;
		const revision = saved.revision;
		busy = true;
		const confirmed = await confirmDialog(t('resetConfirm'));
		if (!scope.current()) return;
		if (!confirmed) { busy = false; return; }
		clearSecrets(); error = ''; notice = '';
		try { const result = await emailApi.reset(revision, scope); if (scope.current()) { apply(result); notice = t('saved'); } }
		catch (e) { if (scope.current()) { error = t(mailError(e)); uncertain = true; } }
		finally { if (scope.current()) busy = false; }
	}
	async function connections() {
		if (blocked || !saved) return;
		const scope = owner.capture(); if (!scope) return;
		clearSecrets(); busy = true; check = null; checkError = '';
		try { const result = await emailApi.check(scope); if (scope.current()) check = result; }
		catch { if (scope.current()) checkError = t('failed'); }
		finally { if (scope.current()) busy = false; }
	}
	async function sendTest(event: SubmitEvent) {
		event.preventDefault(); if (blocked || !saved || attemptedOperation || !recipient.trim()) return;
		const scope = owner.capture(); if (!scope) return;
		attemptedOperation = crypto.randomUUID(); const id = attemptedOperation, target = recipient.trim();
		clearSecrets(); busy = true; testError = ''; operation = null;
		try { const result = await emailApi.test(id, target, scope); if (scope.current()) operation = result; }
		catch (e) {
			if (scope.current()) {
				const failure = mailDispatchFailure(e);
				testError = `${t(failure.message)}${failure.code ? ` (${failure.code})` : ''}`;
				if (failure.status === 'rejected') attemptedOperation = '';
			}
		}
		finally { if (scope.current()) busy = false; }
	}
</script>

<div class="space-y-4" data-admin-email-settings>
	<Card padding="lg" class="space-y-4">
		<div class="flex flex-wrap items-start justify-between gap-3">
			<div><h2 class="text-base font-semibold text-ink-0">{t('title')}</h2><p class="mt-2 max-w-prose text-sm text-ink-2">{t('help')}</p></div>
			<Button variant="secondary" disabled={blocked} onclick={load}>{t('refresh')}</Button>
		</div>
		{#if error}<Alert tone="danger">{error}</Alert>{/if}
		{#if notice}<Alert tone="success">{notice}</Alert>{/if}
		{#if loading}<LoadingState variant="section" label={t('loading')} />{/if}
		{#if saved && draft}
			<p class="text-sm text-ink-2">{saved.source === 'runtime' ? t('sourceRuntime') : t('sourceConfig')} · {t('revision', { revision: saved.revision })}</p>
			<form onsubmit={save} class="space-y-5">
				<fieldset disabled={blocked || uncertain} class="min-w-0 space-y-5">
					<div class="grid min-w-0 grid-cols-1 gap-6 lg:grid-cols-2">
						{#each transports as transport}
							<section class="min-w-0 space-y-3" aria-labelledby={`email-${transport}-title`}>
								<h3 id={`email-${transport}-title`} class="text-sm font-semibold text-ink-0">{transport.toUpperCase()}</h3>
								<label class="flex min-h-11 items-center gap-3 text-sm"><input id={`email-${transport}-enabled`} type="checkbox" bind:checked={draft[transport].enabled} />{t('enabled')}</label>
								<Field label={t('host')} for={`email-${transport}-host`}><TextInput id={`email-${transport}-host`} bind:value={draft[transport].host} required={draft[transport].enabled} maxlength={253} autocomplete="off" /></Field>
								<div class="grid grid-cols-2 gap-3">
									<Field label={t('port')} for={`email-${transport}-port`}><input class="mail-number" id={`email-${transport}-port`} type="number" min="1" max="65535" step="1" required bind:value={draft[transport].port} /></Field>
									<Field label={t('timeout')} for={`email-${transport}-timeout`}><input class="mail-number" id={`email-${transport}-timeout`} type="number" min="1" max="30" step="1" required bind:value={draft[transport].timeout_seconds} /></Field>
								</div>
								<Field label={t('security')} for={`email-${transport}-security`}><SelectInput id={`email-${transport}-security`} bind:value={draft[transport].security}><option value="starttls">STARTTLS</option><option value="tls">TLS</option>{#if draft[transport].security === 'none'}<option value="none" disabled>none</option>{/if}</SelectInput></Field>
								<Field label={t('username')} for={`email-${transport}-username`}><TextInput id={`email-${transport}-username`} bind:value={draft[transport].username} maxlength={320} autocomplete="off" /></Field>
								<Field label={t('password')} for={`email-${transport}-secret-action`} help={saved[transport].password_configured ? t('configured') : t('notConfigured')}>
									<SelectInput id={`email-${transport}-secret-action`} bind:value={actions[transport]} onchange={() => { passwords[transport] = ''; reconfirm[transport] = false; }}><option value="keep">{t('keep')}</option><option value="replace">{t('replace')}</option><option value="clear">{t('clear')}</option></SelectInput>
								</Field>
								{#if actions[transport] === 'replace'}<Field label={t('replace')} for={`email-${transport}-password`}><TextInput id={`email-${transport}-password`} type="password" bind:value={passwords[transport]} required maxlength={4096} autocomplete="new-password" /></Field>{/if}
								{#if actions[transport] === 'keep' && saved[transport].password_configured}<label class="flex min-h-11 items-start gap-3 text-sm text-ink-1"><input class="mt-1" type="checkbox" bind:checked={reconfirm[transport]} />{t('reconfirm')}</label>{/if}
								{#if transport === 'smtp'}
									<Field label={t('fromAddress')} for="email-smtp-from-address"><TextInput id="email-smtp-from-address" type="email" bind:value={draft.smtp.from_address} required={draft.smtp.enabled} maxlength={320} /></Field>
									<Field label={t('fromName')} for="email-smtp-from-name"><TextInput id="email-smtp-from-name" bind:value={draft.smtp.from_name} maxlength={200} /></Field>
								{:else}<Field label={t('mailbox')} for="email-imap-mailbox"><TextInput id="email-imap-mailbox" bind:value={draft.imap.mailbox} required={draft.imap.enabled} maxlength={255} /></Field>{/if}
							</section>
						{/each}
					</div>
					<p class="text-sm text-ink-2">{t('secureHelp')}</p>
					<div class="space-y-2 border-t border-line pt-4">
						<p class="max-w-prose text-sm text-ink-2">{t('globalHelp')}</p>
						<label class="flex min-h-11 items-center gap-3 text-sm"><input type="checkbox" bind:checked={draft.notifications.announcements_enabled} />{t('announcements')}</label>
						<label class="flex min-h-11 items-center gap-3 text-sm"><input type="checkbox" bind:checked={draft.notifications.resource_alerts_enabled} />{t('resourceAlerts')}</label>
					</div>
				</fieldset>
				<div class="flex flex-wrap gap-3"><Button type="submit" variant="primary" disabled={blocked || uncertain || draft.smtp.security === 'none' || draft.imap.security === 'none'} ariaBusy={busy}>{t('save')}</Button><Button variant="secondary" disabled={blocked || uncertain} onclick={reset}>{t('reset')}</Button></div>
			</form>
		{/if}
	</Card>
	<Card padding="lg" class="space-y-4">
		<h2 class="text-base font-semibold text-ink-0">{t('check')}</h2>
		<p class="text-sm text-ink-2">{t('checkHelp')}</p>
		<Button variant="secondary" disabled={blocked || !saved} onclick={connections}>{t('check')}</Button>
		{#if checkError}<Alert tone="danger">{checkError}</Alert>{/if}
		{#if check}<p class="text-sm text-ink-2">{t('checkRevision', { revision: check.revision })}</p><dl class="space-y-2 text-sm">{#each transports as transport}<div class="flex flex-wrap gap-3"><dt>{transport.toUpperCase()}</dt><dd>{t(`status.${check[transport].status}`)}</dd></div>{/each}</dl>{/if}
	</Card>
	<Card padding="lg" class="space-y-4">
		<h2 class="text-base font-semibold text-ink-0">{t('test')}</h2>
		<p class="text-sm text-ink-2">{t('proof')}</p>
		<form onsubmit={sendTest} class="space-y-3">
			<Field label={t('recipient')} for="email-test-recipient"><TextInput id="email-test-recipient" type="email" bind:value={recipient} required maxlength={320} disabled={blocked || !!attemptedOperation} /></Field>
			<Button type="submit" variant="secondary" disabled={blocked || !saved || !!attemptedOperation} ariaBusy={busy}>{t('sendTest')}</Button>
		</form>
		{#if testError}<Alert tone="warning">{testError}</Alert>{/if}
		{#if operation}<MailOperationResult {operation} />{:else if attemptedOperation}<p class="text-sm font-mono [overflow-wrap:anywhere]">{t('operation', { id: attemptedOperation })}</p>{/if}
		{#if operation}<Button variant="secondary" disabled={blocked} onclick={() => { attemptedOperation = ''; operation = null; testError = ''; recipient = ''; }}>{t('newTest')}</Button>{/if}
	</Card>
	<MailDeliveryHistory disabled={busy || loading} onbusy={(value) => { receiptBusy = value; }} />
</div>

<style>
	.mail-number { width: 100%; min-height: var(--control-height); border: 1px solid var(--color-line-2); border-radius: var(--radius-md); padding: 0.375rem 0.75rem; background: var(--color-surface-input); color: var(--color-ink-0); font-size: var(--type-body); }
	.mail-number:focus-visible { outline: none; box-shadow: var(--focus-ring); }
	.mail-number:disabled { background: var(--color-surface-input-disabled); color: var(--color-ink-2); }
	@media (max-width: 767px), (pointer: coarse) { .mail-number { min-height: var(--control-touch-height); } }
</style>
