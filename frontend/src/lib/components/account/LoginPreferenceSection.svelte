<script lang="ts">
	import { onMount } from 'svelte';
	import { get } from 'svelte/store';
	import { api } from '$lib/api/client';
	import { auth, authReady, logoutInProgress, projectSwitching } from '$lib/stores/auth';
	import { sessionScopeKey } from '$lib/utils/authSession';
	import { t } from '$lib/i18n/ns/account';
	import { Alert, Button, Card, Field, SelectInput } from '$lib/components/ui';
	import type { AvailableDomain } from '$lib/types/auth';
	import type { WorkspaceInventory, WorkspaceProject } from '$lib/stores/workspaceController.svelte';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	const uid = $props.id();
	const readOptions = { refresh: true, cache: 'no-store' as const, replayOnUnauthorized: false };
	let choiceEpoch = 0;
	let domains = $state<AvailableDomain[]>([]);
	let projects = $state<WorkspaceProject[]>([]);
	let domainId = $state('');
	let projectId = $state('');
	let choicesLoading = $state(false);
	let mounted = false;
	let epoch = 0;
	let loaded = $state(false);
	let enabled = $state(true);
	let busy = $state(false);
	let error = $state('');
	let saved = $state(false);
	const blocked = $derived(!$authReady || $logoutInProgress || $projectSwitching || !$auth.token || !loaded || busy);
	const fixedReady = $derived(domains.some(row => row.id === domainId) && projects.some(row => row.id === projectId));
	function capture() {
		const state = get(auth), ticket = epoch;
		if (!mounted || !state.token || !get(authReady) || get(logoutInProgress) || get(projectSwitching)) return null;
		return { token: state.token, project: state.projectId ?? undefined,
			current: () => mounted && epoch === ticket && get(authReady) && !get(logoutInProgress) && !get(projectSwitching) };
	}
	async function loadProjects(selected: string, savedProject = '') {
		const owner = capture(); if (!owner) return;
		const ticket = ++choiceEpoch;
		projects = []; projectId = ''; choicesLoading = true; error = ''; saved = false;
		if (!selected) { choicesLoading = false; return; }
		try {
			const result = await api.get<WorkspaceInventory>(`/api/v1/auth/workspaces?domain_id=${encodeURIComponent(selected)}`, owner.token, undefined, readOptions);
			if (owner.current() && ticket === choiceEpoch && !enabled) {
				projects = result.projects;
				projectId = projects.some(row => row.id === savedProject) ? savedProject : '';
			}
		} catch { if (owner.current() && ticket === choiceEpoch && !enabled) error = t('loginPreference.failed'); }
		finally { if (owner.current() && ticket === choiceEpoch) choicesLoading = false; }
	}
	async function loadChoices(savedDomain = '', savedProject = '') {
		const owner = capture(); if (!owner) return;
		const ticket = ++choiceEpoch;
		domains = []; projects = []; domainId = ''; projectId = ''; choicesLoading = true;
		try {
			const result = await api.get<AvailableDomain[]>('/api/v1/auth/domains', owner.token, undefined, readOptions);
			if (!owner.current() || ticket !== choiceEpoch || enabled) return;
			domains = result;
			domainId = domains.some(row => row.id === savedDomain) ? savedDomain : '';
			if (domainId) await loadProjects(domainId, savedProject);
		} catch { if (owner.current() && ticket === choiceEpoch && !enabled) error = t('loginPreference.failed'); }
		finally { if (owner.current() && ticket === choiceEpoch) choicesLoading = false; }
	}
	function changeMode(event: Event) {
		enabled = (event.currentTarget as HTMLInputElement).checked;
		choiceEpoch++; choicesLoading = false; error = ''; saved = false;
		if (!enabled) void loadChoices(domainId, projectId);
	}
	async function load() {
		const owner = capture(); if (!owner) return;
		busy = true; loaded = false; error = ''; saved = false;
		try {
			const result = await api.get<{ remember_last_workspace: boolean; domain_id?: string; project_id?: string }>('/api/v1/profile/login-preference', owner.token, owner.project, readOptions);
			if (owner.current()) {
				enabled = result.remember_last_workspace; loaded = true;
				if (!enabled) await loadChoices(result.domain_id, result.project_id);
			}
		} catch { if (owner.current()) error = t('loginPreference.failed'); }
		finally { if (owner.current()) busy = false; }
	}
	async function save() {
		if (blocked || (!enabled && (choicesLoading || !fixedReady))) return;
		const owner = capture(); if (!owner) return;
		busy = true; error = ''; saved = false;
		try {
			await api.put('/api/v1/profile/login-preference', { remember_last_workspace: enabled, ...(!enabled ? { domain_id: domainId, project_id: projectId } : {}) }, owner.token, owner.project, { cache: 'no-store', replayOnUnauthorized: false });
			if (owner.current()) saved = true;
		} catch { if (owner.current()) { error = t('loginPreference.failed'); loaded = false; } }
		finally { if (owner.current()) busy = false; }
	}
	onMount(() => {
		mounted = true; let previous = '';
		const changed = () => {
			const state = get(auth);
			const next = JSON.stringify([sessionScopeKey(state), get(authReady), get(logoutInProgress), get(projectSwitching)]);
			if (next === previous) return;
			previous = next; epoch++; choiceEpoch++; enabled = true; loaded = false; busy = false; error = ''; saved = false;
			domains = []; projects = []; domainId = ''; projectId = ''; choicesLoading = false;
			void load();
		};
		const unsubscribers = [auth.subscribe(changed), authReady.subscribe(changed), logoutInProgress.subscribe(changed), projectSwitching.subscribe(changed)];
		return () => { mounted = false; epoch++; unsubscribers.forEach(unsubscribe => unsubscribe()); };
	});
