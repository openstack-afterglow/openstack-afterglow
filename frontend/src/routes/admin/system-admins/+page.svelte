<script lang="ts">
	import PageShell from '$lib/components/ui/PageShell.svelte';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import { untrack } from 'svelte';
	import { auth, authReady, isAdmin, isMockAuthActive } from '$lib/stores/auth';
	import { authDisplayContext } from '$lib/stores/authDisplayContext';
	import TutorialStartButton from '$lib/tutorial/TutorialStartButton.svelte';
	import { api } from '$lib/api/client';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import SystemAdminTable from '$lib/components/admin/system-admins/SystemAdminTable.svelte';
	import SystemAdminGrantModal from '$lib/components/admin/system-admins/SystemAdminGrantModal.svelte';
	import SecurityPolicyBanner from '$lib/components/admin/system-admins/SecurityPolicyBanner.svelte';
	import { t } from '$lib/i18n/ns/admin-identity';

	interface SystemAdmin {
		user_id: string;
		name: string;
		email: string;
		enabled: boolean;
	}

	let admins = $state<SystemAdmin[]>([]);
	let loading = $state(true);
	let refreshing = $state(false);
	let adminsError = $state('');
	let loadGeneration = 0;
	let showGrant = $state(false);
	let notice = $state<'granted' | 'revoked' | null>(null);

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);
	const ownerKey = $derived($authDisplayContext.key);

	async function load(force = false) {
		const requestToken = token;
		const requestProjectId = projectId;
		const requestOwner = $authDisplayContext.key;
		const generation = ++loadGeneration;
		const current = () => generation === loadGeneration && requestOwner === $authDisplayContext.key;
		if (admins.length === 0) loading = true;
		else refreshing = true;
		adminsError = '';
		try {
			const value = await api.get<SystemAdmin[]>('/api/v1/admin/identity/system-roles', requestToken, requestProjectId, { refresh: force });
			if (current()) admins = value;
		} catch (loadError) {
			if (current()) {
				admins = [];
				adminsError = loadError instanceof Error ? loadError.message : t('systemPage.adminsFailed');
			}
		} finally {
			if (current()) {
				loading = false;
				refreshing = false;
			}
		}
	}

	const ar = createAutoRefresh((force?: boolean) => { notice = null; return load(force); }, {
		storageKey: 'admin-system-admins',
		invokeOnMount: false,
		defaultActive: true,
		defaultInterval: 60,
		intervalOptions: [30, 60],
	});

	function mutationSucceeded(result: 'granted' | 'revoked') {
		notice = result;
		void load(true);
	}

	$effect(() => {
		ownerKey;
		untrack(() => {
			admins = [];
			adminsError = '';
			notice = null;
			showGrant = false;
			loading = $authDisplayContext.ready;
			if ($authDisplayContext.ready) void load();
		});
		return () => { loadGeneration++; };
	});
</script>

<PageShell>
	<PageHeader breadcrumb={t('systemPage.breadcrumb')} title={t('systemPage.title')}>
		{#snippet actions()}
			{#if !isMockAuthActive() && $authReady && $isAdmin}
				<TutorialStartButton tour="admin-system-admins" compactOnMobile />
			{/if}
			<button
				data-tour="admin-system-admins-add"
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

	{#if notice}
		<Alert tone="success" class="mb-3">{t(notice === 'granted' ? 'systemPage.granted' : 'systemPage.revoked')}</Alert>
	{/if}
	{#if loading}
		<LoadingState variant="surface" />
	{:else}
			{#if !adminsError && $authDisplayContext.ready}
				<div data-tour="admin-system-admins-policy"><SecurityPolicyBanner policy={{ system_admin_count: admins.length }} /></div>
			{/if}

			{#if adminsError}
				<Alert tone="danger" class="mb-3" title={t('systemPage.adminsFailed')}>{adminsError}</Alert>
			{/if}
	{/if}
	<div data-tour="admin-system-admins-list">
		{#key $authDisplayContext.key}
			<SystemAdminTable {admins} onRevoked={() => mutationSucceeded('revoked')} />
		{/key}
	</div>
</PageShell>

{#if showGrant}
	<SystemAdminGrantModal onClose={() => (showGrant = false)} onGranted={() => mutationSucceeded('granted')} />
{/if}
