<script lang="ts">
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import { createTableView } from '$lib/utils/tableView.svelte';
	import TableColumnHeader from '$lib/components/ui/TableColumnHeader.svelte';
	import TableViewControls from '$lib/components/ui/TableViewControls.svelte';
	import RegexSearch from '$lib/components/ui/RegexSearch.svelte';
	import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
	import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';
	import { onMount, onDestroy, untrack } from 'svelte';
	import { domainIam, type IamGroup, type IamSession } from '$lib/api/domainIam';
	import { t } from '$lib/i18n/ns/domain-iam-groups';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { groupAuthorityLost, groupErrorMessage } from './groupError';
	import Button from '$lib/components/ui/Button.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Pill from '$lib/components/ui/Pill.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import TextareaInput from '$lib/components/ui/TextareaInput.svelte';
	import FormModal from '$lib/components/ui/FormModal.svelte';
	import SlideOver from '$lib/components/ui/SlideOver.svelte';
	import TableShell from '$lib/components/ui/TableShell.svelte';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import IamGroupMembers from './IamGroupMembers.svelte';

	let { session, blocked = false, onDenied }: { session: IamSession; blocked?: boolean; onDenied: () => void } = $props();
	const client = untrack(() => domainIam(session));
	const uid = $props.id();
	const NAME = /^\S(?:.*\S)?$/;
	let live = true;
	let revision = 0;
	let groups = $state<IamGroup[]>([]);
	let loading = $state(true);
	let error = $state('');
	let notice = $state('');
	let panel = $state<{ mode: 'edit' | 'members'; group: IamGroup } | null>(null);
	let showCreate = $state(false);
	let creating = $state(false);
	let createName = $state('');
	let createDescription = $state('');
	let createError = $state('');
	let editName = $state('');
	let editDescription = $state('');
	let editError = $state('');
	let saving = $state(false);
	let busy = $state(false);

	const actionsDisabled = $derived(blocked || busy || !session.canSubmit());

	function fail(cause: unknown, fallback = t('loadFailed')) {
		if (!live || !session.isCurrent()) return '';
		if (groupAuthorityLost(cause)) onDenied();
		return groupErrorMessage(cause, fallback);
	}
	async function load() {
		const pending = ++revision;
		loading = true; error = '';
		try {
			const result = await client.groups();
			if (!live || !session.isCurrent() || pending !== revision) return;
			groups = result.items;
			if (panel) {
				const fresh = groups.find(row => row.id === panel!.group.id);
				panel = fresh ? { mode: panel.mode, group: fresh } : null;
			}
		} catch (cause) { if (pending === revision) error = fail(cause); }
		finally { if (live && pending === revision) loading = false; }
	}
	function openCreate() { createName = ''; createDescription = ''; createError = ''; notice = ''; showCreate = true; }
	async function create() {
		const name = createName.trim();
		if (!NAME.test(name)) { createError = t('nameRequired'); return; }
		creating = true; createError = '';
		try {
			await client.createGroup({ name, description: createDescription.trim() });
			if (!live || !session.isCurrent()) return;
			showCreate = false;
			await load();
		} catch (cause) { createError = fail(cause, t('errorSaveFailed')); }
		finally { if (live) creating = false; }
	}
	function openEdit(group: IamGroup) {
		editName = group.name; editDescription = group.description; editError = ''; notice = '';
		panel = { mode: 'edit', group };
	}
	async function save() {
		if (!panel) return;
		const target = panel.group;
		const name = editName.trim();
		if (!NAME.test(name)) { editError = t('nameRequired'); return; }
		const body: { name?: string; description?: string } = {};
		if (name !== target.name) body.name = name;
		if (editDescription.trim() !== target.description) body.description = editDescription.trim();
		if (!Object.keys(body).length) { panel = null; return; }
		saving = true; editError = '';
		try {
			await client.updateGroup(target.id, body);
			if (!live || !session.isCurrent()) return;
			panel = null;
			notice = t('saved');
			await load();
		} catch (cause) { editError = fail(cause, t('errorSaveFailed')); }
		finally { if (live) saving = false; }
	}
	async function remove(group: IamGroup) {
		notice = '';
		if (!await confirmDialog(t('deleteConfirm', { name: group.name }), { confirmLabel: t('delete') })) return;
		if (!live || !session.isCurrent()) return;
		busy = true;
		try {
			await client.deleteGroup(group.id);
			if (!live || !session.isCurrent()) return;
			if (panel?.group.id === group.id) panel = null;
			await load();
		} catch (cause) { error = fail(cause, t('errorSaveFailed')); }
		finally { if (live) busy = false; }
	}
	onMount(() => { void load(); });
	onDestroy(() => { live = false; revision++; groups = []; panel = null; });

	const tableSearchId = `${uid}-search`;
	let tableSearch = $state('');
	const tableView = createTableView<IamGroup>({
		rows: () => groups, locale: () => intlLocale(), search: () => tableSearch,
		searchable: row => [row.name, row.description, row.id],
		columns: () => [
			{ key: 'name', label: t('name'), value: row => row.name },
			{ key: 'description', label: t('description'), value: row => row.description },
			{ key: 'members', label: t('memberCount'), value: row => row.member_count }
		]
	});
</script>

