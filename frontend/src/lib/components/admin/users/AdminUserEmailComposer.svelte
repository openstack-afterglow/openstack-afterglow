<script lang="ts">
	import { untrack } from 'svelte';
	import type { User } from '$lib/types/common';
	import { emailApi, mailDispatchFailure, type MailOperation } from '$lib/api/email';
	import { createEmailOwner } from '$lib/utils/emailOwner';
	import { auth, authReady, logoutInProgress, projectSwitching } from '$lib/stores/auth';
	import { t } from '$lib/i18n/ns/admin-email';
	import { Alert, Button, Field, TextInput, TextareaInput } from '$lib/components/ui';
	import MailOperationResult from '../MailOperationResult.svelte';
	let { user, domainId, disabled = false, onbusy = (_busy: boolean) => {} }: { user: User; domainId: string; disabled?: boolean; onbusy?: (busy: boolean) => void } = $props();
	let open = $state(false), subject = $state(''), body = $state(''), busy = $state(false), error = $state('');
	let operation = $state<MailOperation | null>(null), attemptedId = $state('');
	let epoch = 0;
	function clear() { epoch++; open = false; subject = ''; body = ''; busy = false; error = ''; operation = null; attemptedId = ''; onbusy(false); }
	const owner = createEmailOwner(clear);
	$effect(() => {
		const target = [user.id, user.domain_id, user.email, user.enabled, domainId];
		untrack(() => { void target; clear(); });
	});
	const available = $derived(!!user.email && !!user.enabled && user.domain_id === domainId && !!$auth.token && $auth.isSystemAdmin && $authReady && !$logoutInProgress && !$projectSwitching);
	async function send(event: SubmitEvent) {
		event.preventDefault(); if (!available || disabled || busy || attemptedId || !subject.trim() || !body.trim()) return;
		const scope = owner.capture(); if (!scope) return;
		const ticket = epoch, id = user.id, home = domainId, address = user.email;
		const current = () => scope.current() && ticket === epoch && user.id === id && domainId === home && user.email === address;
		attemptedId = crypto.randomUUID(); const operationId = attemptedId, sentSubject = subject.trim(), sentBody = body;
		busy = true; error = ''; onbusy(true);
		try {
			const result = await emailApi.message(operationId, [id], sentSubject, sentBody, scope);
			if (current()) { operation = result; subject = ''; body = ''; }
		} catch (e) {
			if (current()) {
				const failure = mailDispatchFailure(e);
				error = `${t(failure.message)}${failure.code ? ` (${failure.code})` : ''}`;
				if (failure.status === 'rejected') attemptedId = '';
			}
		}
		finally { if (current()) { busy = false; onbusy(false); } }
	}
</script>
<section class="mt-5 space-y-3 border-t border-line pt-4" aria-labelledby="admin-user-email-title" data-user-email-composer>
	<h3 id="admin-user-email-title" class="text-sm font-semibold text-ink-0">{t('compose')}</h3>
	<p class="text-sm text-ink-2">{t('registeredHelp')}</p>
	<p class="text-sm text-ink-1 [overflow-wrap:anywhere]">{user.name} · {user.email ?? '—'}</p>
	<p class="text-xs font-mono text-ink-2 [overflow-wrap:anywhere]">{user.id}</p>
	{#if !available}<p class="text-sm text-ink-2">{t('noMailbox')}</p>{/if}
	{#if !open}<Button variant="secondary" disabled={!available || disabled} onclick={() => { open = true; }}>{t('compose')}</Button>
	{:else}
		<form onsubmit={send} class="space-y-3">
			<Field label={t('subject')} for="user-email-subject"><TextInput id="user-email-subject" bind:value={subject} maxlength={200} required disabled={!available || disabled || busy || !!attemptedId} /></Field>
			<Field label={t('body')} for="user-email-body"><TextareaInput id="user-email-body" bind:value={body} maxlength={10000} rows={5} required disabled={!available || disabled || busy || !!attemptedId} /></Field>
			<Button variant="primary" type="submit" disabled={!available || disabled || busy || !!attemptedId} ariaBusy={busy}>{t('send')}</Button>
		</form>
	{/if}
	{#if error}<Alert tone="warning">{error}</Alert>{/if}
	{#if operation}<MailOperationResult {operation} />{:else if attemptedId}<p class="text-sm font-mono [overflow-wrap:anywhere]">{t('operation', { id: attemptedId })}</p>{/if}
</section>
