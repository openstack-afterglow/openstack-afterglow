<script lang="ts">
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { untrack } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import QuotaBar from '$lib/components/ui/QuotaBar.svelte';
	import BulkSelectionOverlay from '$lib/components/ui/BulkSelectionOverlay.svelte';
	import type { SecurityGroup, SecurityGroupInstance, SecurityGroupQuota, SecurityGroupRule, SecurityGroupRuleDraft } from '$lib/types/securityGroup';
	import SecurityGroupList from '$lib/components/dashboard/network/security-groups/SecurityGroupList.svelte';
	import SecurityGroupRulesPanel from '$lib/components/dashboard/network/security-groups/SecurityGroupRulesPanel.svelte';
	import SecurityGroupCreateModal from '$lib/components/dashboard/network/security-groups/SecurityGroupCreateModal.svelte';
	import { toast } from '$lib/stores/toast';
	import { createResourceSelection } from '$lib/utils/resourceSelection.svelte';
	import { executeBulkMutations, partitionBulkIds } from '$lib/utils/bulkActions';

	function emptyRule(): SecurityGroupRuleDraft {
		return { direction: 'ingress', protocol: '', port_range_min: '', port_range_max: '', remote_ip_prefix: '', remote_group_id: '', ethertype: 'IPv4' };
	}

	let securityGroups = $state<SecurityGroup[]>([]);
	let quota = $state<SecurityGroupQuota | null>(null);
	let quotaError = $state('');
	let instances = $state<SecurityGroupInstance[]>([]);
	let instancesError = $state('');
	let instancesLoading = $state(false);
	let loading = $state(true);
	let refreshing = $state(false);
	let selection = createResourceSelection();
	let busy = $state(false);
	let sgError = $state('');
	let showSgModal = $state(false);
	let selectedSg = $state<string | null>(null);
	let addRuleOpen = $state(false);
	let originalRuleId = $state<string | null>(null);
	let targetType = $state<'cidr' | 'group'>('cidr');
	let ruleForm = $state<SecurityGroupRuleDraft>(emptyRule());
	let sgCreating = $state(false);
	let sgCreateError = $state('');
	let projectGeneration = 0;
	let groupRequest = 0;
	let quotaRequest = 0;
	let instanceRequest = 0;

	let selectableIds = $derived(new Set(securityGroups.filter((group) => group.name !== 'default').map((group) => group.id)));
	let curSg = $derived(securityGroups.find((group) => group.id === selectedSg) ?? null);
	let canCreateGroup = $derived(quota !== null && (quota.security_group.limit < 0 || quota.security_group.in_use < quota.security_group.limit));
	let canCreateRule = $derived(quota !== null && (quota.security_group_rule.limit < 0 || quota.security_group_rule.in_use < quota.security_group_rule.limit));

	async function fetchSecurityGroups(opts?: { refresh?: boolean }) {
		const project = $auth.projectId;
		const generation = projectGeneration;
		const request = ++groupRequest;
		try {
			const groups = await api.get<SecurityGroup[]>('/api/v1/security-groups', $auth.token ?? undefined, project ?? undefined, opts);
			if (generation !== projectGeneration || request !== groupRequest) return;
			securityGroups = groups;
			sgError = '';
			if (selection.count > 0) selection.retain(groups.map((group) => group.id));
			if (selectedSg && !groups.some((group) => group.id === selectedSg)) selectedSg = null;
			if (!selectedSg && groups.length > 0 && window.matchMedia('(min-width: 768px)').matches) selectedSg = groups[0].id;
		} catch (e) {
			if (generation === projectGeneration && request === groupRequest) sgError = e instanceof ApiError ? `조회 실패 (${e.status}): ${e.message}` : '보안 그룹 조회 실패';
		} finally {
			if (generation === projectGeneration && request === groupRequest) loading = false;
		}
	}

	async function fetchQuota() {
		const project = $auth.projectId;
		const generation = projectGeneration;
		const request = ++quotaRequest;
		try {
			const result = await api.get<SecurityGroupQuota>('/api/v1/security-groups/quota', $auth.token ?? undefined, project ?? undefined);
			if (generation !== projectGeneration || request !== quotaRequest) return;
			quota = result;
			quotaError = '';
		} catch (e) {
			if (generation !== projectGeneration || request !== quotaRequest) return;
			quota = null;
			quotaError = e instanceof ApiError ? e.message : '쿼터 조회 실패';
		}
	}

	async function fetchInstances(sgId: string) {
		const project = $auth.projectId;
		const generation = projectGeneration;
		const request = ++instanceRequest;
		instances = [];
		instancesError = '';
		instancesLoading = true;
		try {
			const result = await api.get<SecurityGroupInstance[]>(`/api/v1/security-groups/${sgId}/instances`, $auth.token ?? undefined, project ?? undefined);
			if (generation === projectGeneration && request === instanceRequest && selectedSg === sgId) instances = result;
		} catch (e) {
			if (generation === projectGeneration && request === instanceRequest && selectedSg === sgId) instancesError = e instanceof ApiError ? e.message : '사용 인스턴스 조회 실패';
		} finally {
			if (generation === projectGeneration && request === instanceRequest && selectedSg === sgId) instancesLoading = false;
		}
	}

	async function refreshResources(opts?: { refresh?: boolean }) {
		const previousSelection = selectedSg;
		await Promise.all([fetchSecurityGroups(opts), fetchQuota()]);
		if (selectedSg && selectedSg === previousSelection) await fetchInstances(selectedSg);
	}

	async function forceRefresh() {
		refreshing = true;
		try { await refreshResources({ refresh: true }); }
		finally { refreshing = false; }
	}

	const ar = createAutoRefresh(() => refreshResources(), {
		storageKey: 'dashboard-network-sg',
		defaultActive: true,
		defaultInterval: 60,
		intervalOptions: [10, 15, 30, 60],
		invokeOnMount: false,
	});

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
				if (selectedSg && succeeded.includes(selectedSg)) selectedSg = null;
			}
			if (succeeded.length > 0) toast.success(`${succeeded.length}개 보안 그룹 삭제 요청을 완료했습니다.`);
			const failedCount = results.length - succeeded.length;
			if (failedCount > 0) toast.error(`${failedCount}개 보안 그룹 삭제에 실패했습니다.`);
			if (skipped.length > 0) toast.warning(`${skipped.length}개는 현재 상태에서 보안 그룹 삭제할 수 없어 제외했습니다.`);
			if (projectSnapshot === ($auth.projectId ?? undefined)) await refreshResources();
		} finally {
			busy = false;
		}
	}

	async function createSecurityGroup(form: { name: string; description: string }): Promise<boolean> {
		if (!form.name.trim() || !canCreateGroup) return false;
		sgCreating = true;
		sgCreateError = '';
		try {
			await api.post('/api/v1/security-groups', form, $auth.token ?? undefined, $auth.projectId ?? undefined);
			showSgModal = false;
			await refreshResources();
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
			if (selectedSg === sgId) selectedSg = null;
			await refreshResources();
		} catch (e) {
			toast.error('삭제 실패: ' + (e instanceof ApiError ? e.message : String(e)));
		}
	}

	function startAddRule() {
		ruleForm = emptyRule();
		targetType = 'cidr';
		originalRuleId = null;
		sgCreateError = '';
		addRuleOpen = true;
	}

	function editRule(rule: SecurityGroupRule) {
		ruleForm = {
			direction: rule.direction,
			protocol: rule.protocol ?? '',
			port_range_min: rule.port_range_min?.toString() ?? '',
			port_range_max: rule.port_range_max?.toString() ?? '',
			remote_ip_prefix: rule.remote_ip_prefix ?? '',
			remote_group_id: rule.remote_group_id ?? '',
			ethertype: rule.ethertype,
		};
		targetType = rule.remote_group_id ? 'group' : 'cidr';
		originalRuleId = rule.id;
		sgCreateError = '';
		addRuleOpen = true;
	}

	function cancelAddRule() {
		addRuleOpen = false;
		originalRuleId = null;
		sgCreateError = '';
	}

	function validPort(value: string): boolean {
		return /^[0-9]+$/.test(value) && Number(value) >= 1 && Number(value) <= 65535;
	}

	async function addSgRule(sgId: string) {
		if (!canCreateRule) { sgCreateError = '규칙 쿼터를 먼저 확인하거나 기존 규칙을 제거하세요.'; return; }
		const body: Record<string, unknown> = { direction: ruleForm.direction, ethertype: ruleForm.ethertype };
		if (ruleForm.protocol) body.protocol = ruleForm.protocol;
		if (ruleForm.protocol === 'tcp' || ruleForm.protocol === 'udp') {
			const min = ruleForm.port_range_min.trim();
			const max = ruleForm.port_range_max.trim();
			if ((min && !validPort(min)) || (max && (!validPort(max) || !min || Number(max) < Number(min)))) {
				sgCreateError = '포트는 1–65535 범위여야 하며 끝 포트는 시작 포트 이상이어야 합니다.';
				return;
			}
			if (min) { body.port_range_min = Number(min); body.port_range_max = max ? Number(max) : Number(min); }
		}
		if (targetType === 'group') {
			if (!ruleForm.remote_group_id || !securityGroups.some((group) => group.id === ruleForm.remote_group_id)) {
				sgCreateError = '현재 프로젝트의 원격 보안 그룹을 선택하세요.';
				return;
			}
			body.remote_group_id = ruleForm.remote_group_id;
		} else {
			body.remote_ip_prefix = ruleForm.remote_ip_prefix.trim() || (ruleForm.ethertype === 'IPv6' ? '::/0' : '0.0.0.0/0');
		}
		sgCreating = true;
		sgCreateError = '';
		try {
			await api.post(`/api/v1/security-groups/${sgId}/rules`, body, $auth.token ?? undefined, $auth.projectId ?? undefined);
			cancelAddRule();
			await refreshResources();
		} catch (e) {
			sgCreateError = e instanceof ApiError ? e.message : '규칙 추가 실패';
		} finally {
			sgCreating = false;
		}
	}

	async function deleteSgRule(sgId: string, ruleId: string): Promise<boolean> {
		try {
			await api.delete(`/api/v1/security-groups/${sgId}/rules/${ruleId}`, $auth.token ?? undefined, $auth.projectId ?? undefined);
			if (originalRuleId === ruleId) originalRuleId = null;
			await refreshResources();
			return true;
		} catch (e) {
			toast.error('규칙 삭제 실패: ' + (e instanceof ApiError ? e.message : String(e)));
			return false;
		}
	}

	async function removeOriginalRule(sgId: string) {
		if (!originalRuleId) return;
		if (!await confirmDialog('기존 규칙을 제거하시겠습니까? 새 규칙을 추가할 때까지 접근 정책이 달라집니다.')) return;
		await deleteSgRule(sgId, originalRuleId);
	}

	$effect(() => {
		const pid = $auth.projectId;
		untrack(() => {
			projectGeneration++;
			groupRequest++;
			quotaRequest++;
			instanceRequest++;
			securityGroups = [];
			quota = null;
			instances = [];
			selectedSg = null;
			selection.clear();
			cancelAddRule();
			loading = !!pid;
			if (pid) void refreshResources();
		});
	});

	$effect(() => {
		const pid = $auth.projectId;
		const id = selectedSg;
		untrack(() => {
			instanceRequest++;
			instances = [];
			instancesError = '';
			instancesLoading = false;
			cancelAddRule();
			if (pid && id) void fetchInstances(id);
		});
	});
