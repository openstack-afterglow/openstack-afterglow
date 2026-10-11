<script lang="ts">
	import { t } from '$lib/i18n/ns/dashboard-home';
	import { TableShell } from '$lib/components/ui';
	import { RESOURCE_CATEGORIES } from '$lib/types/userDashboard';
	import type { ProjectResourceInventory } from '$lib/types/userDashboard';

	let { projects }: { projects: ProjectResourceInventory[] } = $props();
</script>

{#if projects.length > 0}
	<section data-project-usage class="min-w-0 mb-5" aria-labelledby="project-usage-title">
		<h2 id="project-usage-title" class="text-sm font-semibold text-ink-0 mb-3">{t('projectUsage.title')}</h2>
		<p class="text-xs text-ink-2 mb-3">{t('myResources.keypairContext')}</p>
		<div data-project-usage-scroll role="region" aria-label={t('myResources.usageScroll')} tabindex="0" class="min-w-0 overflow-x-auto rounded-lg focus-visible:outline-2 focus-visible:outline-accent">
			<TableShell density="compact" class="min-w-max">
				<table class="min-w-max">
					<thead><tr>
						<th scope="col">{t('projectUsage.project')}</th>
						{#each RESOURCE_CATEGORIES as category (category)}<th scope="col">{t(`myResources.category.${category}`)}</th>{/each}
						<th scope="col">{t('myResources.usage.vcpus')}</th>
						<th scope="col">{t('myResources.usage.ram_mb')}</th>
						<th scope="col">{t('myResources.usage.storage_gb')}</th>
					</tr></thead>
					<tbody>
						{#each projects as project (project.project_id)}
							<tr data-usage-project={project.project_id}>
								<th scope="row" class="text-ink-0">{project.project_name}</th>
								{#each RESOURCE_CATEGORIES as category (category)}
									{@const inventory = project.resources[category]}
									<td data-usage-category={category} data-usage-state={inventory.state} class="tabular-nums whitespace-nowrap">
									{inventory.state !== 'ready' || inventory.count === null ? t('myResources.unknown') : inventory.count}
										{#if inventory.state !== 'ready'}<span class="text-ink-2"> · {t(`myResources.state.${inventory.state}`)}</span>{/if}
									</td>
								{/each}
								{#each ['vcpus', 'ram_mb', 'storage_gb'] as metric}
									{@const value = project.usage[metric as keyof typeof project.usage]}
									<td data-usage-metric={metric} class="tabular-nums whitespace-nowrap">{value === null ? t('myResources.unknown') : value}</td>
								{/each}
							</tr>
						{/each}
					</tbody>
				</table>
			</TableShell>
		</div>
	</section>
{/if}
