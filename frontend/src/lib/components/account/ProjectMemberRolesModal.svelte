<script lang="ts">
	import { untrack } from 'svelte';
	import { t } from '$lib/i18n/ns/account';
	import { t as tc } from '$lib/i18n/ns/common';
	import type { AssignableProjectRole, ProjectAccessMember } from '$lib/types/project';
	import Modal from '$lib/components/ui/Modal.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import SelectInput from '$lib/components/ui/SelectInput.svelte';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
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
	let selectedArea = $state(untrack(() => roles[0]?.area ?? 'legacy'));
	let searchArea = $state('');
	const componentId = $props.id();
	const titleId = `${componentId}-title`;
	const searchId = `${componentId}-search`;
	const areaId = `${componentId}-area`;
	const roleById = $derived(new Map(roles.map(role => [role.id, role])));
	const implied = $derived(impliedRoleIds(selected));
	const externalInherited = $derived(new Set(member.external_role_ids));
	const directEditable = $derived(!['group', 'inherited'].includes(member.source ?? ''));
	const query = $derived(search.trim().toLowerCase());
	const visibleRoles = $derived(roles.filter(role => !query || [role.name, role.id, role.description ?? ''].some(value => value.toLowerCase().includes(query))));
	const areas = $derived.by(() => {
		const groups = new Map<string, { name: string; directCount: number; inheritedCount: number }>();
		const directIds = new Set(selected);
		for (const role of roles) {
			const name = role.area ?? 'legacy';
			let group = groups.get(name);
			if (!group) {
				group = { name, directCount: 0, inheritedCount: 0 };
				groups.set(name, group);
			}
			if (directIds.has(role.id)) group.directCount++;
			if (inherited(role.id)) group.inheritedCount++;
		}
		return [...groups.values()];
	});
	const matchingAreaNames = $derived(new Set(visibleRoles.map(role => role.area ?? 'legacy')));
	const matchingAreas = $derived(areas.filter(area => matchingAreaNames.has(area.name)));
	const preferredArea = $derived(query && searchArea ? searchArea : selectedArea);
	const activeArea = $derived(matchingAreas.some(area => area.name === preferredArea) ? preferredArea : matchingAreas[0]?.name ?? '');
	const activeRoles = $derived(visibleRoles.filter(role => (role.area ?? 'legacy') === activeArea));
	const activeSummary = $derived(areas.find(area => area.name === activeArea));
	function chooseArea(area: string) {
		if (busy) return;
		if (query) searchArea = area;
		else selectedArea = area;
	}
	function updateSearch(event: Event) {
		search = (event.currentTarget as HTMLInputElement).value;
		searchArea = '';
	}
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

<Modal open={true} {onClose} dismissible={!busy} labelledBy={titleId}>
	<Card surface="modal" padding="none" class="flex h-[min(48rem,calc(100dvh-2rem))] w-[min(56rem,calc(100vw-2rem))] min-h-0 flex-col">
		<header class="shrink-0 space-y-3 border-b border-line p-4">
			<h2 id={titleId} class="truncate text-lg font-semibold text-ink-0" title={t('projectMemberRoles.title', { user: member.username || member.user_id })}>{t('projectMemberRoles.title', { user: member.username || member.user_id })}</h2>
			<Field label={t('projectMemberRoles.searchLabel')} for={searchId}>
				<TextInput id={searchId} type="search" value={search} oninput={updateSearch} placeholder={t('projectMemberRoles.searchPlaceholder')} disabled={busy} ariaDescribedBy={visibleRoles.length === 0 ? `${searchId}-message` : ''} />
			</Field>
		</header>
		<div class="min-h-0 flex-1 flex flex-col overflow-hidden md:flex-row">
			<nav aria-label={t('projectMemberRoles.areaLabel')} class="role-area-nav hidden w-56 shrink-0 overflow-y-auto border-r border-line p-3 md:block">
				<p class="mb-2 text-xs font-semibold text-ink-2">{t('projectMemberRoles.areaLabel')}</p>
				<div class="space-y-1">
					{#each matchingAreas as area (area.name)}
						<Button variant="ghost" class="project-member-area min-h-11 w-full" ariaPressed={activeArea === area.name} disabled={busy} onclick={() => chooseArea(area.name)}>
							<span class="min-w-0 w-full text-left [overflow-wrap:anywhere]">
								<span class="block text-sm text-ink-1">{area.name}</span>
								<span class="block text-xs text-ink-2 whitespace-normal">{t('projectMemberRoles.areaCounts', { direct: area.directCount, inherited: area.inheritedCount })}</span>
							</span>
						</Button>
					{/each}
				</div>
			</nav>
			<div class="shrink-0 border-b border-line p-4 md:hidden">
				<Field label={t('projectMemberRoles.areaLabel')} for={areaId}>
					<SelectInput id={areaId} value={activeArea} disabled={busy || matchingAreas.length === 0} onchange={(event) => chooseArea((event.currentTarget as HTMLSelectElement).value)}>
						{#if matchingAreas.length === 0}<option value="">{t('projectMemberRoles.searchNoResults')}</option>{/if}
						{#each matchingAreas as area (area.name)}
							<option value={area.name}>{area.name} · {t('projectMemberRoles.areaCounts', { direct: area.directCount, inherited: area.inheritedCount })}</option>
						{/each}
					</SelectInput>
				</Field>
			</div>
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
							{activeArea}
							<span class="block text-xs font-normal text-ink-2">{t('projectMemberRoles.areaCounts', { direct: activeSummary?.directCount ?? 0, inherited: activeSummary?.inheritedCount ?? 0 })}</span>
						</legend>
						{#each activeRoles as role (role.id)}
							<label class="flex min-h-11 items-start gap-3 rounded-md border border-line p-3 text-sm text-ink-1">
								<input class="mt-1 shrink-0" type="checkbox" checked={selected.includes(role.id) || inherited(role.id)} disabled={disabled(role)} onchange={(event) => toggle(role, event.currentTarget.checked)} />
								<span class="min-w-0 [overflow-wrap:anywhere]"><code>{role.name}</code> <span class="text-xs text-ink-2">{role.grade ?? ''} · {role.name === `${role.area}_${role.grade}` ? t('projectMemberRoles.grade') : t('projectMemberRoles.permission')}{inherited(role.id) ? t('projectMemberRoles.inheritedReadOnly') : ''}</span>{#if role.description}<span class="block text-xs text-ink-2">{role.description}</span>{/if}</span>
							</label>
						{/each}
					</fieldset>
				{/if}
			</div>
		</div>
		<footer class="flex shrink-0 flex-wrap items-center justify-end gap-3 border-t border-line p-4">
			{#if busy}<ActivityIndicator size="xs" label={tc('state.processing')} />{/if}
			<Button variant="secondary" disabled={busy} onclick={onClose}>{tc('actions.cancel')}</Button>
			<Button variant="primary" disabled={busy || !directEditable} ariaBusy={busy} onclick={save}>{t('projectMemberRoles.save')}</Button>
		</footer>
	</Card>
</Modal>

<style>
	.role-area-nav :global(.project-member-area[aria-pressed='true']) {
		background: var(--color-surface-selected);
	}
</style>
