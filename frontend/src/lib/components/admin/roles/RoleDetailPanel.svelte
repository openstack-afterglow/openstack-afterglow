<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-identity';
	import SlidePanel from '$lib/components/SlidePanel.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import SelectionCheckbox from '$lib/components/ui/SelectionCheckbox.svelte';
	import RoleBadges from './RoleBadges.svelte';
	import { buildRoleGraph, deleteDisabledReason, edgeDisabledReason, matchesRole, sortRoles } from './catalog';
	import type { ManagedRole } from './types';
	let { role, roles, busy, stale, error, onClose, onEdit, onDelete, onToggle, onSelect }: {
		role: ManagedRole; roles: ManagedRole[]; busy: boolean; stale: boolean; error: string;
		onClose: () => void; onEdit: () => void; onDelete: () => void;
		onToggle: (candidate: ManagedRole) => void; onSelect: (role: ManagedRole) => void;
	} = $props();
	let query = $state('');
	const graph = $derived(buildRoleGraph(roles));
	const candidates = $derived(sortRoles(roles.filter((candidate) => matchesRole(candidate, query)), 'name', 'asc'));
	const direct = $derived(new Set(role.implied_role_ids));
	const inherited = $derived(role.inherited_role_ids.filter((id) => !direct.has(id)));
	const deleteReason = $derived(deleteDisabledReason(role));
</script>

<SlidePanel {onClose} width="w-full md:w-[32rem] max-w-full" resizable={false} storageKey="admin-roles.detail" ariaLabel={t('rolePage.detailLabel', { name: role.name })}>
	<div class="min-w-0 space-y-5 px-4 pb-6 md:px-6">
		<header class="space-y-2">
			<h2 class="text-lg font-semibold text-ink-0 [overflow-wrap:anywhere]">{role.name}</h2>
			<RoleBadges {role} />
			<p class="text-xs font-mono text-ink-2 [overflow-wrap:anywhere]">{role.id}</p>
			<p class="text-xs text-ink-2 [overflow-wrap:anywhere]">{t('roleDetail.domain', { domain: role.domain_id ?? t('roleDetail.global') })}</p>
			<p class="whitespace-pre-wrap text-sm text-ink-1 [overflow-wrap:anywhere]">{role.description || t('rolePage.noDescription')}</p>
		</header>
		{#if error}<Alert tone="danger">{error}</Alert>{/if}
		{#if stale}<Alert tone="warning">{t('roleDetail.stale')}</Alert>{/if}
		{#if busy}<p role="status" class="text-xs text-ink-2">{t('roleDetail.busy')}</p>{/if}
		<div class="flex flex-wrap gap-2">
			<Button variant="secondary" disabled={busy || stale} onclick={onEdit}>{t('roleDetail.edit')}</Button>
			<Button variant="danger-outline" disabled={busy || stale || !!deleteReason} onclick={onDelete}>{t('roleDetail.delete')}</Button>
		</div>
		<p class="text-xs text-ink-2">{deleteReason ?? t('roleDetail.deleteHelp')}</p>

		<section aria-label={t('roleDetail.directChildrenLabel')} class="space-y-3">
			<h3 class="text-sm font-semibold text-ink-0">{t('roleDetail.directChildrenHeading', { count: direct.size })}</h3>
			<p class="text-xs text-ink-2">{t('roleDetail.directChildrenHelp')}</p>
			<TextInput type="search" bind:value={query} ariaLabel={t('roleDetail.searchChildren')} placeholder={t('rolePage.searchPlaceholder')} />
			<ul class="divide-y divide-line" aria-label={t('roleDetail.candidatesLabel')}>
				{#each candidates as candidate (candidate.id)}
					{@const checked = direct.has(candidate.id)}
					{@const reason = edgeDisabledReason(graph, role, candidate)}
					<li class="flex min-w-0 items-start gap-3 py-3">
						<SelectionCheckbox {checked} disabled={busy || stale || !!reason} ariaLabel={t('roleDetail.inheritLabel', { name: candidate.name })} title={reason ?? undefined}
							onclick={(event) => { event.preventDefault(); onToggle(candidate); }} class="shrink-0" />
						<div class="min-w-0 flex-1 space-y-1">
							<p class="text-sm text-ink-1 [overflow-wrap:anywhere]">{candidate.name}</p>
							<RoleBadges role={candidate} />
							<p class="text-xs font-mono text-ink-2 [overflow-wrap:anywhere]">{candidate.id}</p>
							<p class="text-xs text-ink-2">{checked ? t('roleDetail.directlyLinked') : role.inherited_role_ids.includes(candidate.id) ? t('roleDetail.indirectlyInherited') : t('roleDetail.notLinked')}</p>
							{#if reason}<p class="text-xs text-ink-2">{t('roleDetail.unavailable', { reason })}</p>{/if}
						</div>
					</li>
				{/each}
			</ul>
			{#if candidates.length === 0}<p class="text-xs text-ink-2">{t('roleDetail.noCandidates')}</p>{/if}
			{#each role.implied_role_ids.filter((id) => !graph.byId.has(id)) as missingId}
				<Alert tone="warning">{t('roleDetail.missingTarget', { id: missingId })}</Alert>
			{/each}
		</section>

		{#snippet related(ids: string[], empty: string)}
			{#if ids.length === 0}<p class="text-xs text-ink-2">{empty}</p>{:else}
				<ul class="space-y-2">
					{#each ids as id (id)}
						{@const relatedRole = graph.byId.get(id)}
						<li class="min-w-0 text-sm [overflow-wrap:anywhere]">
							{#if relatedRole}<Button variant="link" class="max-w-full !whitespace-normal [overflow-wrap:anywhere] !text-left" onclick={() => { query = ''; onSelect(relatedRole); }}>{relatedRole.name}</Button>
							{:else}<span class="text-ink-2">{t('roleDetail.missingRelated', { id })}</span>{/if}
						</li>
					{/each}
				</ul>
			{/if}
		{/snippet}
		<section aria-label={t('roleDetail.indirectChildrenLabel')} class="space-y-2">
			<h3 class="text-sm font-semibold text-ink-0">{t('roleDetail.indirectHeading', { count: inherited.length })}</h3>
			<p class="text-xs text-ink-2">{t('roleDetail.indirectHelp')}</p>
			{@render related(inherited, t('roleDetail.noIndirect'))}
		</section>
		<section aria-label={t('roleDetail.directParentsLabel')} class="space-y-2">
			<h3 class="text-sm font-semibold text-ink-0">{t('roleDetail.directParentsHeading', { count: role.parent_role_ids.length })}</h3>
			{@render related(role.parent_role_ids, t('roleDetail.noParents'))}
		</section>
	</div>
</SlidePanel>
