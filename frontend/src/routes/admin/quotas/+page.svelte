<script lang="ts">
	import PageShell from '$lib/components/ui/PageShell.svelte';
	import { onMount, tick } from 'svelte';
	import { get } from 'svelte/store';
	import { auth, authReady, projectSwitching, logoutInProgress } from '$lib/stores/auth';
	import { createAdminQuotasController } from '$lib/stores/adminQuotasController.svelte';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import ProjectSelector from '$lib/components/admin/quotas/ProjectSelector.svelte';
	import ProjectQuotaForm from '$lib/components/admin/quotas/ProjectQuotaForm.svelte';
	import { t } from '$lib/i18n/ns/admin-identity';
	import { t as td } from '$lib/i18n/ns/domain-admin';
	import Field from '$lib/components/ui/Field.svelte';
	import SearchSelect from '$lib/components/ui/SearchSelect.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import { t as tp } from '$lib/i18n/ns/compute-pools';
	import ComputePoolPanel from '$lib/components/iam/ComputePoolPanel.svelte';
	import GpuQuotaRequests from '$lib/components/iam/GpuQuotaRequests.svelte';

	const ctrl = createAdminQuotasController({
		token: () => get(auth).token ?? undefined,
		projectId: () => get(auth).projectId ?? undefined,
		userId: () => get(auth).userId ?? undefined,
	});
	const selectedDomain = $derived(ctrl.selectedDomainId || ctrl.projects.find(project => project.id === ctrl.selectedProjectId)?.domain_id || '');

	onMount(() => {
		let owner = '';
		const sync = () => {
			const state = get(auth);
			const next = JSON.stringify([!!state.token, state.sessionId, state.userId, state.identityDomainId, state.domainId, state.projectId, state.isSystemAdmin, get(authReady), get(projectSwitching), get(logoutInProgress)]);
			if (next === owner) return;
			owner = next;
			if (!state.token || !state.isSystemAdmin || !get(authReady) || get(projectSwitching) || get(logoutInProgress)) return;
			void ctrl.loadDomains(); void ctrl.loadProjects();
		};
		const subscriptions = [auth.subscribe(sync), authReady.subscribe(sync), projectSwitching.subscribe(sync), logoutInProgress.subscribe(sync)];
		return () => { for (const unsubscribe of subscriptions) unsubscribe(); };
	});
</script>

<PageShell>
	<PageHeader breadcrumb={t('quotaPage.breadcrumb')} title={t('quotaPage.title')} />
	<GpuQuotaRequests adminMode onSelectDomain={async (domainId) => { ctrl.selectedDomainId = domainId; await tick(); document.getElementById('gpu-request-domain-editor')?.focus(); }} />

	{#if ctrl.loading}
		<LoadingState variant="surface" />
	{:else}
			<Alert tone="info" class="mb-4">{tp('legacyHelp')}<div class="mt-2"><Button variant="link" href={selectedDomain ? `/admin/domains/${encodeURIComponent(selectedDomain)}` : '/admin/domains'}>{tp('managePools')}</Button></div></Alert>

			<div class="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-6 max-w-3xl">
				<Field for="quota-domain-scope" label={td('scope.domain')}>
					<SearchSelect
						id="quota-domain-scope"
						value={ctrl.selectedDomainId}
						options={ctrl.domains.map(domain => ({ value: domain.id, label: domain.name, description: domain.id }))}
						loading={ctrl.domainsLoading}
						disabled={!!ctrl.domainsError}
						placeholder={td('scope.choose')}
						ariaLabel={td('scope.domain')}
						onchange={(id) => { ctrl.selectedDomainId = id; if (ctrl.selectedProjectId) void ctrl.loadQuotas(); }}
					/>
					{#if ctrl.selectedDomainId}
						<Button variant="ghost" size="sm" onclick={() => { ctrl.selectedDomainId = ''; if (ctrl.selectedProjectId) void ctrl.loadQuotas(); }}>{td('scope.clear')}</Button>
					{/if}
				</Field>
				<ProjectSelector
					projects={ctrl.projects}
					selectedId={ctrl.selectedProjectId}
					loading={ctrl.refreshing}
					disabled={!!ctrl.projectsError}
					onSelected={(id) => { ctrl.selectedProjectId = id; void ctrl.loadQuotas(); }}
				/>
			</div>
			{#if ctrl.domainsError}
				<Alert class="mb-4">{ctrl.domainsError}</Alert>
				<Button variant="secondary" size="sm" disabled={ctrl.domainsLoading} onclick={() => ctrl.loadDomains()}>{td('actions.refresh')}</Button>
			{/if}
			{#if ctrl.projectsError}
				<Alert class="mb-4">{ctrl.projectsError}</Alert>
				<Button variant="secondary" size="sm" disabled={ctrl.loading || ctrl.refreshing} onclick={() => ctrl.loadProjects()}>{td('actions.refresh')}</Button>
			{/if}
			{#if selectedDomain}<div id="gpu-request-domain-editor" tabindex="-1" class="mb-6 scroll-mt-4">{#key `${ctrl.scopeRevision}:${selectedDomain}`}<ComputePoolPanel domainId={selectedDomain} adminMode />{/key}</div>{/if}

		{#key ctrl.scopeRevision}
			{#if ctrl.selectedProjectId}
				{#if ctrl.quotaLoading}
					<LoadingState variant="section" />
				{:else if ctrl.quotas}
					<ProjectQuotaForm
						quotas={ctrl.quotas}
						projectId={ctrl.selectedProjectId}
						saving={ctrl.saving}
						savingSection={ctrl.savingSection}
						sectionErrors={ctrl.sectionErrors}
						sectionSuccesses={ctrl.sectionSuccesses}
						onSaveSection={ctrl.saveSectionQuotas}
					/>
				{:else}
					<div class="text-ink-2 text-sm">{t('quotaPage.unavailable')}</div>
				{/if}
			{/if}
		{/key}
	{/if}
</PageShell>
