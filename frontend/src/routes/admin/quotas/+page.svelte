<script lang="ts">
	import PageShell from '$lib/components/ui/PageShell.svelte';
	import { onMount } from 'svelte';
	import { get } from 'svelte/store';
	import { auth, authReady, projectSwitching, logoutInProgress } from '$lib/stores/auth';
	import { createAdminQuotasController } from '$lib/stores/adminQuotasController.svelte';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import GpuDefaultQuotaSection from '$lib/components/admin/quotas/GpuDefaultQuotaSection.svelte';
	import ProjectSelector from '$lib/components/admin/quotas/ProjectSelector.svelte';
	import ProjectQuotaForm from '$lib/components/admin/quotas/ProjectQuotaForm.svelte';
	import GpuQuotaTable from '$lib/components/admin/quotas/GpuQuotaTable.svelte';
	import { t } from '$lib/i18n/ns/admin-identity';
	import { t as td } from '$lib/i18n/ns/domain-admin';
	import Field from '$lib/components/ui/Field.svelte';
	import SearchSelect from '$lib/components/ui/SearchSelect.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Button from '$lib/components/ui/Button.svelte';

	const ctrl = createAdminQuotasController({
		token: () => get(auth).token ?? undefined,
		projectId: () => get(auth).projectId ?? undefined,
		userId: () => get(auth).userId ?? undefined,
	});

	onMount(() => {
		let owner = '';
		const sync = () => {
			const state = get(auth);
			const next = JSON.stringify([!!state.token, state.sessionId, state.userId, state.identityDomainId, state.domainId, state.projectId, state.isSystemAdmin, get(authReady), get(projectSwitching), get(logoutInProgress)]);
			if (next === owner) return;
			owner = next;
			if (!state.token || !state.isSystemAdmin || !get(authReady) || get(projectSwitching) || get(logoutInProgress)) return;
			void ctrl.loadDomains(); void ctrl.loadProjects(); void ctrl.loadGpuAliases(); void ctrl.loadGpuDefaults();
		};
		const subscriptions = [auth.subscribe(sync), authReady.subscribe(sync), projectSwitching.subscribe(sync), logoutInProgress.subscribe(sync)];
		return () => { for (const unsubscribe of subscriptions) unsubscribe(); };
	});
</script>

<PageShell>
	<PageHeader breadcrumb={t('quotaPage.breadcrumb')} title={t('quotaPage.title')} />

	{#if ctrl.loading}
		<LoadingSkeleton variant="table" rows={3} />
	{:else}
			<GpuDefaultQuotaSection
				defaults={ctrl.gpuDefaultMap}
				allGpuTypes={ctrl.allGpuTypes}
				loading={ctrl.gpuDefaultLoading}
				error={ctrl.gpuDefaultError}
				success={ctrl.gpuDefaultSuccess}
				onChange={ctrl.setGpuDefault}
			/>

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

		{#key ctrl.scopeRevision}
			{#if ctrl.selectedProjectId}
				{#if ctrl.quotaLoading}
					<LoadingSkeleton variant="table" rows={3} />
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
				<GpuQuotaTable
					rows={ctrl.gpuQuotaRows}
					defaults={ctrl.gpuDefaultMap}
					loading={ctrl.gpuQuotaLoading}
					error={ctrl.gpuQuotaError}
					hasAnyAlias={ctrl.allGpuTypes.length > 0}
					onSetLimit={ctrl.setGpuQuota}
					onClear={ctrl.deleteGpuQuota}
				/>
			{/if}
		{/key}
	{/if}
</PageShell>
