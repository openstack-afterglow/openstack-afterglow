<script lang="ts">
	import { onMount, onDestroy, untrack } from 'svelte';
	import { ApiError } from '$lib/api/client';
	import type { IamSession } from '$lib/api/domainIam';
	import { workspaceIam, type IamResourceWorkspace } from '$lib/api/workspaceIam';
	import { t } from '$lib/i18n/ns/workspace-iam';
	import { resourceLabel, observationLabel } from './workspaceLabels';
	import Button from '$lib/components/ui/Button.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import SelectInput from '$lib/components/ui/SelectInput.svelte';
	import TableShell from '$lib/components/ui/TableShell.svelte';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import ResourceMetricTable from './ResourceMetricTable.svelte';
	let { session, blocked = false, onDenied }: { session: IamSession; blocked?: boolean; onDenied: () => void } = $props();
	const client = untrack(() => workspaceIam(session));
	let live = true;
	let generation = 0;
	let data = $state<IamResourceWorkspace | null>(null);
	let loading = $state(true);
	let error = $state('');
	let view = $state<'domain' | 'project' | 'user'>('domain');
	let projectId = $state('');
	let userId = $state('');
	const project = $derived(data?.projects.find(row => row.id === projectId));
	const user = $derived(data?.users.find(row => row.id === userId));
	const metrics = $derived(view === 'domain' ? data?.resources : view === 'project' ? project?.resources : user?.resources);
	const inventory = $derived(data?.inventory.filter(row => view === 'domain' || (view === 'project' ? row.project_id === projectId : row.user_id === userId)) ?? []);
	async function load() {
		if (blocked || loading && data || !session.isCurrent()) return;
		const pending = ++generation;
		loading = true; error = ''; data = null;
		try {
			const result = await client.resources();
			if (!live || pending !== generation) return;
			if (result.domain.id !== session.domainId) throw new Error(t('scopeMismatch'));
			data = result;
			if (!result.projects.some(row => row.id === projectId)) projectId = result.projects[0]?.id ?? '';
			if (!result.users.some(row => row.id === userId)) userId = result.users[0]?.id ?? '';
		} catch (cause) {
			if (!live || pending !== generation || !session.isCurrent()) return;
			error = cause instanceof Error ? cause.message : t('loadFailed');
			if (cause instanceof ApiError && cause.status === 403) onDenied();
		} finally { if (live && pending === generation) loading = false; }
	}
	onMount(() => { void load(); });
	onDestroy(() => { live = false; generation++; data = null; projectId = ''; userId = ''; });
</script>

<div class="space-y-4">
	<div class="flex flex-wrap items-center gap-2"><h2 class="mr-auto text-lg font-semibold text-ink-0">{t('resources')}</h2><Button variant="secondary" disabled={loading || blocked} onclick={load}>{t('reload')}</Button></div>
	<Alert tone="info">{t('attributionHelp')}</Alert>
	{#if error}<Alert tone="danger">{error}</Alert>{/if}
	{#if loading}<ActivityIndicator label={t('loading')} />{/if}
	{#if data}
		<Alert tone={data.coverage.partial ? 'warning' : 'info'}>{t('coverage')}: {t(data.coverage.partial ? 'state.partial' : 'state.ready')} · {t('observedAt')}: {data.coverage.observed_at}</Alert>
		<div class="flex flex-wrap gap-2" role="group" aria-label={t('attributionScope')}>
			{#each ['domain', 'project', 'user'] as scope}<Button variant={view === scope ? 'secondary' : 'ghost'} ariaPressed={view === scope} onclick={() => view = scope as typeof view}>{t(`scope.${scope as typeof view}`)}</Button>{/each}
		</div>
		{#if view === 'project'}
			<SelectInput bind:value={projectId} ariaLabel={t('project')}><option value="">{t('chooseProject')}</option>{#each data.projects as row (row.id)}<option value={row.id}>{row.name || row.id} · {row.id}{row.enabled ? '' : ` · ${t('disabled')}`}</option>{/each}</SelectInput>
		{:else if view === 'user'}
			<SelectInput bind:value={userId} ariaLabel={t('user')}><option value="">{t('chooseUser')}</option>{#each data.users as row (row.id)}<option value={row.id}>{row.name || row.id} · {row.id}{row.enabled ? '' : ` · ${t('disabled')}`}</option>{/each}</SelectInput>
			<Alert tone="info">{t('userQuotaHelp')}</Alert>
			{#if user}<div class="rounded-lg border border-line p-3 text-sm text-ink-1 [overflow-wrap:anywhere]"><p>{t('identityDomain')}: <code>{user.domain_id}</code></p><p>{t('memberships')}: {observationLabel(user.membership_state)}</p><ul>{#each user.project_ids as id}<li>{data.projects.find(row => row.id === id)?.name || id} · <code>{id}</code></li>{:else}<li>{user.membership_state === 'ready' ? t('noMemberships') : t('unknown')}</li>{/each}</ul></div>{/if}
		{/if}
		{#if metrics}<ResourceMetricTable {metrics} />{:else}<p class="text-sm text-ink-2">{t('chooseScope')}</p>{/if}
		<section class="space-y-2">
			<h3 class="text-sm font-semibold text-ink-0">{t('inventory')}</h3>
			<p class="text-sm text-ink-2">{t('inventoryHelp')}</p>
			<TableShell><table><thead><tr><th>{t('metric')}</th><th>{t('nameId')}</th><th>{t('project')}</th><th>{t('user')}</th><th>{t('status')}</th></tr></thead><tbody>{#each inventory as row}<tr><td>{resourceLabel(row.category)}</td><td>{row.name || '—'}<code class="block text-xs text-ink-2">{row.id ?? t('unknown')}</code></td><td>{data.projects.find(project => project.id === row.project_id)?.name || row.project_id}<code class="block text-xs text-ink-2">{row.project_id}</code></td><td>{row.user_id ? data.users.find(user => user.id === row.user_id)?.name || row.user_id : t('unattributed')}<code class="block text-xs text-ink-2">{row.user_id ?? ''}</code></td><td>{row.status ?? t('unknown')}</td></tr>{:else}<tr><td colspan="5">{t('noObservations')}</td></tr>{/each}</tbody></table></TableShell>
		</section>
		{#if data.coverage.notes.length}<details><summary class="cursor-pointer text-sm text-ink-1">{t('coverageNotes')}</summary><ul class="list-disc space-y-1 pl-5 text-sm text-ink-2">{#each data.coverage.notes as note}<li><code>{note}</code></li>{/each}</ul></details>{/if}
	{/if}
</div>
