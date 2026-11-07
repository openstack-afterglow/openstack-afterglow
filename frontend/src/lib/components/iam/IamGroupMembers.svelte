<script lang="ts">
	import { onMount, onDestroy, untrack } from 'svelte';
	import { domainIam, type IamGroup, type IamGroupMember, type IamSession, type IamUser } from '$lib/api/domainIam';
	import { t } from '$lib/i18n/ns/domain-iam-groups';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { groupAuthorityLost, groupErrorMessage } from './groupError';
	import Button from '$lib/components/ui/Button.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Pill from '$lib/components/ui/Pill.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import SelectInput from '$lib/components/ui/SelectInput.svelte';
	import TableShell from '$lib/components/ui/TableShell.svelte';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';

	let { session, group, blocked = false, onDenied, onChanged }: { session: IamSession; group: IamGroup; blocked?: boolean; onDenied: () => void; onChanged: () => void } = $props();
	const client = untrack(() => domainIam(session));
	const uid = $props.id();
	let live = true;
	let revision = 0;
	let members = $state<IamGroupMember[]>([]);
	let users = $state<IamUser[]>([]);
	let selected = $state('');
	let loading = $state(true);
	let busy = $state(false);
	let error = $state('');
	// Candidates are the fresh domain directory; the server rechecks joined/enabled/privileged state.
	const candidates = $derived(users.filter(user => user.enabled && !members.some(member => member.id === user.id)));
	const disabled = $derived(blocked || busy || loading || group.protected || !session.canSubmit());

	function fail(cause: unknown, fallback: string) {
		if (!live || !session.isCurrent()) return;
		if (groupAuthorityLost(cause)) onDenied();
		error = groupErrorMessage(cause, fallback);
	}
	async function load() {
		const pending = ++revision;
		loading = true; error = '';
		try {
			const [rows, directory] = await Promise.all([client.groupMembers(group.id), client.users()]);
			if (!live || !session.isCurrent() || pending !== revision) return;
			members = rows.items; users = directory.items;
			if (!candidates.some(user => user.id === selected)) selected = '';
		} catch (cause) { if (pending === revision) fail(cause, t('loadFailed')); }
		finally { if (live && pending === revision) loading = false; }
	}
	async function change(send: () => Promise<unknown>) {
		busy = true; error = '';
		try {
			await send();
			if (!live || !session.isCurrent()) return;
			selected = '';
			onChanged();
			await load();
		} catch (cause) { fail(cause, t('errorSaveFailed')); }
		finally { if (live) busy = false; }
	}
	async function add() {
		const user = selected;
		if (user) await change(() => client.addGroupMember(group.id, user));
	}
	async function remove(member: IamGroupMember) {
		if (!await confirmDialog(t('removeConfirm', { user: member.name, group: group.name }), { confirmLabel: t('remove') })) return;
		if (live && session.isCurrent()) await change(() => client.removeGroupMember(group.id, member.id));
	}
	onMount(() => { void load(); });
	onDestroy(() => { live = false; revision++; members = []; users = []; });
</script>

<div class="space-y-4">
	{#if group.protected}<Alert tone="warning">{t('protectedHelp')}</Alert>{/if}
	<p class="text-xs text-ink-2">{t('roleNote')}</p>
	{#if !group.protected}
		<div class="flex flex-wrap items-end gap-2">
			<Field class="min-w-60 flex-1" label={t('user')} for="{uid}-user">
				<SelectInput id="{uid}-user" bind:value={selected} disabled={disabled || !candidates.length}>
					<option value="">{candidates.length ? t('selectUser') : t('noCandidates')}</option>
					{#each candidates as user (user.id)}<option value={user.id}>{user.name}{user.email ? ` (${user.email})` : ''}</option>{/each}
				</SelectInput>
			</Field>
			<Button variant="accent" disabled={disabled || !selected} ariaBusy={busy} onclick={add}>{t('add')}</Button>
		</div>
	{/if}
	{#if loading}<LoadingState variant={members.length ? 'inline' : 'surface'} label={t('loading')} />{/if}
	{#if error}<Alert tone="danger">{error}</Alert>{/if}
	<TableShell><table>
		<thead><tr><th>{t('user')}</th><th>{t('email')}</th><th>{t('actions')}</th></tr></thead>
		<tbody>
			{#each members as member (member.id)}<tr>
				<td><span class="font-medium">{member.name}</span>
					{#if member.protected}<span class="ml-2"><Pill tone="warning" size="xs">{t('memberProtected')}</Pill></span>{/if}
					{#if member.identity_read_only}<span class="ml-2"><Pill tone="neutral" size="xs">{t('memberJoined')}</Pill></span>{/if}
				</td>
				<td class="[overflow-wrap:anywhere]">{member.email || '—'}</td>
				<td><Button variant="danger-outline" size="sm" disabled={disabled || member.protected} onclick={() => remove(member)}>{t('remove')}</Button></td>
			</tr>{/each}
			{#if !loading && !error && !members.length}<tr><td colspan="3">{t('noMembers')}</td></tr>{/if}
		</tbody>
	</table></TableShell>
</div>
