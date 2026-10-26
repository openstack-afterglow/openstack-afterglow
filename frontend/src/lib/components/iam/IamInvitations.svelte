<script lang="ts">
	import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
	import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';
	import { onMount, onDestroy, untrack } from 'svelte';
	import { ApiError } from '$lib/api/client';
	import { domainIam, type IamSession, type IamInvitation, type IamAssignableRoles } from '$lib/api/domainIam';
	import type { Project } from '$lib/types/project';
	import { t } from '$lib/i18n/ns/domain-iam';
	import { t as tc } from '$lib/i18n/ns/common';
	import { iamErrorMessage } from './iamError';
	import { enrollmentStatusLabel } from './enrollmentStatus';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import FormModal from '$lib/components/ui/FormModal.svelte';
	import TableShell from '$lib/components/ui/TableShell.svelte';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	let { session, blocked = false, onDenied }: { session: IamSession; blocked?: boolean; onDenied: () => void } = $props();
	const client = untrack(() => domainIam(session));
	const uid = $props.id();
	let live = true;
	let revision = 0;
	let projects = $state<Project[]>([]);
	let rows = $state<IamInvitation[]>([]);
	let email = $state('');
	let recipient = $state('');
	let selected = $state<Record<string, string[]>>({});
	let catalogs = $state<Record<string, IamAssignableRoles>>({});
	let roleLoading = $state<string[]>([]);
	let choosing = $state(false);
	let loading = $state(true);
	let busy = $state(false);
	let error = $state('');
	let modalError = $state('');
	let notice = $state('');
	const valid = $derived(!roleLoading.length && Object.entries(selected).every(([id, roles]) => catalogs[id] && roles.some(role => catalogs[id].roles.some(row => row.id === role && row.area === 'project' && ['reader', 'member', 'admin'].includes(row.grade ?? '')))));
	function current() { return live && session.isCurrent(); }
	function fail(cause: unknown) { if (!current()) return; error = iamErrorMessage(cause, t('saveFailed')); if (cause instanceof ApiError && cause.status === 403) onDenied(); }
	function close() { revision++; choosing = false; recipient = ''; selected = {}; catalogs = {}; roleLoading = []; modalError = ''; }
	async function load() {
		loading = true; error = '';
		try {
			const [p, invitations] = await Promise.all([client.projects(), client.invitations()]);
			if (current()) { projects = p.items; rows = invitations.items; }
		} catch (cause) { fail(cause); }
		finally { if (current()) loading = false; }
	}
	function prepare(event: SubmitEvent) {
		event.preventDefault();
		if (!current() || !session.canSubmit() || blocked || busy || loading || !email.trim()) return;
		close(); recipient = email.trim(); choosing = true; error = ''; notice = '';
	}
	async function toggleProject(id: string, checked: boolean) {
		if (!current() || busy || blocked) return;
		if (!checked) { const next = { ...selected }; delete next[id]; selected = next; return; }
		selected = { ...selected, [id]: [] }; roleLoading = [...roleLoading, id]; modalError = '';
		const request = revision;
		try {
			const result = await client.roles(id);
			if (current() && choosing && request === revision) {
				catalogs = { ...catalogs, [id]: { ...result, roles: result.roles.filter(role => role.name.toLowerCase() !== 'admin' && !(role.area === 'project' && role.grade === 'owner')) } };
			}
		} catch (cause) { if (current() && request === revision) { modalError = iamErrorMessage(cause, t('loadFailed')); if (cause instanceof ApiError && cause.status === 403) onDenied(); } }
		finally { if (current() && request === revision) roleLoading = roleLoading.filter(value => value !== id); }
	}
	function toggleRole(id: string, role: string, checked: boolean) {
		if (!current() || busy || blocked || !selected[id] || !catalogs[id]?.roles.some(row => row.id === role)) return;
		selected = { ...selected, [id]: checked ? [...new Set([...selected[id], role])] : selected[id].filter(value => value !== role) };
	}
	async function send() {
		if (!current() || !session.canSubmit() || blocked || busy || loading || !choosing || !valid) return;
		const target = recipient;
		const plan = Object.entries(selected).map(([project_id, role_ids]) => ({ project_id, role_ids: [...role_ids] }));
		busy = true; error = ''; notice = '';
		try { await client.invite(target, plan); if (current()) { email = ''; notice = t('inviteSent'); close(); await load(); } }
		catch (cause) { if (current()) { close(); email = ''; fail(cause); } }
		finally { if (current()) busy = false; }
	}
	async function revoke(row: IamInvitation) {
		if (!current() || blocked || busy || loading || !(row.status === 'pending' || row.recovery_required)) return;
		if (!await confirmDialog(t('revokeConfirm', { email: row.email }), { confirmLabel: t('revoke') })) return;
		if (!current() || !session.canSubmit() || blocked || busy || loading || !rows.includes(row) || !(row.status === 'pending' || row.recovery_required)) return;
		busy = true; error = '';
		try { await client.revoke(row.id); if (current()) await load(); }
		catch (cause) { fail(cause); }
		finally { if (current()) busy = false; }
	}
	function date(value: string) { const parsed = new Date(value); return Number.isNaN(parsed.getTime()) ? '—' : parsed.toLocaleString(intlLocale()); }
	function projectNames(row: IamInvitation) { return row.projects?.map(project => project.project_name || project.project_id).join(', ') || row.project_name || row.project_id || t('defaultMembership'); }
	onMount(() => { void load(); });
	onDestroy(() => { live = false; close(); email = ''; rows = []; projects = []; });
