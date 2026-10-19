<script lang="ts">
	import { onMount, onDestroy, untrack } from 'svelte';
	import { ApiError } from '$lib/api/client';
	import { domainIam, type IamSession, type IamUser } from '$lib/api/domainIam';
	import { t } from '$lib/i18n/ns/domain-iam';
	import { iamErrorMessage } from './iamError';
	import { t as tc } from '$lib/i18n/ns/common';
	import Button from '$lib/components/ui/Button.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import FormModal from '$lib/components/ui/FormModal.svelte';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import TableShell from '$lib/components/ui/TableShell.svelte';
	let { session, blocked = false, onDenied }: { session: IamSession; blocked?: boolean; onDenied: () => void } = $props();
	const client = untrack(() => domainIam(session));
	let live = true;
	let sequence = 0;
	let users = $state<IamUser[]>([]);
	let loading = $state(true);
	let error = $state('');
	let notice = $state('');
	let open = $state(false);
	let editing = $state<IamUser | null>(null);
	let name = $state('');
	let email = $state('');
	let personalDomain = $state('');
	let enabled = $state(true);
	let password = $state('');
	let busy = $state(false);
	let form = $state<HTMLFormElement>();
	const uid = $props.id();
	function fail(cause: unknown) {
		if (!live) return;
		error = iamErrorMessage(cause, t('saveFailed'));
		if (cause instanceof ApiError && cause.status === 403) onDenied();
	}
	async function load() {
		const pending = ++sequence; loading = true; error = '';
		try { const result = await client.users(); if (live && pending === sequence) users = result.items; }
		catch (cause) { if (pending === sequence) fail(cause); }
		finally { if (live && pending === sequence) loading = false; }
	}
	function close() { open = false; editing = null; name = ''; email = ''; personalDomain = ''; password = ''; enabled = true; }
	function edit(user: IamUser | null) {
		if (busy || blocked || loading || user?.protected || (user && user.domain_id !== session.domainId)) return;
		editing = user; name = user?.name ?? ''; email = user?.email ?? ''; personalDomain = ''; enabled = user?.enabled ?? true; password = ''; error = ''; open = true;
	}
	async function save() {
		if (!live || !session.canSubmit() || blocked || busy || loading || editing?.protected || (editing && editing.domain_id !== session.domainId) || !form?.reportValidity() || (!editing && !personalDomain.trim())) return;
		const body = { name: name.trim(), email: email.trim(), enabled, ...(password ? { password } : {}), ...(!editing ? { personal_domain_name: personalDomain.trim() } : {}) };
		password = ''; busy = true; error = ''; notice = '';
		try {
			if (editing) await client.updateUser(editing.id, body); else await client.createUser(body);
			if (live) { close(); notice = t('saved'); await load(); }
		} catch (cause) { fail(cause); }
		finally { if (live) busy = false; }
	}
	onMount(() => { void load(); });
	onDestroy(() => { live = false; sequence++; password = ''; users = []; });
</script>

<div class="space-y-4">
	<div class="flex flex-wrap gap-2"><Button variant="primary" disabled={blocked || loading || busy} onclick={() => edit(null)}>{t('createUser')}</Button><Button variant="secondary" disabled={blocked || loading || busy} onclick={load}>{t('refresh')}</Button></div>
	{#if loading}<ActivityIndicator label={t('loading')} />{/if}
	{#if error && !open}<Alert tone="danger">{error}</Alert>{/if}
	{#if notice}<Alert tone="success">{notice}</Alert>{/if}
	<TableShell><table>
		<thead><tr><th>{t('name')}</th><th>{t('email')}</th><th>{t('identityDomain')}</th><th>{t('status')}</th><th>{t('actions')}</th></tr></thead>
		<tbody>
			{#each users as user (user.id)}<tr><td>{user.name}</td><td>{user.email || '—'}</td><td><code>{user.domain_id}</code>{#if user.domain_id !== session.domainId}<span class="block text-xs text-ink-2">{t('foreignIdentity')}</span>{/if}</td><td>{user.enabled ? t('enabled') : t('disabled')}{#if user.protected}<span class="block text-xs text-ink-2">{t('protected')}</span>{/if}</td><td><Button variant="secondary" size="sm" disabled={blocked || loading || busy || user.protected || user.domain_id !== session.domainId} onclick={() => edit(user)}>{t('editUser')}</Button></td></tr>{/each}
			{#if !loading && !error && !users.length}<tr><td colspan="5">{t('emptyUsers')}</td></tr>{/if}
		</tbody>
	</table></TableShell>
</div>
{#if open}
	<FormModal bind:open title={editing ? t('editUser') : t('createUser')} submitting={busy} onClose={close} onSubmit={save} submitLabel={t('save')}>
		<form bind:this={form} class="space-y-4" onsubmit={(event) => { event.preventDefault(); void save(); }}>
			{#if error}<Alert tone="danger">{error}</Alert>{/if}
			<Field label={t('name')} for={`${uid}-name`} required><TextInput id={`${uid}-name`} bind:value={name} required disabled={busy} autocomplete="off" /></Field>
			<Field label={t('email')} for={`${uid}-email`} required><TextInput id={`${uid}-email`} type="email" bind:value={email} required disabled={busy} autocomplete="off" /></Field>
			{#if !editing}<Field label={t('personalDomainName')} help={t('personalDomainHelp')} for={`${uid}-domain`} required><TextInput id={`${uid}-domain`} bind:value={personalDomain} maxlength={64} required disabled={busy} autocomplete="off" /></Field>{/if}
			<Field label={editing ? t('newPassword') : t('password')} help={t('passwordHelp')} for={`${uid}-password`} required={!editing}><TextInput id={`${uid}-password`} type="password" bind:value={password} required={!editing} disabled={busy} autocomplete="new-password" /></Field>
			<label class="flex min-h-11 items-center gap-3 text-sm text-ink-1"><input type="checkbox" bind:checked={enabled} disabled={busy} />{t('enabled')}</label>
		</form>
		{#snippet actions()}
			<Button variant="secondary" disabled={busy} onclick={close}>{tc('actions.cancel')}</Button>
			<Button variant="primary" disabled={busy || blocked} onclick={save}>{t('save')}</Button>
		{/snippet}
	</FormModal>
{/if}
