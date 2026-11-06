<script lang="ts">
	import PageShell from '$lib/components/ui/PageShell.svelte';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import { onMount } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { api } from '$lib/api/client';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import SystemAdminTable from '$lib/components/admin/system-admins/SystemAdminTable.svelte';
	import SystemAdminGrantModal from '$lib/components/admin/system-admins/SystemAdminGrantModal.svelte';
	import SecurityPolicyBanner from '$lib/components/admin/system-admins/SecurityPolicyBanner.svelte';
	import type { AdminSecurityPolicy } from '$lib/types/adminSecurityPolicy';
	import { t } from '$lib/i18n/ns/admin-identity';

	interface SystemAdmin {
		user_id: string;
		name: string;
		email: string;
		enabled: boolean;
	}

	let admins = $state<SystemAdmin[]>([]);
	let policy = $state<AdminSecurityPolicy | null>(null);
	let loading = $state(true);
	let refreshing = $state(false);
	let policyLoading = $state(true);
	let adminsError = $state('');
	let policyError = $state('');
	let loadGeneration = 0;
	let showGrant = $state(false);

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	async function load(force = false) {
		const requestToken = token;
		const requestProjectId = projectId;
		const generation = ++loadGeneration;
		if (admins.length === 0) loading = true;
		else refreshing = true;
		policyLoading = true;
		adminsError = '';
		policyError = '';
		const adminsPromise = api.get<SystemAdmin[]>('/api/v1/admin/identity/system-roles', requestToken, requestProjectId, { refresh: force });
		const policyPromise = api.get<AdminSecurityPolicy>('/api/v1/admin/identity/security-policy', requestToken, requestProjectId, { refresh: force })
			.then((value) => {
				if (generation === loadGeneration && token === requestToken && projectId === requestProjectId) policy = value;
				if (generation === loadGeneration && token === requestToken && projectId === requestProjectId) policyError = '';
			})
			.catch((loadError) => {
				if (generation === loadGeneration && token === requestToken && projectId === requestProjectId) {
					policy = null;
					policyError = loadError instanceof Error ? loadError.message : t('systemPage.policyFailed');
				}
			})
			.finally(() => {
				if (generation === loadGeneration && token === requestToken && projectId === requestProjectId) policyLoading = false;
			});
		try {
			const value = await adminsPromise;
			if (generation === loadGeneration && token === requestToken && projectId === requestProjectId) admins = value;
		} catch (loadError) {
			if (generation === loadGeneration && token === requestToken && projectId === requestProjectId) {
				admins = [];
				adminsError = loadError instanceof Error ? loadError.message : t('systemPage.adminsFailed');
			}
		} finally {
			if (generation === loadGeneration && token === requestToken && projectId === requestProjectId) {
				loading = false;
				refreshing = false;
			}
		}
		void policyPromise;
	}

	const ar = createAutoRefresh(load, {
		storageKey: 'admin-system-admins',
		invokeOnMount: false,
		defaultActive: true,
		defaultInterval: 60,
		intervalOptions: [30, 60],
	});

	onMount(load);
</script>

<PageShell>
	<PageHeader breadcrumb={t('systemPage.breadcrumb')} title={t('systemPage.title')}>
		{#snippet actions()}
			<button
				onclick={() => (showGrant = true)}
				class="px-4 py-2 bg-action-warm hover:bg-action-warm-hover text-action-on-warm text-sm font-medium rounded-lg"
			>
				{t('systemPage.add')}
			</button>
			<AutoRefreshControl
				bind:active={ar.active}
				bind:intervalSeconds={ar.intervalSeconds}
				intervalOptions={ar.intervalOptions}
				refreshing={loading || refreshing}
				onManualRefresh={ar.refresh}
			/>
		{/snippet}
	</PageHeader>

	{#if loading}
		<LoadingState variant="surface" />
	{:else}
			{#if policyLoading}
				<Alert tone="neutral" class="mb-3"><span class="inline-flex items-center gap-2"><LoadingState variant="control" label="" aria-hidden="true" />{t('systemPage.policyLoading')}</span></Alert>
			{:else if policyError}
				<Alert tone="danger" class="mb-3" title={t('systemPage.policyFailed')}>{policyError}</Alert>
			{:else if policy}
				<SecurityPolicyBanner {policy} />
			{/if}

			{#if adminsError}
				<Alert tone="danger" class="mb-3" title={t('systemPage.adminsFailed')}>{adminsError}</Alert>
			{/if}
	{/if}
	<SystemAdminTable {admins} onRevoked={load} />
</PageShell>

{#if showGrant}
	<SystemAdminGrantModal onClose={() => (showGrant = false)} onGranted={load} />
{/if}