</script>

<div class="bulk-selection-page p-4 md:p-6">
	<PageHeader breadcrumb="NETWORK / SECURITY GROUPS" title="보안 그룹">
		{#snippet actions()}
			<AutoRefreshControl bind:active={ar.active} bind:intervalSeconds={ar.intervalSeconds} intervalOptions={ar.intervalOptions} {refreshing} onManualRefresh={forceRefresh} />
			<button type="button" onclick={() => { showSgModal = true; sgCreateError = ''; }} disabled={!canCreateGroup} title={!canCreateGroup ? '보안 그룹 쿼터가 가득 찼거나 확인되지 않았습니다' : undefined} class="bg-action-warm hover:bg-action-warm-hover text-action-on-warm text-sm px-4 py-2 rounded-lg transition-colors disabled:opacity-50">+ 보안 그룹 생성</button>
		{/snippet}
	</PageHeader>

	<div class="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-5" aria-label="프로젝트 보안 그룹 쿼터">
		{#if quota}
			<div class="bg-surface-base border border-line rounded-lg p-3"><QuotaBar label="보안 그룹" used={quota.security_group.in_use} limit={quota.security_group.limit} size="sm" /></div>
			<div class="bg-surface-base border border-line rounded-lg p-3"><QuotaBar label="보안 그룹 규칙" used={quota.security_group_rule.in_use} limit={quota.security_group_rule.limit} size="sm" /></div>
		{:else}
			<p role={quotaError ? 'alert' : undefined} class="text-sm text-ink-2 sm:col-span-2">{quotaError ? `쿼터 조회 실패: ${quotaError}` : '프로젝트 쿼터 확인 중...'}</p>
		{/if}
	</div>
	{#if sgError}<p role="alert" class="text-sm text-state-danger-text mb-4">{sgError}</p>{/if}
	{#if loading}
		<LoadingSkeleton variant="table" rows={5} />
	{:else if securityGroups.length === 0}
		<div class="text-center py-20 text-ink-2"><div class="text-lg">보안 그룹이 없습니다</div></div>
	{:else}
		<div class="security-group-workspace">
			<div class="security-group-list">
				<SecurityGroupList groups={securityGroups} bind:selectedSg selectedIds={selection.ids} {selectableIds} selectionDisabled={busy} onToggleSelect={(id) => selection.toggle(id)} onToggleAll={() => selection.toggleAll(selectableIds)} />
			</div>
			{#if curSg}
				<SecurityGroupRulesPanel
					group={curSg} groups={securityGroups} {instances} {instancesError} {instancesLoading}
					{addRuleOpen} {originalRuleId} addingRule={sgCreating} canAddRule={canCreateRule} addError={sgCreateError} bind:ruleForm bind:targetType
					onStartAdd={startAddRule} onEditRule={editRule} onCancelAdd={cancelAddRule}
					onAddRule={() => addSgRule(curSg!.id)} onRemoveOriginal={() => removeOriginalRule(curSg!.id)}
					onDeleteRule={async (id) => { await deleteSgRule(curSg!.id, id); }}
					onDeleteGroup={() => deleteSecurityGroup(curSg!.id, curSg!.name)}
					onSelectGroup={(id) => { if (securityGroups.some((group) => group.id === id)) selectedSg = id; }}
					onRetryInstances={() => fetchInstances(curSg!.id)} onCloseMobile={() => selectedSg = null}
				/>
			{:else}
				<div class="bg-surface-base border border-line rounded-lg p-5 flex items-center justify-center text-ink-2 text-sm min-h-[200px] max-md:hidden">왼쪽에서 보안 그룹을 선택하세요</div>
			{/if}
		</div>
	{/if}
</div>

<BulkSelectionOverlay count={selection.count} ariaLabel="선택한 보안 그룹 일괄 작업" actions={[{ key: 'delete', label: '삭제', tone: 'danger', disabled: partitionBulkIds(selection.ids, selectableIds).eligible.length === 0, onAction: bulkDeleteGroups }]} {busy} onClear={() => selection.clear()} />
<SecurityGroupCreateModal bind:open={showSgModal} creating={sgCreating} error={sgCreateError} onCreate={createSecurityGroup} />

<style>
	.security-group-workspace { display: grid; grid-template-columns: minmax(0, 1fr); align-items: start; gap: 1.5rem; }
	@media (min-width: 1024px) {
		.security-group-workspace { grid-template-columns: minmax(17.5rem, 22rem) minmax(0, 1fr); gap: clamp(1.5rem, 2.5vw, 3rem); }
	}
</style>
