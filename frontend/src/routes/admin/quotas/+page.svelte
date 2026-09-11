<script lang="ts">
	import { onMount } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { createAdminQuotasController } from '$lib/stores/adminQuotasController.svelte';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import GpuDefaultQuotaSection from '$lib/components/admin/quotas/GpuDefaultQuotaSection.svelte';
	import ProjectSelector from '$lib/components/admin/quotas/ProjectSelector.svelte';
	import ProjectQuotaForm from '$lib/components/admin/quotas/ProjectQuotaForm.svelte';
	import GpuQuotaTable from '$lib/components/admin/quotas/GpuQuotaTable.svelte';

	const ctrl = createAdminQuotasController({
		token: () => $auth.token ?? undefined,
		projectId: () => $auth.projectId ?? undefined,
	});

	onMount(() => { ctrl.loadProjects(); ctrl.loadGpuAliases(); ctrl.loadGpuDefaults(); });
</script>

<div class="p-4 md:p-6 max-w-7xl mx-auto">
	<PageHeader breadcrumb="IDENTITY / QUOTAS" title="쿼터" />

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

			<ProjectSelector
				projects={ctrl.projects}
				bind:search={ctrl.projectSearch}
				bind:selectedId={ctrl.selectedProjectId}
				bind:selectedName={ctrl.selectedProjectName}
				onSelected={() => ctrl.loadQuotas()}
			/>

			{#if ctrl.selectedProjectId}
				{#if ctrl.quotaLoading}
					<LoadingSkeleton variant="table" rows={3} />
				{:else if ctrl.quotas}
					<ProjectQuotaForm
						quotas={ctrl.quotas}
						saving={ctrl.saving}
						saveError={ctrl.saveError}
						saveSuccess={ctrl.saveSuccess}
						onSave={ctrl.saveQuotas}
					/>
					<GpuQuotaTable
						rows={ctrl.gpuQuotas}
						defaults={ctrl.gpuDefaultMap}
						loading={ctrl.gpuQuotaLoading}
						error={ctrl.gpuQuotaError}
						hasAnyAlias={ctrl.allGpuTypes.length > 0}
						onSetLimit={ctrl.setGpuQuota}
						onClear={ctrl.deleteGpuQuota}
						reconcilePreview={ctrl.reconcilePreview}
					/>
				{:else}
					<div class="text-ink-3 text-sm">쿼터를 불러올 수 없습니다</div>
				{/if}
			{/if}
	{/if}
</div>
