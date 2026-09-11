<script lang="ts">
  import { confirmDialog } from '$lib/stores/confirm.svelte';
  import { untrack } from 'svelte';
  import { auth } from '$lib/stores/auth';
  import { api, ApiError } from '$lib/api/client';
  import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
  import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
  import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
  import PageHeader from '$lib/components/ui/PageHeader.svelte';
  import BulkSelectionOverlay from '$lib/components/ui/BulkSelectionOverlay.svelte';
  import type { SecurityGroup } from '$lib/types/securityGroup';
  import SecurityGroupList from '$lib/components/dashboard/network/security-groups/SecurityGroupList.svelte';
  import SecurityGroupRulesPanel from '$lib/components/dashboard/network/security-groups/SecurityGroupRulesPanel.svelte';
  import SecurityGroupCreateModal from '$lib/components/dashboard/network/security-groups/SecurityGroupCreateModal.svelte';
  import { toast } from '$lib/stores/toast';
  import { createResourceSelection } from '$lib/utils/resourceSelection.svelte';
  import { executeBulkMutations, partitionBulkIds } from '$lib/utils/bulkActions';

	let securityGroups = $state<SecurityGroup[]>([]);
	let loading = $state(true);
	let refreshing = $state(false);
	let selection = createResourceSelection();
	let busy = $state(false);
	let selectableIds = $derived(new Set(securityGroups.filter((group) => group.name !== 'default').map((group) => group.id)));

	async function bulkDeleteGroups() {
		const snapshotIds = [...selection.ids];
		const { eligible, skipped } = partitionBulkIds(snapshotIds, selectableIds);
		if (eligible.length === 0) return;
		const suffix = skipped.length > 0 ? `\n${skipped.length}개는 현재 상태에서 제외됩니다.` : '';
		if (!await confirmDialog(`${eligible.length}개 보안 그룹을 삭제하시겠습니까?${suffix}`)) return;
		const tokenSnapshot = $auth.token ?? undefined;
		const projectSnapshot = $auth.projectId ?? undefined;
		busy = true;
		try {
			const results = await executeBulkMutations(eligible, (id) => api.delete(`/api/v1/security-groups/${id}`, tokenSnapshot, projectSnapshot));
			const succeeded = results.filter((result) => result.ok).map((result) => result.id);
			if (projectSnapshot === ($auth.projectId ?? undefined)) {
				selection.remove(succeeded);
				if (selectedSg && succeeded.some((id) => securityGroups.find((group) => group.id === id)?.name === selectedSg)) selectedSg = null;
			}
			if (succeeded.length > 0) toast.success(`${succeeded.length}개 보안 그룹 삭제 요청을 완료했습니다.`);
			const failedCount = results.length - succeeded.length;
			if (failedCount > 0) toast.error(`${failedCount}개 보안 그룹 삭제에 실패했습니다.`);
			if (skipped.length > 0) toast.warning(`${skipped.length}개는 현재 상태에서 보안 그룹 삭제할 수 없어 제외했습니다.`);
			if (projectSnapshot === ($auth.projectId ?? undefined)) await fetchSecurityGroups();
		} finally {
			busy = false;
		}
	}
	let sgError = $state('');

	let showSgModal = $state(false);
	let selectedSg = $state<string | null>(null);
	let addRuleOpen = $state(false);
	let ruleForm = $state({ direction: 'ingress', protocol: '', port_range_min: '', port_range_max: '', remote_ip_prefix: '', ethertype: 'IPv4' });
	let sgCreating = $state(false);
	let sgCreateError = $state('');

	let curSg = $derived(securityGroups.find(sg => sg.name === selectedSg) ?? null);

	async function fetchSecurityGroups(opts?: { refresh?: boolean }) {
		try {
			securityGroups = await api.get<SecurityGroup[]>('/api/v1/security-groups', $auth.token ?? undefined, $auth.projectId ?? undefined, opts);
			sgError = '';
			if (selection.count > 0) selection.retain(securityGroups.map((group) => group.id));
			if (!selectedSg && securityGroups.length > 0) selectedSg = securityGroups[0].name;
		} catch (e) {
			sgError = e instanceof ApiError ? `조회 실패 (${e.status}): ${(e as ApiError).message}` : '서버 오류';
		} finally {
			loading = false;
		}
	}

	async function forceRefresh() {
		refreshing = true;
		try { await fetchSecurityGroups({ refresh: true }); }
		finally { refreshing = false; }
	}

	const ar = createAutoRefresh(() => fetchSecurityGroups(), {
		storageKey: 'dashboard-network-sg',
		defaultActive: true,
		defaultInterval: 60,
		intervalOptions: [10, 15, 30, 60],
		invokeOnMount: false,
	});

	async function createSecurityGroup(form: { name: string; description: string }): Promise<boolean> {
		if (!form.name.trim()) return false;
		sgCreating = true;
		sgCreateError = '';
		try {
			await api.post('/api/v1/security-groups', form, $auth.token ?? undefined, $auth.projectId ?? undefined);
			showSgModal = false;
			await fetchSecurityGroups();
			return true;
		} catch (e) {
			sgCreateError = e instanceof ApiError ? e.message : '생성 실패';
			return false;
		} finally {
			sgCreating = false;
		}
	}

	async function deleteSecurityGroup(sgId: string, name: string) {
		if (!await confirmDialog(`"${name}" 보안 그룹을 삭제하시겠습니까?`)) return;
		try {
			await api.delete(`/api/v1/security-groups/${sgId}`, $auth.token ?? undefined, $auth.projectId ?? undefined);
			if (selectedSg === name) selectedSg = null;
			await fetchSecurityGroups();
		} catch (e) {
			toast.error('삭제 실패: ' + (e instanceof ApiError ? e.message : String(e)));
		}
	}

	async function addSgRule(sgId: string) {
		sgCreating = true;
		sgCreateError = '';
		try {
			const body: Record<string, unknown> = {
				direction: ruleForm.direction,
				ethertype: ruleForm.ethertype,
			};
			if (ruleForm.protocol) body.protocol = ruleForm.protocol;
			if (ruleForm.port_range_min) body.port_range_min = parseInt(ruleForm.port_range_min);
			if (ruleForm.port_range_max) body.port_range_max = parseInt(ruleForm.port_range_max);
			if (body.port_range_min != null && body.port_range_max == null) body.port_range_max = body.port_range_min;
			if (ruleForm.remote_ip_prefix) body.remote_ip_prefix = ruleForm.remote_ip_prefix;
			await api.post(`/api/v1/security-groups/${sgId}/rules`, body, $auth.token ?? undefined, $auth.projectId ?? undefined);
			addRuleOpen = false;
			ruleForm = { direction: 'ingress', protocol: '', port_range_min: '', port_range_max: '', remote_ip_prefix: '', ethertype: 'IPv4' };
			await fetchSecurityGroups();
		} catch (e) {
			sgCreateError = e instanceof ApiError ? e.message : '규칙 추가 실패';
		} finally {
			sgCreating = false;
		}
	}

	async function deleteSgRule(sgId: string, ruleId: string) {
		try {
			await api.delete(`/api/v1/security-groups/${sgId}/rules/${ruleId}`, $auth.token ?? undefined, $auth.projectId ?? undefined);
			await fetchSecurityGroups();
		} catch (e) {
			toast.error('규칙 삭제 실패: ' + (e instanceof ApiError ? e.message : String(e)));
		}
	}
	$effect(() => {
		const pid = $auth.projectId;
		if (!pid) return;
		untrack(() => {
			selection.clear();
			void fetchSecurityGroups();
		});
	});
