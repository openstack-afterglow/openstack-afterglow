<script lang="ts">
	import { untrack } from 'svelte';
	import { t } from '$lib/i18n/ns/account';
	import { t as tc } from '$lib/i18n/ns/common';
	import type { AssignableProjectRole, ProjectAccessMember } from '$lib/types/project';
	import { isAssignableRole } from '$lib/utils/roleCatalog';
	import Modal from '$lib/components/ui/Modal.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	let { member, roles, busy, submitDisabled = false, error, onSave, onClose }: {
		member: ProjectAccessMember; roles: AssignableProjectRole[];
		busy: boolean; submitDisabled?: boolean; error: string; onSave: (ids: string[]) => void; onClose: () => void;
	} = $props();
	let selected = $state<string[]>(untrack(() => [...(member.direct_role_ids ?? [])]));
	let search = $state('');
	const selectableRoles = $derived(roles.filter(isAssignableRole));
	const componentId = $props.id();
	const titleId = `${componentId}-title`;
	const searchId = `${componentId}-search`;
	const roleById = $derived(new Map([...member.direct_roles, ...roles].map(role => [role.id, role])));
	const implied = $derived(impliedRoleIds(selected));
	const externalInherited = $derived(new Set(member.external_role_ids));
	const directEditable = $derived(!['group', 'inherited'].includes(member.source ?? ''));
	const query = $derived(search.trim().toLowerCase());
	const visibleRoles = $derived(selectableRoles.filter(role => !query || [role.name, role.id, role.description ?? ''].some(value => value.toLowerCase().includes(query))));
	function updateSearch(event: Event) {
		search = (event.currentTarget as HTMLInputElement).value;
	}
	function editable(role: AssignableProjectRole) {
		// Singleton ownership changes only through the explicit transfer workflow.
		return isAssignableRole(role) && !(role.area === 'project' && role.grade === 'owner');
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
	function toggle(role: AssignableProjectRole, input: HTMLInputElement) {
		const checked = input.checked;
		if (!disabled(role)) {
			selected = checked ? selected.includes(role.id) ? selected : [...selected, role.id] : selected.filter(value => value !== role.id);
		}
		// Direct and external inheritance remain independent of the visible choices.
		input.checked = selected.includes(role.id) || inherited(role.id);
	}
	function save() {
		if (!busy && !submitDisabled && directEditable) onSave(selected);
	}
</script>

<Modal open={true} {onClose} dismissible={!busy} labelledBy={titleId}>
	<Card surface="modal" padding="none" class="flex h-[min(48rem,calc(100dvh-2rem))] w-[min(56rem,calc(100vw-2rem))] min-h-0 flex-col">
		<header class="shrink-0 space-y-3 border-b border-line p-4">
			<h2 id={titleId} class="truncate text-lg font-semibold text-ink-0" title={t('projectMemberRoles.title', { user: member.username || member.user_id })}>{t('projectMemberRoles.title', { user: member.username || member.user_id })}</h2>
			<Field label={t('projectMemberRoles.searchLabel')} for={searchId}>
				<TextInput id={searchId} type="search" value={search} oninput={updateSearch} placeholder={t('projectMemberRoles.searchPlaceholder')} disabled={busy} ariaDescribedBy={visibleRoles.length === 0 ? `${searchId}-message` : ''} />
			</Field>
		</header>
		<div class="min-w-0 min-h-0 flex-1 overflow-y-auto p-4 space-y-4">
				<Alert tone="info">{t('projectMemberRoles.directOnlyHelp')}</Alert>
				{#if error}<Alert tone="danger">{error}</Alert>{/if}
				<details class="border-t border-line pt-3">
					<summary class="cursor-pointer text-sm text-ink-2">{t('projectMemberRoles.effectiveRolesCount', { count: (member.roles ?? []).length })}</summary>
					<p class="mt-2 max-h-32 overflow-y-auto text-sm text-ink-2 [overflow-wrap:anywhere]">{t('projectMemberRoles.effectiveRoles', { roles: (member.roles ?? []).join(', ') || '—' })}</p>
				</details>
				{#if visibleRoles.length === 0}
					<p id={`${searchId}-message`} role="status" class="text-sm text-ink-2">{t('projectMemberRoles.searchNoResults')}</p>
				{:else}
					<fieldset class="min-w-0 space-y-2">
						<legend class="mb-3 text-sm font-semibold text-ink-1 [overflow-wrap:anywhere]">
							{t('projectMemberRoles.rolesLabel')}
						</legend>
						{#each visibleRoles as role (role.id)}
							<label class="flex min-h-11 items-start gap-3 rounded-md border border-line p-3 text-sm text-ink-1">
								<input class="mt-1 shrink-0" type="checkbox" checked={selected.includes(role.id) || inherited(role.id)} disabled={disabled(role)} onchange={(event) => toggle(role, event.currentTarget)} />
							<span class="min-w-0 [overflow-wrap:anywhere]"><code>{role.name}</code> <span class="text-xs text-ink-2">{#if role.grade && role.grade !== role.name}{role.grade} · {/if}{role.name === 'member' || role.name === 'reader' ? t('projectMemberRoles.rolesLabel') : role.name === `${role.area}_${role.grade}` ? t('projectMemberRoles.grade') : t('projectMemberRoles.permission')}{inherited(role.id) ? t('projectMemberRoles.inheritedReadOnly') : ''}</span>{#if role.description}<span class="block text-xs text-ink-2">{role.description}</span>{/if}</span>
							</label>
						{/each}
					</fieldset>
				{/if}
			</div>
		<footer class="flex shrink-0 flex-wrap items-center justify-end gap-3 border-t border-line p-4">
			{#if busy}<LoadingState variant="control" label={tc('state.processing')}  />{/if}
			<Button variant="secondary" disabled={busy} onclick={onClose}>{tc('actions.cancel')}</Button>
			<Button variant="primary" disabled={busy || submitDisabled || !directEditable} ariaBusy={busy} onclick={save}>{t('projectMemberRoles.save')}</Button>
		</footer>
	</Card>
</Modal>
