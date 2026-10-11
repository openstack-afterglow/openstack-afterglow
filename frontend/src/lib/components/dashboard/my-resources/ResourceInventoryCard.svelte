<script lang="ts">
	import { t } from '$lib/i18n/ns/dashboard-home';
	import { Button, Card, EmptyState, Pill, StatusChip } from '$lib/components/ui';
	import type { ProjectResourceInventory, ResourceCategory, ResourceTotal } from '$lib/types/userDashboard';

	let { category, projects, total, currentProjectId }: {
		category: ResourceCategory;
		projects: ProjectResourceInventory[];
		total: ResourceTotal;
		currentProjectId: string;
	} = $props();
	let expanded = $state(false);
	const items = $derived(projects.flatMap(project =>
		project.resources[category].state === 'ready' ? project.resources[category].items : []));
	const preview = $derived(expanded ? items : items.slice(0, 5));
</script>

<section data-resource-category={category} aria-labelledby={`resource-${category}`} class="min-w-0">
	<Card surface="base" class="h-full">
		<div class="flex flex-wrap items-center justify-between gap-2 mb-3">
			<h2 id={`resource-${category}`} class="text-sm font-semibold text-ink-0">{t(`myResources.category.${category}`)}</h2>
			<span data-resource-count class="text-xs tabular-nums text-ink-1">{total.state !== 'ready' || total.count === null ? t('myResources.unknown') : total.count}</span>
		</div>
		{#if total.state !== 'ready'}
			<p data-resource-total-state={total.state} class="text-xs text-ink-2 mb-3">
				{t(`myResources.state.${total.state}`)}
				{#if total.state === 'partial'}<span data-known-count> · {t('myResources.knownCount', { count: total.known_count })}</span>{/if}
			</p>
		{/if}
		{#if category === 'keypairs'}<p data-keypair-context class="text-xs text-ink-2 mb-3">{t('myResources.keypairContext')}</p>{/if}
		<ul class="space-y-2 mb-3" aria-label={t('myResources.projectStates')}>
			{#each projects as project (project.project_id)}
				{@const inventory = project.resources[category]}
				<li data-inventory-project={project.project_id} data-inventory-state={inventory.state} class="text-xs">
					<div class="flex flex-wrap items-center gap-2">
						<span class="text-ink-1 break-all">{project.project_name}</span>
						<Pill tone={inventory.state === 'failed' ? 'danger' : inventory.state === 'denied' ? 'warning' : 'neutral'}>{t(`myResources.state.${inventory.state}`)}</Pill>
						<span data-project-count class="ml-auto tabular-nums text-ink-2">{inventory.state !== 'ready' || inventory.count === null ? t('myResources.unknown') : inventory.count}</span>
					</div>
					{#if inventory.state === 'failed' && inventory.error}
						<p class="text-state-danger-text mt-1 break-words">{inventory.error}</p>
					{/if}
				</li>
			{/each}
		</ul>
		<ul id={`resource-items-${category}`} class="divide-y divide-line">
			{#each preview as item (`${item.project_id}:${item.owner_scope}:${item.owner_id}:${item.id}`)}
				<li data-resource-item={item.id} class="py-3 space-y-1">
					<div class="flex flex-wrap items-center justify-between gap-2">
						{#if item.project_id === currentProjectId}
							<a href={item.href} class="text-[13px] font-medium text-warm-text hover:text-warm-text-hover break-all">{item.name || item.id}</a>
						{:else}
							<span class="text-[13px] font-medium text-ink-0 break-all">{item.name || item.id}</span>
						{/if}
						<StatusChip status={item.status} />
					</div>
					<p class="text-xs text-ink-2 break-all">{category === 'keypairs' ? t('myResources.visibilityContext', { project: item.project_name }) : item.project_name} · {t(`myResources.owner.${item.owner_scope}`, { owner: item.owner_id })}</p>
					{#if category === 'volumes' && item.size !== undefined}
						<p data-resource-metadata class="text-xs text-ink-2">{item.size === null ? t('myResources.unknown') : `${item.size} GB`}{item.volume_type ? ` · ${item.volume_type}` : ''}</p>
					{/if}
					{#if item.project_id !== currentProjectId}
						<p data-select-project-first class="text-xs text-ink-2">{t(category === 'keypairs' ? 'myResources.selectContextFirst' : 'myResources.selectProjectFirst', { project: item.project_name })}</p>
					{/if}
				</li>
			{/each}
		</ul>
		{#if items.length === 0 && total.state === 'ready' && total.count === 0}
			<div data-resource-empty><EmptyState headline={t('myResources.emptyCategory')} class="py-6" /></div>
		{/if}
		{#if items.length > 5}
			<div data-resource-show-more class="mt-3">
				<Button variant="subtle" size="sm" ariaExpanded={expanded} ariaLabel={t(expanded ? 'myResources.showLessCategory' : 'myResources.showMoreCategory', { category: t(`myResources.category.${category}`) })} onclick={() => expanded = !expanded}>
					{expanded ? t('myResources.showLess') : t('myResources.showMore', { count: items.length - 5 })}
				</Button>
			</div>
		{/if}
	</Card>
</section>
