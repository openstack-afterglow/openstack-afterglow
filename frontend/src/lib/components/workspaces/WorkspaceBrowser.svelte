<script lang="ts">
	import { onMount } from 'svelte';
	import { derived } from 'svelte/store';
	import { auth, authReady, logoutInProgress, projectSwitching } from '$lib/stores/auth';
	import { sessionScopeKey } from '$lib/utils/authSession';
	import { createWorkspaceController } from '$lib/stores/workspaceController.svelte';
	import { sortWorkspaceResources, type ResourceKind } from '$lib/stores/workspacePreferences';
	import { t } from '$lib/i18n/ns/workspace-selector';
	import Button from '$lib/components/ui/Button.svelte';
	import { t as ta } from '$lib/i18n/ns/domain-auth';
	import Field from '$lib/components/ui/Field.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import SelectInput from '$lib/components/ui/SelectInput.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import CreateProjectModal from '$lib/components/projects/CreateProjectModal.svelte';

	let { onSelected, onClose, mockup = false, busy = $bindable(false) }: { onSelected: () => void; onClose: () => void; mockup?: boolean; busy?: boolean } = $props();
	const controller = createWorkspaceController(() => onSelected());
	const componentId = $props.id();
	let search = $state('');
	let domainSearch = $state('');
	// A fresh chooser shows authorized resources even before any recent/pinned history exists.
	let view = $state<'recent' | 'pinned' | 'all'>('all');
	let settings = $state(false);
	let createProject = $state(false);
	let projectSubmitting = $state(false);
	let createDomain = $state(false);
	let name = $state('');
	let description = $state('');
	const mutationBusy = $derived(controller.busy || projectSubmitting);
	const disabled = $derived(!controller.ready || controller.loading || mutationBusy || $projectSwitching);
	$effect(() => { busy = mutationBusy; });
	const orderedDomains = $derived(sortWorkspaceResources(controller.domains, controller.preferences.domains));
	const matchingDomains = $derived(orderedDomains.filter(row => (settings || !controller.preferences.domains[row.id]?.hidden || row.id === controller.domainId || row.id === $auth.domainId) && `${row.name} ${row.id}`.toLocaleLowerCase().includes(domainSearch.toLocaleLowerCase())));
	const orderedProjects = $derived(sortWorkspaceResources(controller.inventory?.projects ?? [], controller.preferences.projects, view === 'recent' && !settings));
	const views = ['recent', 'pinned', 'all'] as const;
	const projects = $derived(orderedProjects.filter(row => {
		const preference = controller.preferences.projects[row.id];
		return (settings || !preference?.hidden || row.id === $auth.projectId)
			&& (settings || view === 'all' || (view === 'pinned' ? preference?.pinned : preference?.visited))
			&& `${row.name} ${row.id} ${row.description ?? ''}`.toLocaleLowerCase().includes(search.toLocaleLowerCase());
	}));
	onMount(() => {
		const dispose = controller.mount();
		let previous = '';
		const unsubscribe = derived([auth, authReady, logoutInProgress], ([state, ready, loggingOut]) => JSON.stringify([sessionScopeKey(state), !!state.token, ready, loggingOut])).subscribe(key => {
			if (previous && key !== previous) {
				search = ''; domainSearch = ''; view = 'all'; settings = false;
				createProject = false; createDomain = false; name = ''; description = '';
			}
			previous = key;
		});
		return () => { unsubscribe(); dispose(); busy = false; };
	});
	function toggle(kind: ResourceKind, id: string, field: 'pinned' | 'hidden') {
		controller.preference(kind, id, { [field]: !controller.preferences[kind][id]?.[field] });
	}
	async function submitDomain(event: SubmitEvent) {
		event.preventDefault();
		if (!name.trim()) return;
		if (await controller.createDomain(name, description)) { createDomain = false; name = ''; description = ''; domainSearch = ''; }
	}
	function close() {
		if (!mutationBusy && !$projectSwitching) onClose();
	}
</script>

