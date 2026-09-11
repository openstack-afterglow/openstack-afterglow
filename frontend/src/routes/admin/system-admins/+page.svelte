<script lang="ts">
	import { onMount } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { api } from '$lib/api/client';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import SystemAdminTable from '$lib/components/admin/system-admins/SystemAdminTable.svelte';
	import SystemAdminGrantModal from '$lib/components/admin/system-admins/SystemAdminGrantModal.svelte';
	import SecurityPolicyBanner from '$lib/components/admin/system-admins/SecurityPolicyBanner.svelte';
	import MigrateModal from '$lib/components/admin/system-admins/MigrateModal.svelte';

	interface SystemAdmin {
		user_id: string;
		name: string;
		email: string;
		enabled: boolean;
	}

	interface SecurityPolicy {
		legacy_compat: boolean;
		system_admin_count: number;
		admin_project_member_count: number;
	}

	let admins = $state<SystemAdmin[]>([]);
	let policy = $state<SecurityPolicy | null>(null);
	let loading = $state(true);
	let refreshing = $state(false);
	let policyLoading = $state(true);
	let adminsError = $state('');
	let policyError = $state('');
	let loadGeneration = 0;
	let showGrant = $state(false);
	let showMigrate = $state(false);

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	async function load() {
		const requestToken = token;
		const requestProjectId = projectId;
		const generation = ++loadGeneration;
		if (admins.length === 0) loading = true;
		else refreshing = true;
		policyLoading = true;
		adminsError = '';
		policyError = '';
		const adminsPromise = api.get<SystemAdmin[]>('/api/v1/admin/identity/system-roles', requestToken, requestProjectId);
		const policyPromise = api.get<SecurityPolicy>('/api/v1/admin/identity/security-policy', requestToken, requestProjectId)
			.then((value) => {
				if (generation === loadGeneration && token === requestToken && projectId === requestProjectId) policy = value;
				if (generation === loadGeneration && token === requestToken && projectId === requestProjectId) policyError = '';
			})
			.catch((loadError) => {
				if (generation === loadGeneration && token === requestToken && projectId === requestProjectId) {
					policy = null;
					policyError = loadError instanceof Error ? loadError.message : '보안 정책 조회 실패';
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
				adminsError = loadError instanceof Error ? loadError.message : '시스템 관리자 조회 실패';
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

<div class="p-4 md:p-6 max-w-7xl mx-auto">
	<PageHeader breadcrumb="IDENTITY / SYSTEM ADMINS" title="시스템 관리자">
		{#snippet actions()}
			<button
				onclick={() => (showGrant = true)}
				class="px-4 py-2 bg-action-warm hover:bg-action-warm-hover text-action-on-warm text-sm font-medium rounded-lg"
			>
				+ 추가
			</button>
			<AutoRefreshControl
				bind:active={ar.active}
				bind:intervalSeconds={ar.intervalSeconds}
				intervalOptions={ar.intervalOptions}
				refreshing={loading || refreshing}
				onManualRefresh={load}
			/>
		{/snippet}
	</PageHeader>

	{#if loading}
		<LoadingSkeleton variant="table" rows={3} />
	{:else}
			{#if policyLoading}
				<Alert tone="neutral" class="mb-3">보안 정책을 불러오는 중...</Alert>
			{:else if policyError}
				<Alert tone="danger" class="mb-3" title="보안 정책 조회 실패">{policyError}</Alert>
			{:else if policy}
				<SecurityPolicyBanner {policy} onMigrate={() => (showMigrate = true)} />
			{/if}

			{#if adminsError}
				<Alert tone="danger" class="mb-3" title="시스템 관리자 조회 실패">{adminsError}</Alert>
			{/if}
			{#if admins.length === 0}
				<div class="text-ink-3 text-sm py-12 text-center">
					등록된 system admin이 없습니다.
				</div>
			{:else}
				<SystemAdminTable {admins} onRevoked={load} />
			{/if}
	{/if}
</div>

{#if showGrant}
	<SystemAdminGrantModal onClose={() => (showGrant = false)} onGranted={load} />
{/if}

{#if showMigrate && policy}
	<MigrateModal
		adminProjectMemberCount={policy.admin_project_member_count}
		onClose={() => (showMigrate = false)}
		onMigrated={load}
	/>
{/if}
