<script lang="ts">
	import { t } from '$lib/i18n/ns/topology';
	import Button from '$lib/components/ui/Button.svelte';
	import StatusChip from '$lib/components/ui/StatusChip.svelte';
	import ResourceIdentifier from '$lib/components/ui/ResourceIdentifier.svelte';
	import { domainGroupLabel } from '../domainGroups';
	import { matchesQuery, switchId } from './topologyGraph';
	import type { CanvasGraph, CanvasNet, CanvasNode } from './types';

	let { graph, query, onopen }: { graph: CanvasGraph; query: string; onopen: (id: string) => void } = $props();
	type Project = { id: string | null; name: string | null; nets: CanvasNet[]; nodes: CanvasNode[] };
	const groups = $derived.by(() => {
		const domains = new Map<string, { id: string; label: string; projects: Map<string, Project> }>();
		const projects = new Map<string, Project>();
		for (const domain of graph.domainGroups ?? []) {
			const group = { id: domain.id, label: domainGroupLabel(domain), projects: new Map<string, Project>() };
			domains.set(group.id, group);
			for (const netId of domain.netIds) {
				const net = graph.netById.get(netId);
				if (!net) continue;
				const key = net.project_id ?? 'owner:unknown';
				let project = group.projects.get(key);
				if (!project) {
					project = { id: net.project_id, name: net.raw.project_name ?? null, nets: [], nodes: [] };
					if ((net.project_id && (!projects.has(key) || net.raw.owner_status === 'known')) || (!net.project_id && group.id === 'owner:unknown')) projects.set(key, project);
					group.projects.set(key, project);
				}
				project.nets.push(net);
			}
		}
		for (const node of graph.nodes.values()) {
			if (node.kind === 'switch' || node.kind === 'internet') continue;
			const id = node.kind === 'vm' ? node.meta.project_id : node.raw.project_id;
			const key = id ?? 'owner:unknown';
			let project = projects.get(key);
			if (!project) {
				// An attached shared network's owner is not the resource's owner domain.
				const groupId = id ? `project:${id}` : 'owner:unknown';
				let domain = domains.get(groupId);
				if (!domain) {
					domain = { id: groupId, label: t('domain.unknown'), projects: new Map() };
					domains.set(groupId, domain);
				}
				project = { id, name: null, nets: [], nodes: [] };
				projects.set(key, project);
				domain.projects.set(key, project);
			}
			project.nodes.push(node);
		}
		const q = query.trim().toLocaleLowerCase();
		const matches = matchesQuery(graph, query);
		return [...domains.values()].sort((a, b) => a.label.localeCompare(b.label)).map((domain) => ({
			...domain,
			projects: [...domain.projects.values()].sort((a, b) => (a.name ?? a.id ?? '').localeCompare(b.name ?? b.id ?? '')).filter((project) =>
				!q || domain.label.toLocaleLowerCase().includes(q) || `${project.name ?? ''} ${project.id ?? ''}`.toLocaleLowerCase().includes(q)
				|| project.nets.some((net) => matches?.nets.has(net.id)) || project.nodes.some((node) => matches?.nodes.has(node.id))),
		})).filter((domain) => domain.projects.length > 0);
	});
</script>

<section class="overview" aria-label={t('overview.title')}>
	<p class="overview-note">{t('overview.description')}</p>
	{#each groups as domain (domain.id)}
		<section class="domain" data-overview-domain={domain.id}>
			<h3>{domain.label}</h3>
			{#each domain.projects as project (project.id)}
				<details class="project" data-overview-project={project.id ?? 'owner:unknown'} open={Boolean(query.trim())}>
					<summary>
						<span class="owner"><strong>{project.name ?? t('domain.unknown')}</strong>{#if project.id}<ResourceIdentifier id={project.id} />{/if}</span>
						<span class="counts">{t('summary.networks', { count: project.nets.length })} · {t('summary.instances', { count: project.nodes.filter((node) => node.kind === 'vm').length })} · {t('summary.routers', { count: project.nodes.filter((node) => node.kind === 'router').length })} · {t('summary.loadBalancers', { count: project.nodes.filter((node) => node.kind === 'lb').length })}</span>
					</summary>
					<div class="resources">
						{#each project.nets as net (net.id)}
							<div class="resource" data-overview-network={net.id}><Button variant="link" size="sm" onclick={() => onopen(switchId(net.id))}>{net.name || net.id}</Button><span>{t(net.kind === 'external' ? 'network.external' : net.kind === 'shared' ? 'network.shared' : 'network.internal')}</span><span class="identifier">{net.cidrs.join(' · ')}</span><StatusChip status={net.status} /></div>
						{/each}
						{#each project.nodes as node (node.id)}
							<div class="resource" data-overview-resource={node.id}><Button variant="link" size="sm" onclick={() => onopen(node.id)}>{node.name || node.id}</Button><span>{t(node.kind === 'vm' ? 'resource.instance' : node.kind === 'router' ? 'resource.router' : 'resource.loadBalancer')}</span><StatusChip status={node.status} /></div>
						{/each}
					</div>
				</details>
			{/each}
		</section>
	{:else}
		<p class="overview-note">{t(query.trim() ? 'canvas.noResults' : 'empty.resources')}</p>
	{/each}
</section>

<style>
	.overview { display: grid; gap: 1rem; max-height: 68dvh; overflow: auto; }
	.overview-note { margin: 0; color: var(--color-ink-2); font-size: 0.8125rem; }
	.domain { border: 1px solid var(--color-line-2); border-radius: var(--radius-lg); padding: 1rem; background: var(--color-surface-base); }
	h3 { margin: 0 0 0.75rem; color: var(--color-ink-1); font-size: 0.875rem; font-weight: 600; overflow-wrap: anywhere; }
	.project + .project { border-top: 1px solid var(--color-line-2); }
	summary { padding: 0.75rem 0; cursor: pointer; min-height: 44px; color: var(--color-ink-1); }
	summary:focus-visible { outline: none; box-shadow: var(--focus-ring); }
	.owner { display: inline-flex; flex-wrap: wrap; gap: 0.375rem 0.75rem; max-width: 100%; vertical-align: middle; font-size: 0.875rem; }
	.owner strong { min-width: 0; overflow-wrap: anywhere; }
	.identifier { font-family: var(--font-mono); font-size: 0.75rem; color: var(--color-ink-2); overflow-wrap: anywhere; }
	.counts { display: block; margin: 0.375rem 0 0 1rem; color: var(--color-ink-2); font-size: 0.8125rem; font-variant-numeric: tabular-nums; }
	.resources { padding: 0 0 0.75rem 1rem; }
	.resource { display: flex; flex-wrap: wrap; align-items: center; gap: 0.375rem 0.75rem; min-height: 44px; font-size: 0.8125rem; color: var(--color-ink-2); }
	.resource :global(.btn) { white-space: normal; overflow-wrap: anywhere; text-align: left; }
	@media (max-width: 767px) { .domain { padding: 0.75rem; } .resource { padding-block: 0.375rem; } }
</style>