<div class="workspace-browser flex min-h-0 flex-col">
	<header class="shrink-0 space-y-3 border-b border-line p-4 md:p-5">
		<div class="flex flex-wrap items-center justify-between gap-2">
			<h2 class="text-lg font-semibold text-ink-0">{t('title')}</h2>
			<div class="flex flex-wrap gap-2">
				<Button variant="secondary" onclick={() => { settings = !settings; createDomain = false; }} ariaPressed={settings} disabled={mutationBusy}>{t('displaySettings')}</Button>
				<Button onclick={() => { createProject = true; }} disabled={disabled || mockup || !controller.inventory?.can_create_project}>{t('newProject')}</Button>
			</div>
		</div>
		<div class="text-xs text-ink-2" aria-live="polite">
			<p class="break-all">{ta('select.identityDomain')}: {$auth.identityDomainName || '—'} · {$auth.identityDomainId || '—'}</p>
			<p class="break-all">{t('activeDomain')}: {$auth.domainName || '—'} · {$auth.domainId || '—'}</p>
			<p class="break-all">{t('activeProject')}: {$auth.projectName || t('noProject')} · {$auth.projectId || '—'}</p>
		</div>
		<p class="text-xs text-ink-2">{t('browseHelp')}</p>
	</header>
	<div class="min-h-0 flex-1 overflow-y-auto p-4 md:p-5 space-y-4">
		{#if controller.error}<Alert tone="warning">{t(controller.error)}</Alert>{/if}
		{#if controller.storageFailed}<Alert tone="warning">{t('storageFailed')}</Alert>{/if}
		{#if controller.loading}<ActivityIndicator label={t('loading')} />{/if}
		<div class="grid grid-cols-1 gap-3 md:grid-cols-2">
			<Field label={t('domainSearch')} for={`${componentId}-domain-search`}><TextInput id={`${componentId}-domain-search`} bind:value={domainSearch} disabled={mutationBusy} /></Field>
			<Field label={t('domain')} for={`${componentId}-domain`}>
				<SelectInput id={`${componentId}-domain`} value={controller.domainId} disabled={controller.loading || mutationBusy || !controller.domains.length || $projectSwitching} onchange={(event) => { search = ''; void controller.selectDomain((event.currentTarget as HTMLSelectElement).value); }}>
					{#each matchingDomains as domain (domain.id)}<option value={domain.id}>{controller.preferences.domains[domain.id]?.pinned ? '★ ' : ''}{domain.name} · {domain.id}{domain.kind === 'personal' || domain.kind === 'organization' ? ` · ${t(domain.kind)}` : ''}</option>{/each}
				</SelectInput>
			</Field>
		</div>
		{#if settings}
			<p class="text-sm text-ink-2">{t('preferencesHelp')}</p>
			<h3 class="text-sm font-medium">{t('domains')}</h3>
			<ul class="divide-y divide-line rounded-lg border border-line">
				{#each matchingDomains as domain, index (domain.id)}
					<li class="flex flex-wrap items-center gap-2 p-3">
						<div class="min-w-0 flex-1"><p class="break-all text-sm">{domain.name}</p><p class="break-all font-mono text-xs text-ink-2">{domain.id}</p>{#if domain.kind === 'personal' || domain.kind === 'organization'}<p class="text-xs text-ink-2">{t(domain.kind)}</p>{/if}</div>
						{@render controls('domains', domain.id, domain.name, matchingDomains, index)}
					</li>
				{/each}
			</ul>
		{/if}
		{#if createDomain}
			<form class="space-y-3 rounded-lg border border-line p-4" onsubmit={submitDomain}>
				<h3 class="text-sm font-medium">{t('newDomain')}</h3>
				<Field label={t('domainName')} for={`${componentId}-domain-name`} required><TextInput id={`${componentId}-domain-name`} bind:value={name} required maxlength={64} disabled={mutationBusy || controller.uncertain} /></Field>
				<Field label={t('description')} for={`${componentId}-description`}><TextInput id={`${componentId}-description`} bind:value={description} maxlength={255} disabled={mutationBusy || controller.uncertain} /></Field>
				<div class="flex flex-wrap justify-end gap-2">
					<Button variant="secondary" onclick={() => { createDomain = false; }} disabled={mutationBusy}>{t('cancel')}</Button>
					<Button type="submit" disabled={disabled || controller.uncertain || !name.trim() || !$auth.canCreateDomain}>{t('create')}</Button>
				</div>
			</form>
		{/if}
		{#if !settings}
			<div class="flex flex-wrap gap-2" role="group" aria-label={t('views')}>
				{#each views as tab}<Button variant={view === tab ? 'secondary' : 'ghost'} ariaPressed={view === tab} onclick={() => { view = tab; }} disabled={mutationBusy}>{t(tab)}</Button>{/each}
			</div>
		{/if}
		<Field label={t('projectSearch')} for={`${componentId}-project-search`}><TextInput id={`${componentId}-project-search`} bind:value={search} disabled={mutationBusy} /></Field>
		{#if controller.ready && !controller.loading}
			{#if !projects.length}<p class="py-4 text-sm text-ink-2">{t('empty')}</p>{/if}
			<ul class="divide-y divide-line rounded-lg border border-line" aria-label={t('projects')}>
				{#each projects as project, index (project.id)}
					<li class="flex flex-wrap items-center gap-2 p-3 {project.id === $auth.projectId && controller.domainId === $auth.domainId ? 'bg-surface-selected' : ''}">
						<button type="button" class="min-h-11 min-w-0 flex-1 rounded-md text-left focus-visible:outline-none focus-visible:shadow-[var(--focus-ring)] disabled:opacity-50" onclick={() => controller.select(project.id)} disabled={disabled || mockup}>
							<span class="block break-all text-sm font-medium">{project.name}{project.id === $auth.projectId && controller.domainId === $auth.domainId ? ` · ${t('current')}` : ''}</span>
							<span class="block break-all font-mono text-xs text-ink-2">{project.id}</span>
							{#if project.description}<span class="block break-words text-xs text-ink-2">{project.description}</span>{/if}
						</button>
						{@render controls('projects', project.id, project.name, projects, index)}
					</li>
				{/each}
			</ul>
		{/if}
		{#if mockup}<Alert tone="neutral">{t('tutorialUnavailable')}</Alert>{/if}
	</div>
	<footer class="shrink-0 flex flex-wrap items-center justify-between gap-2 border-t border-line p-4">
		<div class="flex flex-wrap gap-2">
			<Button variant="secondary" onclick={() => { void controller.refresh(); }} disabled={mutationBusy || $projectSwitching}>{t('refresh')}</Button>
			{#if $auth.canCreateDomain && !mockup}<Button variant="secondary" onclick={() => { createDomain = !createDomain; }} disabled={disabled || controller.uncertain}>{t('newDomain')}</Button>{/if}
			{#if controller.inventory?.is_domain_manager && controller.inventory.domain.kind !== 'personal' && !mockup}<Button variant="secondary" onclick={() => controller.select(null)} disabled={disabled}>{t('useDomain')}</Button>{/if}
			{#if $auth.projectId}<Button variant="link" href="/dashboard/project-settings" onclick={close} disabled={mutationBusy || $projectSwitching}>{t('projectSettings')}</Button>{/if}
		</div>
		<Button variant="secondary" onclick={close} disabled={mutationBusy || $projectSwitching}>{t('close')}</Button>
	</footer>
</div>

{#snippet controls(kind: ResourceKind, id: string, resourceName: string, rows: { id: string }[], index: number)}
	<div class="flex flex-wrap gap-1">
		<Button variant="ghost" class="min-h-11" ariaPressed={controller.preferences[kind][id]?.pinned === true} ariaLabel={t(controller.preferences[kind][id]?.pinned ? 'unpinResource' : 'pinResource', { name: resourceName, id })} onclick={() => toggle(kind, id, 'pinned')} disabled={disabled}>{controller.preferences[kind][id]?.pinned ? '★' : '☆'}</Button>
		{#if settings}
			<Button variant="secondary" class="min-h-11" onclick={() => toggle(kind, id, 'hidden')} disabled={disabled} ariaLabel={t(controller.preferences[kind][id]?.hidden ? 'showResource' : 'hideResource', { name: resourceName, id })}>{t(controller.preferences[kind][id]?.hidden ? 'show' : 'hide')}</Button>
			<Button variant="ghost" class="min-h-11" ariaLabel={t('moveUpResource', { name: resourceName, id })} onclick={() => controller.reorder(kind, rows, index, -1)} disabled={disabled || index === 0}>↑</Button>
			<Button variant="ghost" class="min-h-11" ariaLabel={t('moveDownResource', { name: resourceName, id })} onclick={() => controller.reorder(kind, rows, index, 1)} disabled={disabled || index === rows.length - 1}>↓</Button>
		{/if}
	</div>
{/snippet}

{#if createProject && controller.inventory && !mockup}
	<CreateProjectModal bind:submitting={projectSubmitting} domainId={controller.domainId} domainName={controller.inventory.domain.name} onClose={() => { createProject = false; void controller.refresh(); }} onSuccess={() => { createProject = false; void controller.refresh(); }} />
{/if}

<style>
	.workspace-browser { height: min(46rem, calc(100dvh - 2rem)); width: min(56rem, calc(100vw - 2rem)); color: var(--color-ink-0); }
</style>
