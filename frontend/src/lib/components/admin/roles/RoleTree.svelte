<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-identity';
	import Card from '$lib/components/ui/Card.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import RoleBadges from './RoleBadges.svelte';
	import { roleTreeRows } from './catalog';
	import type { ManagedRole, RoleSort, SortDirection } from './types';
	let { roles, query, sort, direction, onSelect }: {
		roles: ManagedRole[]; query: string; sort: RoleSort; direction: SortDirection;
		onSelect: (role: ManagedRole) => void;
	} = $props();
	const rows = $derived(roleTreeRows(roles, query, sort, direction));
	const knownIds = $derived(new Set(roles.map((role) => role.id)));
	const unknownEdges = $derived(roles.some((role) => role.implied_role_ids.some((id) => !knownIds.has(id))));
</script>

<Card surface="base" padding="md" class="min-w-0">
	<p class="mb-3 text-xs text-ink-2">{t('roleTree.help')}</p>
	{#if unknownEdges}<Alert tone="warning" class="mb-3">{t('roleTree.missingTargets')}</Alert>{/if}
	{#if rows.some((row) => row.kind === 'cycle')}<Alert tone="warning" class="mb-3">{t('roleTree.cycleWarning')}</Alert>{/if}
	<ul aria-label={t('roleTree.graphLabel')} class="min-w-0 divide-y divide-line">
		{#each rows as row (row.key)}
			<li class="min-w-0 py-3" style:padding-left={`${Math.min(row.depth, 4) * 0.75}rem`}>
				<div class="flex min-w-0 flex-wrap items-center gap-2">
					<span aria-hidden="true" class="text-ink-2">{row.parent ? '↳' : '•'}</span>
					<Button variant="link" class="min-w-0 max-w-full !whitespace-normal [overflow-wrap:anywhere] !text-left" ariaLabel={t('rolePage.detailLabel', { name: row.role.name })} onclick={() => onSelect(row.role)}>{row.role.name}</Button>
					<RoleBadges role={row.role} />
				</div>
				<div class="mt-1 space-y-1 text-xs text-ink-2 [overflow-wrap:anywhere]">
					<p class="font-mono">{row.role.id}</p>
					{#if row.parent}<p>{t('roleTree.directInheritance', { parent: row.parent.name, child: row.role.name, depth: row.depth })}</p>{:else if row.kind === 'component'}<p>{t('roleTree.rootlessEntry')}</p>{:else}<p>{t('roleTree.root')}</p>{/if}
					{#if row.kind === 'shared'}<p>{t('roleTree.shared')}</p>{/if}
					{#if row.kind === 'cycle'}<p>{t('roleTree.cycle')}</p>{/if}
					{#if !row.matches}<p>{t('roleTree.searchAncestor')}</p>{/if}
				</div>
			</li>
		{/each}
	</ul>
</Card>
