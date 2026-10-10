<script lang="ts">
	import { untrack } from 'svelte';
	import { t } from '$lib/i18n/ns/account';
	import { t as tc } from '$lib/i18n/ns/common';
	import type { AssignableProjectRole, ProjectAccessMember } from '$lib/types/project';
	import FormModal from '$lib/components/ui/FormModal.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	let { member, roles, isOwner, busy, error, onSave, onClose }: {
		member: ProjectAccessMember; roles: AssignableProjectRole[]; isOwner: boolean;
		busy: boolean; error: string; onSave: (ids: string[]) => void; onClose: () => void;
	} = $props();
	let selected = $state<string[]>(untrack(() => [...(member.direct_role_ids ?? [])]));
	const areas = $derived([...new Set(roles.map(role => role.area ?? 'legacy'))]);
	function editable(role: AssignableProjectRole) {
		return isOwner || !['project_owner', 'project_admin'].includes(role.name);
	}
	function toggle(id: string, checked: boolean) {
		selected = checked ? [...selected, id] : selected.filter(value => value !== id);
	}
</script>

<FormModal open={true} title={t('projectMemberRoles.title', { user: member.username || member.user_id })} submitting={busy} {onClose}>
	<div class="space-y-4 min-w-0">
		<Alert tone="info">{t('projectMemberRoles.directOnlyHelp')}</Alert>
		{#if error}<Alert tone="danger">{error}</Alert>{/if}
		<p class="text-sm text-ink-2 [overflow-wrap:anywhere]">{t('projectMemberRoles.effectiveRoles', { roles: (member.roles ?? []).join(', ') || '—' })}</p>
		{#each areas as area}
			<fieldset class="border border-line rounded-lg p-3 space-y-2">
				<legend class="text-sm font-semibold text-ink-1 px-1">{area}</legend>
				{#each roles.filter(role => (role.area ?? 'legacy') === area) as role (role.id)}
					<label class="flex items-start gap-2 text-sm text-ink-1">
						<input type="checkbox" checked={selected.includes(role.id)} disabled={busy || !editable(role)} onchange={(event) => toggle(role.id, event.currentTarget.checked)} />
						<span class="min-w-0 [overflow-wrap:anywhere]"><code>{role.name}</code> <span class="text-xs text-ink-2">{role.grade ?? ''} · {role.name === `${role.area}_${role.grade}` ? t('projectMemberRoles.grade') : t('projectMemberRoles.permission')}{member.effective_role_ids?.includes(role.id) && !member.direct_role_ids?.includes(role.id) ? t('projectMemberRoles.inheritedReadOnly') : ''}</span>{#if role.description}<span class="block text-xs text-ink-2">{role.description}</span>{/if}</span>
					</label>
				{/each}
			</fieldset>
		{/each}
	</div>
	{#snippet actions()}
		<Button variant="secondary" disabled={busy} onclick={onClose}>{tc('actions.cancel')}</Button>
		<Button variant="primary" disabled={busy || ['group', 'inherited'].includes(member.source ?? '')} ariaBusy={busy} onclick={() => onSave(selected)}>{t('projectMemberRoles.save')}</Button>
	{/snippet}
</FormModal>