<div class="space-y-4">
	<div class="flex flex-wrap justify-end gap-2">
		<Button variant="secondary" disabled={loading} onclick={load}>{t('refresh')}</Button>
		<Button variant="accent" disabled={actionsDisabled || creating} onclick={openCreate}>{t('create')}</Button>
	</div>
	{#if loading}<LoadingState variant={groups.length ? 'inline' : 'surface'} label={t('loading')} />{/if}
	{#if error}<Alert tone="danger">{error}</Alert>{/if}
	{#if notice}<Alert tone="success">{notice}</Alert>{/if}
	<RegexSearch id={tableSearchId} bind:value={tableSearch} /><TableViewControls view={tableView} />
	<ResponsiveTable>
		{#snippet cards()}
			{#each tableView.rows as group (group.id)}<CompactResourceCard>
				<div class="flex flex-wrap items-center justify-between gap-2"><h3 class="min-w-0 break-words text-sm font-medium">{group.name}</h3>{#if group.protected}<Pill tone="warning">{t('protected')}</Pill>{/if}{#if group.sso_mapped}<Pill tone="info">{t('ssoMapped')}</Pill>{/if}</div>
				<p class="line-clamp-2 text-sm text-ink-2">{group.description || '—'}</p>
				<p class="text-xs text-ink-2">{t('memberCount')}: {group.member_count}</p>
				{#snippet actions()}
					<Button variant="secondary" size="sm" disabled={actionsDisabled || group.protected} onclick={() => openEdit(group)}>{t('edit')}</Button>
					<Button variant="secondary" size="sm" disabled={blocked} onclick={() => { notice = ''; panel = { mode: 'members', group }; }}>{t('members')}</Button>
					<Button variant="danger-outline" size="sm" disabled={actionsDisabled || group.protected || group.sso_mapped} onclick={() => remove(group)}>{t('delete')}</Button>
				{/snippet}
			</CompactResourceCard>{/each}
		{/snippet}
		<TableShell><table>
			<thead><tr><TableColumnHeader view={tableView} columnKey="name" /><TableColumnHeader view={tableView} columnKey="description" /><TableColumnHeader view={tableView} columnKey="members" /><th>{t('actions')}</th></tr></thead>
			<tbody>
				{#each tableView.rows as group (group.id)}<tr>
					<td><span class="font-medium">{group.name}</span>{#if group.protected}<span class="ml-2"><Pill tone="warning" size="xs">{t('protected')}</Pill></span>{/if}{#if group.sso_mapped}<span class="ml-2"><Pill tone="info" size="xs">{t('ssoMapped')}</Pill></span>{/if}</td>
					<td class="max-w-80 whitespace-normal [overflow-wrap:anywhere]">{group.description || '—'}</td>
					<td>{group.member_count}</td>
					<td><div class="flex flex-wrap gap-2">
						<Button variant="secondary" size="sm" disabled={actionsDisabled || group.protected} onclick={() => openEdit(group)}>{t('edit')}</Button>
						<Button variant="secondary" size="sm" disabled={blocked} onclick={() => { notice = ''; panel = { mode: 'members', group }; }}>{t('members')}</Button>
						<Button variant="danger-outline" size="sm" disabled={actionsDisabled || group.protected || group.sso_mapped} onclick={() => remove(group)}>{t('delete')}</Button>
					</div></td>
				</tr>{/each}
				{#if !loading && !error && !groups.length}<tr><td colspan="4">{t('empty')}</td></tr>{/if}
			</tbody>
		</table></TableShell>
	</ResponsiveTable>
	{#if groups.some(group => group.protected)}<p class="text-xs text-ink-2">{t('protectedHelp')}</p>{/if}
	{#if groups.some(group => group.sso_mapped)}<p class="text-xs text-ink-2">{t('ssoMappedHelp')}</p>{/if}
</div>

{#if panel}
	{#key `${panel.mode}:${panel.group.id}`}
		{#if panel.mode === 'edit'}
			<SlideOver open={true} title={t('editTitle', { name: panel.group.name })} dismissible={!saving} onClose={() => { panel = null; }}>
				<Field label={t('name')} for="{uid}-edit-name" help={panel.group.sso_mapped ? t('ssoMappedHelp') : t('nameHelp')} error={editError} required>
					<TextInput id="{uid}-edit-name" bind:value={editName} maxlength={64} disabled={saving || actionsDisabled || panel.group.sso_mapped} />
				</Field>
				<Field label={t('description')} for="{uid}-edit-description">
					<TextareaInput id="{uid}-edit-description" bind:value={editDescription} maxlength={255} rows={3} disabled={saving || actionsDisabled} />
				</Field>
				<p class="text-xs text-ink-2">{t('roleNote')}</p>
				{#snippet footer()}
					<Button variant="primary" disabled={saving || actionsDisabled} ariaBusy={saving} onclick={save}>{t('save')}</Button>
				{/snippet}
			</SlideOver>
		{:else}
			<SlideOver open={true} title={t('membersTitle', { name: panel.group.name })} onClose={() => { panel = null; }}>
				<IamGroupMembers {session} group={panel.group} {blocked} {onDenied} onChanged={load} />
			</SlideOver>
		{/if}
	{/key}
{/if}
<FormModal bind:open={showCreate} title={t('createTitle')} submitLabel={t('createSubmit')} submitting={creating} onSubmit={create}>
	<div class="space-y-4">
		<Field label={t('name')} for="{uid}-create-name" help={t('nameHelp')} error={createError} required>
			<TextInput id="{uid}-create-name" bind:value={createName} maxlength={64} disabled={creating} />
		</Field>
		<Field label={t('description')} for="{uid}-create-description">
			<TextareaInput id="{uid}-create-description" bind:value={createDescription} maxlength={255} rows={3} disabled={creating} />
		</Field>
	</div>
</FormModal>
