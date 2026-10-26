<script lang="ts">
	import { untrack } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { domainsApi, type AdminDomain } from '$lib/api/domains';
	import { ApiError } from '$lib/api/client';
	import { projectNames, type AdminProjectName } from '$lib/stores/projectNames';
	import { Alert, Button, Field, SearchSelect } from '$lib/components/ui';
	import { t } from '$lib/i18n/ns/domain-admin';

	let { domainId = '', projectId = '', emptyProjectLabel, disabled = false, excludedProjectIds = [], selectProjectDomain = false, onchange }: {
		domainId?: string; projectId?: string; emptyProjectLabel?: string; disabled?: boolean; excludedProjectIds?: readonly string[]; selectProjectDomain?: boolean;
		onchange: (domainId: string, projectId: string, projectName: string) => void;
	} = $props();
	const id = $props.id();
	let domains = $state<AdminDomain[]>([]);
	let projects = $state<readonly AdminProjectName[]>([]);
	let loading = $state(true);
	let domainError = $state('');
	let projectError = $state('');
	let refreshRevision = $state(0);
	const authority = $derived(JSON.stringify([$auth.sessionId, $auth.userId, $auth.identityDomainId, $auth.domainId, $auth.projectId, $auth.isSystemAdmin, $auth.isDomainManager, !!$auth.token]));
	const visibleProjects = $derived(projects.filter(project => (!domainId || project.domain_id === domainId) && !excludedProjectIds.includes(project.id)));
	const invalidDomain = $derived(!loading && !domainError && !!domainId && !domains.some(domain => domain.id === domainId));
	const invalidProject = $derived(!loading && !projectError && !!projectId && !projects.some(project => project.id === projectId && (!domainId || project.domain_id === domainId)));
	$effect(() => {
		const owner = authority;
		const refresh = refreshRevision > 0;
		let alive = true;
		const { token, activeProjectId, userId } = untrack(() => ({ token: $auth.token ?? undefined, activeProjectId: $auth.projectId ?? undefined, userId: $auth.userId ?? undefined }));
		untrack(() => { domains = []; projects = []; loading = true; domainError = ''; projectError = ''; });
		if (!token) { loading = false; return () => { alive = false; }; }
		const owns = () => alive && owner === authority;
		void Promise.all([
			domainsApi.list({ token, projectId: activeProjectId }, { refresh }).then(response => {
				if (owns()) domains = response.items;
			}).catch(reason => { if (owns()) domainError = reason instanceof ApiError ? reason.message : t('scope.loadFailed'); }),
			projectNames.loadMetadata(token, activeProjectId, userId, refresh).then(response => {
				if (!owns()) return;
				projects = response.projects;
				if (response.failed) { projectError = response.error instanceof ApiError ? response.error.message : t('scope.projectsFailed'); return; }
			}).catch(reason => { if (owns()) projectError = reason instanceof ApiError ? reason.message : t('scope.projectsFailed'); }),
		]).finally(() => { if (owns()) loading = false; });
		return () => { alive = false; };
	});
	function chooseDomain(value: string) {
		const selected = projects.find(project => project.id === projectId);
		const compatible = !value || selected?.domain_id === value;
		onchange(value, compatible ? projectId : '', compatible ? selected?.name ?? '' : '');
	}
</script>

<div class="flex flex-wrap items-end gap-3">
	<Field for={`${id}-domain`} label={t('scope.domain')} class="w-full sm:flex-1 sm:min-w-48 min-w-0">
		<SearchSelect id={`${id}-domain`} value={domainId}
			options={[{ value: '', label: t('scope.allDomains') }, ...domains.map(domain => ({ value: domain.id, label: domain.name, description: domain.id }))]}
			{loading} disabled={disabled || loading || !!domainError} placeholder={domainId || t('scope.allDomains')} ariaLabel={t('scope.domain')} onchange={chooseDomain} />
	</Field>
	<Field for={`${id}-project`} label={t('scope.project')} class="w-full sm:flex-1 sm:min-w-48 min-w-0">
		<SearchSelect id={`${id}-project`} value={projectId}
			options={[{ value: '', label: emptyProjectLabel ?? t('scope.allProjects') }, ...visibleProjects.map(project => ({ value: project.id, label: project.name, description: project.id }))]}
			{loading} disabled={disabled || loading || !!projectError} placeholder={projectId || emptyProjectLabel || t('scope.allProjects')} ariaLabel={t('scope.project')}
			onchange={(value) => { const project = projects.find(project => project.id === value); onchange(domainId || (selectProjectDomain ? project?.domain_id ?? '' : ''), value, project?.name ?? ''); }} />
	</Field>
	<Button variant="secondary" size="sm" disabled={disabled || loading} onclick={() => refreshRevision += 1}>{t('actions.refresh')}</Button>
</div>
{#if domainError}<Alert class="mt-3">{domainError}</Alert>{/if}
{#if projectError}<Alert class="mt-3">{projectError}</Alert>{/if}
{#if invalidDomain}<Alert class="mt-3">{t('scope.invalid')}</Alert>{/if}
{#if invalidProject}<Alert class="mt-3">{t('scope.project')}: {projectId} · {t('state.unavailable')}</Alert>{/if}
