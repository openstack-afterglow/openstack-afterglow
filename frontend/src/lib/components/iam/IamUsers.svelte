<script lang="ts">
	import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
	import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';
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
	function close() { open = false; editing = null; name = ''; email = ''; password = ''; enabled = true; }
	function edit(user: IamUser) {
		if (busy || blocked || loading || user.protected || user.domain_id !== session.domainId) return;
		editing = user; name = user.name; email = user.email; enabled = user.enabled; password = ''; error = ''; open = true;
	}
	async function save() {
		if (!live || !session.canSubmit() || blocked || busy || loading || !editing || editing.protected || editing.domain_id !== session.domainId || !form?.reportValidity()) return;
		const body = { name: name.trim(), email: email.trim(), enabled, ...(password ? { password } : {}) };
		password = ''; busy = true; error = ''; notice = '';
		try {
			await client.updateUser(editing.id, body);
			if (live) { close(); notice = t('saved'); await load(); }
		} catch (cause) { fail(cause); }
		finally { if (live) busy = false; }
	}
	onMount(() => { void load(); });
	onDestroy(() => { live = false; sequence++; password = ''; users = []; });
</script>

<div class="space-y-4">
	<div class="flex flex-wrap gap-2"><Button variant="secondary" disabled={blocked || loading || busy} onclick={load}>{t('refresh')}</Button></div>
	{#if loading}<ActivityIndicator label={t('loading')} />{/if}
	{#if error && !open}<Alert tone="danger">{error}</Alert>{/if}
	{#if notice}<Alert tone="success">{notice}</Alert>{/if}
	<ResponsiveTable>
		{#snippet cards()}
			{#each users as user (user.id)}<CompactResourceCard>
				<div class="flex flex-wrap justify-between gap-2"><h3 class="text-sm font-medium">{user.name}</h3><span class="text-xs">{user.enabled ? t('enabled') : t('disabled')}</span></div>
				<p class="text-sm break-all">{user.email || '—'}</p>
				{#if user.protected}<p class="text-xs text-ink-2">{t('protected')}</p>{/if}
				{#snippet details()}<p class="text-xs">{t('identityDomain')}: <code>{user.domain_id}</code></p>{#if user.domain_id !== session.domainId}<p class="text-xs text-ink-2">{t('foreignIdentity')}</p>{/if}{/snippet}
				{#snippet actions()}<Button variant="secondary" size="sm" disabled={blocked || loading || busy || user.protected || user.domain_id !== session.domainId} onclick={() => edit(user)}>{t('editUser')}</Button>{/snippet}
			</CompactResourceCard>{/each}
			{#if !loading && !error && !users.length}<p class="text-sm text-ink-2">{t('emptyUsers')}</p>{/if}
		{/snippet}
	<TableShell><table>
		<thead><tr><th>{t('name')}</th><th>{t('email')}</th><th>{t('identityDomain')}</th><th>{t('status')}</th><th>{t('actions')}</th></tr></thead>
		<tbody>
			{#each users as user (user.id)}<tr><td>{user.name}</td><td>{user.email || '—'}</td><td><code>{user.domain_id}</code>{#if user.domain_id !== session.domainId}<span class="block text-xs text-ink-2">{t('foreignIdentity')}</span>{/if}</td><td>{user.enabled ? t('enabled') : t('disabled')}{#if user.protected}<span class="block text-xs text-ink-2">{t('protected')}</span>{/if}</td><td><Button variant="secondary" size="sm" disabled={blocked || loading || busy || user.protected || user.domain_id !== session.domainId} onclick={() => edit(user)}>{t('editUser')}</Button></td></tr>{/each}
			{#if !loading && !error && !users.length}<tr><td colspan="5">{t('emptyUsers')}</td></tr>{/if}
		</tbody>
	</table></TableShell>
	</ResponsiveTable>
</div>
{#if open}
	<FormModal bind:open title={t('editUser')} submitting={busy} onClose={close} onSubmit={save} submitLabel={t('save')}>
		<form bind:this={form} class="space-y-4" onsubmit={(event) => { event.preventDefault(); void save(); }}>
			{#if error}<Alert tone="danger">{error}</Alert>{/if}
			<Field label={t('name')} for={`${uid}-name`} required><TextInput id={`${uid}-name`} bind:value={name} required disabled={busy} autocomplete="off" /></Field>
			<Field label={t('email')} for={`${uid}-email`} required><TextInput id={`${uid}-email`} type="email" bind:value={email} required disabled={busy} autocomplete="off" /></Field>
			<Field label={t('newPassword')} help={t('passwordHelp')} for={`${uid}-password`}><TextInput id={`${uid}-password`} type="password" bind:value={password} disabled={busy} autocomplete="new-password" /></Field>
			<label class="flex min-h-11 items-center gap-3 text-sm text-ink-1"><input type="checkbox" bind:checked={enabled} disabled={busy} />{t('enabled')}</label>
		</form>
		{#snippet actions()}
			<Button variant="secondary" disabled={busy} onclick={close}>{tc('actions.cancel')}</Button>
			<Button variant="primary" disabled={busy || blocked} onclick={save}>{t('save')}</Button>
		{/snippet}
	</FormModal>
{/if}
