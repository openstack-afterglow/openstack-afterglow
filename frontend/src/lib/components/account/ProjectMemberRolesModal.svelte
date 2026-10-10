<script lang="ts">
	import { untrack } from 'svelte';
	import { t } from '$lib/i18n/ns/account';
	import { t as tc } from '$lib/i18n/ns/common';
	import type { AssignableProjectRole, ProjectAccessMember } from '$lib/types/project';
	import FormModal from '$lib/components/ui/FormModal.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	let { member, roles, isOwner, busy, error, onSave, onClose }: {
		member: ProjectAccessMember; roles: AssignableProjectRole[]; isOwner: boolean;
		busy: boolean; error: string; onSave: (ids: string[]) => void; onClose: () => void;
	} = $props();
	let selected = $state<string[]>(untrack(() => [...(member.direct_role_ids ?? [])]));
	let search = $state('');
	const roleById = $derived(new Map(roles.map(role => [role.id, role])));
	const implied = $derived(impliedRoleIds(selected));
	const externalInherited = $derived(new Set(member.external_role_ids));
	const directEditable = $derived(!['group', 'inherited'].includes(member.source ?? ''));
	const query = $derived(search.trim().toLowerCase());
	const visibleRoles = $derived(roles.filter(role => !query || [role.name, role.id, role.description ?? ''].some(value => value.toLowerCase().includes(query))));
	const areas = $derived([...new Set(visibleRoles.map(role => role.area ?? 'legacy'))]);
	function editable(role: AssignableProjectRole) {
		return isOwner || !['project_owner', 'project_admin'].includes(role.name);
	}
	function impliedRoleIds(directIds: string[]) {
		const descendants = new Set<string>();
		for (const id of directIds) {
			// The catalog already contains the server-validated transitive closure.
			for (const child of roleById.get(id)?.inherited_role_ids ?? []) {
				if (child !== id) descendants.add(child);
			}
		}
		return descendants;
	}
	function inherited(id: string) {
		return implied.has(id) || externalInherited.has(id);
	}
	function disabled(role: AssignableProjectRole) {
		return busy || !directEditable || !editable(role) || inherited(role.id);
	}
	function toggle(role: AssignableProjectRole, checked: boolean) {
		if (disabled(role)) return;
		selected = checked ? selected.includes(role.id) ? selected : [...selected, role.id] : selected.filter(value => value !== role.id);
	}
	function save() {
		if (!busy && directEditable) onSave(selected);
	}
</script>

<FormModal open={true} title={t('projectMemberRoles.title', { user: member.username || member.user_id })} submitting={busy} {onClose}>
	<div class="space-y-4 min-w-0">
		<Alert tone="info">{t('projectMemberRoles.directOnlyHelp')}</Alert>
		{#if error}<Alert tone="danger">{error}</Alert>{/if}
		<Field label={t('projectMemberRoles.searchLabel')} for="project-member-role-search">
			<TextInput id="project-member-role-search" type="search" bind:value={search} placeholder={t('projectMemberRoles.searchPlaceholder')} disabled={busy} ariaDescribedBy={visibleRoles.length === 0 ? 'project-member-role-search-message' : ''} />
			{#if visibleRoles.length === 0}<p id="project-member-role-search-message" role="status" class="text-sm text-ink-2">{t('projectMemberRoles.searchNoResults')}</p>{/if}
		</Field>
		<p class="text-sm text-ink-2 [overflow-wrap:anywhere]">{t('projectMemberRoles.effectiveRoles', { roles: (member.roles ?? []).join(', ') || '—' })}</p>
		{#each areas as area}
			<fieldset class="border border-line rounded-lg p-3 space-y-2">
				<legend class="text-sm font-semibold text-ink-1 px-1">{area}</legend>
				{#each visibleRoles.filter(role => (role.area ?? 'legacy') === area) as role (role.id)}
					<label class="flex items-start gap-2 text-sm text-ink-1">
						<input type="checkbox" checked={selected.includes(role.id) || inherited(role.id)} disabled={disabled(role)} onchange={(event) => toggle(role, event.currentTarget.checked)} />
						<span class="min-w-0 [overflow-wrap:anywhere]"><code>{role.name}</code> <span class="text-xs text-ink-2">{role.grade ?? ''} · {role.name === `${role.area}_${role.grade}` ? t('projectMemberRoles.grade') : t('projectMemberRoles.permission')}{inherited(role.id) ? t('projectMemberRoles.inheritedReadOnly') : ''}</span>{#if role.description}<span class="block text-xs text-ink-2">{role.description}</span>{/if}</span>
					</label>
				{/each}
			</fieldset>
		{/each}
	</div>
	{#snippet actions()}
		<Button variant="secondary" disabled={busy} onclick={onClose}>{tc('actions.cancel')}</Button>
		<Button variant="primary" disabled={busy || !directEditable} ariaBusy={busy} onclick={save}>{t('projectMemberRoles.save')}</Button>
	{/snippet}
</FormModal>