</script>

<div class="space-y-4">
	<Alert tone="info">{t('inviteHelp')}</Alert>
	{#if error}<Alert tone="danger">{error}</Alert>{/if}
	{#if notice}<Alert tone="success">{notice}</Alert>{/if}
	{#if loading}<ActivityIndicator label={t('loading')} />{/if}
	<Card><form class="space-y-4" onsubmit={prepare}>
		<Field label={t('email')} required for={`${uid}-email`}><TextInput id={`${uid}-email`} type="email" bind:value={email} required disabled={blocked || busy || loading} autocomplete="off" /></Field>
		<Button type="submit" variant="primary" disabled={blocked || !session.canSubmit() || busy || loading}>{t('sendInvite')}</Button>
	</form></Card>
	<div><Button variant="secondary" disabled={busy || loading} onclick={load}>{t('refresh')}</Button></div>
	<ResponsiveTable>
		{#snippet cards()}
			{#each rows as row (row.id)}<CompactResourceCard>
				<h3 class="text-sm font-medium break-all">{row.email}</h3><p class="text-xs">{enrollmentStatusLabel(row.status)}</p><p class="text-sm [overflow-wrap:anywhere]">{projectNames(row)}</p>
				{#snippet details()}<p class="text-xs">{t('expires')}: {date(row.expires_at)}</p>{/snippet}
				{#snippet actions()}<Button variant="danger-outline" size="sm" disabled={blocked || busy || loading || !(row.status === 'pending' || row.recovery_required)} onclick={() => revoke(row)}>{t('revoke')}</Button>{/snippet}
			</CompactResourceCard>{/each}
			{#if !loading && !error && !rows.length}<p class="text-sm text-ink-2">{t('emptyInvites')}</p>{/if}
		{/snippet}
		<TableShell><table><thead><tr><th>{t('email')}</th><th>{t('project')}</th><th>{t('status')}</th><th>{t('expires')}</th><th>{t('actions')}</th></tr></thead>
			<tbody>{#each rows as row (row.id)}<tr><td>{row.email}</td><td class="[overflow-wrap:anywhere]">{projectNames(row)}</td><td>{enrollmentStatusLabel(row.status)}</td><td>{date(row.expires_at)}</td><td><Button variant="danger-outline" size="sm" disabled={blocked || busy || loading || !(row.status === 'pending' || row.recovery_required)} onclick={() => revoke(row)}>{t('revoke')}</Button></td></tr>{/each}{#if !loading && !error && !rows.length}<tr><td colspan="5">{t('emptyInvites')}</td></tr>{/if}</tbody>
		</table></TableShell>
	</ResponsiveTable>
</div>
{#if choosing}
	<FormModal open={true} title={t('inviteProjectsTitle')} submitting={busy} onClose={close}>
		<div class="space-y-4">
			<p class="text-sm [overflow-wrap:anywhere]">{recipient}</p>
			<Alert tone="info">{t('inviteProjectsHelp')}</Alert>
			{#if modalError}<Alert tone="danger">{modalError}</Alert>{/if}
			{#each projects as project (project.id)}
				<div class="space-y-2 border-b border-line pb-3">
					<label class="flex min-h-11 items-start gap-3 text-sm"><input type="checkbox" class="mt-1 shrink-0" checked={project.id in selected} disabled={blocked || busy || roleLoading.includes(project.id)} onchange={(event) => toggleProject(project.id, event.currentTarget.checked)} /><span class="min-w-0 [overflow-wrap:anywhere]">{project.name}<span class="block text-xs text-ink-2">{project.id}</span></span></label>
					{#if project.id in selected}
						{#if roleLoading.includes(project.id)}<ActivityIndicator label={t('loading')} />{:else if catalogs[project.id]}
							<fieldset class="space-y-1 pl-5"><legend class="text-xs text-ink-2 [overflow-wrap:anywhere]">{project.name} · {project.id} · {t('inviteProjectsRoles')}</legend>
								{#each catalogs[project.id].roles as role (role.id)}<label class="flex min-h-11 items-center gap-3 text-sm"><input type="checkbox" checked={selected[project.id].includes(role.id)} disabled={blocked || busy} onchange={(event) => toggleRole(project.id, role.id, event.currentTarget.checked)} /><span class="min-w-0 [overflow-wrap:anywhere]">{role.name}</span></label>{/each}
							</fieldset>
						{:else}<Button variant="secondary" disabled={busy || blocked} onclick={() => toggleProject(project.id, true)}>{t('refresh')}</Button>{/if}
					{/if}
				</div>
			{/each}
		</div>
		{#snippet actions()}<Button variant="secondary" disabled={busy} onclick={close}>{tc('actions.cancel')}</Button><Button variant="primary" disabled={blocked || !session.canSubmit() || busy || !valid} ariaBusy={busy} onclick={send}>{t('inviteProjectsSend')}</Button>{/snippet}
	</FormModal>
{/if}