</script>
<div class="bulk-selection-page p-4 md:p-8">
	<PageHeader breadcrumb="NETWORK / SECURITY GROUPS" title="보안 그룹">
		{#snippet actions()}
			<AutoRefreshControl
				bind:active={ar.active}
				bind:intervalSeconds={ar.intervalSeconds}
				intervalOptions={ar.intervalOptions}
				refreshing={refreshing}
				onManualRefresh={forceRefresh}
			/>
			<button
				onclick={() => { showSgModal = true; sgCreateError = ''; }}
				class="bg-action-warm hover:bg-action-warm-hover text-action-on-warm text-sm px-4 py-2 rounded-lg transition-colors"
			>+ 보안 그룹 생성</button>
		{/snippet}
	</PageHeader>

	{#if sgError}
		<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm mb-4">{sgError}</div>
	{/if}

	{#if loading}
		<LoadingSkeleton variant="table" rows={5} />
	{:else if securityGroups.length === 0}
		<div class="text-center py-20 text-ink-3">
			<div class="text-5xl mb-4">🔒</div>
			<div class="text-lg">보안 그룹이 없습니다</div>
		</div>
	{:else}
		<div class="security-group-workspace">
			<div class="security-group-list">
			<SecurityGroupList
				groups={securityGroups}
				bind:selectedSg
				selectedIds={selection.ids}
				selectableIds={selectableIds}
				selectionDisabled={busy}
				onToggleSelect={(id) => selection.toggle(id)}
				onToggleAll={() => selection.toggleAll(selectableIds)}
			/>
			</div>

			{#if curSg}
				<SecurityGroupRulesPanel
					group={curSg}
					bind:addRuleOpen
					addingRule={sgCreating}
					addError={sgCreateError}
					bind:ruleForm
					onAddRule={() => addSgRule(curSg!.id)}
					onDeleteRule={(ruleId) => deleteSgRule(curSg!.id, ruleId)}
					onDeleteGroup={() => deleteSecurityGroup(curSg!.id, curSg!.name)}
					onCloseMobile={() => selectedSg = null}
				/>
			{:else}
				<div class="bg-surface-base border border-line rounded-lg p-5 flex items-center justify-center text-ink-3 text-sm min-h-[200px]">
					왼쪽에서 보안 그룹을 선택하세요
				</div>
			{/if}
		</div>
	{/if}
</div>

<BulkSelectionOverlay
	count={selection.count}
	ariaLabel="선택한 보안 그룹 일괄 작업"
	actions={[{ key: 'delete', label: '삭제', tone: 'danger', disabled: partitionBulkIds(selection.ids, selectableIds).eligible.length === 0, onAction: bulkDeleteGroups }]}
	{busy}
	onClear={() => selection.clear()}
/>
<SecurityGroupCreateModal
	bind:open={showSgModal}
	creating={sgCreating}
	error={sgCreateError}
	onCreate={createSecurityGroup}
/>

<style>
	.security-group-workspace {
		display: grid;
		grid-template-columns: minmax(17.5rem, 22rem) minmax(0, 1fr);
		align-items: start;
		gap: clamp(1.5rem, 2.5vw, 3rem);
	}

	@media (max-width: 639px) {
		.security-group-workspace {
			grid-template-columns: minmax(0, 1fr);
		}
	}
</style>