</script>

<Card class="p-5 space-y-4">
	<h2 class="text-sm font-semibold text-ink-0">{t('loginPreference.title')}</h2>
	<p class="text-sm text-ink-2">{t('loginPreference.help')}</p>
	{#if busy}<LoadingState variant={loaded ? 'inline' : 'section'} label={t('loginPreference.loading')}  />{/if}
	{#if error}<Alert flat tone="danger">{error} <Button variant="secondary" disabled={busy || !$authReady || $logoutInProgress || $projectSwitching} onclick={load}>{t('loginPreference.reload')}</Button></Alert>{/if}
	{#if saved}<Alert flat tone="success">{t('loginPreference.saved')}</Alert>{/if}
	<label class="flex min-h-11 items-center gap-3 text-sm"><input type="checkbox" bind:checked={enabled} disabled={blocked} onchange={changeMode} />{t('loginPreference.remember')}</label>
	{#if !enabled && loaded}
		<p class="text-sm text-ink-2">{t('loginPreference.fixedHelp')}</p>
		{#if choicesLoading}<LoadingState variant="inline" label={t('loginPreference.loading')} />{/if}
		<div class="grid gap-3 md:grid-cols-2">
			<Field label={t('loginPreference.domain')} for={`${uid}-domain`}>
				<SelectInput id={`${uid}-domain`} bind:value={domainId} disabled={blocked || choicesLoading} onchange={event => { domainId = (event.currentTarget as HTMLSelectElement).value; void loadProjects(domainId); }}>
					<option value="">{t('loginPreference.selectDomain')}</option>
					{#each domains as row (row.id)}<option value={row.id}>{row.name} · {row.id}</option>{/each}
				</SelectInput>
			</Field>
			<Field label={t('loginPreference.project')} for={`${uid}-project`}>
				<SelectInput id={`${uid}-project`} bind:value={projectId} disabled={blocked || choicesLoading || !domainId} onchange={() => { saved = false; }}>
					<option value="">{t('loginPreference.selectProject')}</option>
					{#each projects as row (row.id)}<option value={row.id}>{row.name} · {row.id}</option>{/each}
				</SelectInput>
			</Field>
		</div>
	{/if}
	<Button variant="secondary" disabled={blocked || (enabled ? !$auth.projectId : choicesLoading || !fixedReady)} onclick={save}>{t('loginPreference.save')}</Button>
</Card>
