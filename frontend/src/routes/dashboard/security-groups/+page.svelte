<script lang="ts">
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import SecurityGroupCard from '$lib/components/dashboard/security-groups/SecurityGroupCard.svelte';
	import SecurityGroupCreateModal from '$lib/components/dashboard/security-groups/SecurityGroupCreateModal.svelte';

	import type { SecurityGroupRule, SecurityGroup } from '$lib/types/securityGroup';
	import { toast } from '$lib/stores/toast';

	let securityGroups = $state<SecurityGroup[]>([]);
	let loading = $state(true);
	let sgError = $state('');
	let showSgModal = $state(false);

	async function fetchSecurityGroups() {
		try {
			securityGroups = await api.get<SecurityGroup[]>('/api/v1/security-groups', $auth.token ?? undefined, $auth.projectId ?? undefined);
			sgError = '';
		} catch (e) {
			sgError = e instanceof ApiError ? `조회 실패 (${e.status}): ${(e as ApiError).message}` : '서버 오류';
		} finally {
			loading = false;
		}
	}

	async function createSecurityGroup(form: { name: string; description: string }): Promise<string | true> {
		if (!form.name.trim()) return '이름을 입력하세요';
		try {
			await api.post('/api/v1/security-groups', form, $auth.token ?? undefined, $auth.projectId ?? undefined);
			await fetchSecurityGroups();
			return true;
		} catch (e) {
			return e instanceof ApiError ? e.message : '생성 실패';
		}
	}

	async function deleteSecurityGroup(sgId: string, name: string) {
		if (!await confirmDialog(`"${name}" 보안 그룹을 삭제하시겠습니까?`)) return;
		try {
			await api.delete(`/api/v1/security-groups/${sgId}`, $auth.token ?? undefined, $auth.projectId ?? undefined);
			await fetchSecurityGroups();
		} catch (e) {
			toast.error('삭제 실패: ' + (e instanceof ApiError ? e.message : String(e)));
		}
	}

	async function addSgRule(
		sgId: string,
		form: { direction: string; protocol: string; port_range_min: string; port_range_max: string; remote_ip_prefix: string; ethertype: string }
	): Promise<string | true> {
		try {
			const body: Record<string, unknown> = {
				direction: form.direction,
				ethertype: form.ethertype,
			};
			if (form.protocol) body.protocol = form.protocol;
			if (form.port_range_min) body.port_range_min = parseInt(form.port_range_min);
			if (form.port_range_max) body.port_range_max = parseInt(form.port_range_max);
			if (form.remote_ip_prefix) body.remote_ip_prefix = form.remote_ip_prefix;
			await api.post(`/api/v1/security-groups/${sgId}/rules`, body, $auth.token ?? undefined, $auth.projectId ?? undefined);
			await fetchSecurityGroups();
			return true;
		} catch (e) {
			return e instanceof ApiError ? e.message : '규칙 추가 실패';
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
		if ($auth.projectId) fetchSecurityGroups();
	});
</script>

<div class="max-w-5xl mx-auto px-6 py-8">
	<div class="flex items-center justify-between mb-6">
		<div>
			<div class="flex items-center gap-2 text-sm text-ink-3 mb-1">
				<a href="/dashboard" class="hover:text-ink-2 transition-colors">대시보드</a>
				<span>›</span>
				<span class="text-ink-2">보안 그룹</span>
			</div>
			<h1 class="text-xl font-semibold text-ink-0">보안 그룹</h1>
		</div>
		<button
			onclick={() => { showSgModal = true; }}
			class="bg-action-warm hover:bg-action-warm-hover text-action-on-warm text-sm px-4 py-2 rounded-lg transition-colors"
		>+ 보안 그룹 생성</button>
	</div>

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
		<div class="space-y-3">
			{#each securityGroups as sg (sg.id)}
				<SecurityGroupCard
					{sg}
					onDelete={deleteSecurityGroup}
					onAddRule={addSgRule}
					onDeleteRule={deleteSgRule}
				/>
			{/each}
		</div>
	{/if}
</div>

<SecurityGroupCreateModal bind:open={showSgModal} onCreate={createSecurityGroup} />
