<script lang="ts">
	import { untrack } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import { goto } from '$app/navigation';

	import type { Network, SubnetDetail } from '$lib/types/networks';

	let networks = $state<Network[]>([]);
	let subnets = $state<SubnetDetail[]>([]);
	let form = $state({ name: '', vip_subnet_id: '', vip_network_id: '', description: '' });
	let creating = $state(false);
	let error = $state('');
	let loadingSubnets = $state(false);

	async function loadNetworks() {
		try {
			networks = await api.get<Network[]>('/api/v1/networks', $auth.token ?? undefined, $auth.projectId ?? undefined);
		} catch {
			// ignore
		}
	}

	async function onNetworkChange() {
		form.vip_subnet_id = '';
		subnets = [];
		if (!form.vip_network_id) return;
		loadingSubnets = true;
		try {
			const detail = await api.get<{ subnet_details: SubnetDetail[] }>(
				`/api/v1/networks/${form.vip_network_id}`,
				$auth.token ?? undefined, $auth.projectId ?? undefined
			);
			subnets = detail.subnet_details ?? [];
		} catch {
			subnets = [];
		} finally {
			loadingSubnets = false;
		}
	}

	async function createLb() {
		if (!form.name.trim() || !form.vip_subnet_id) {
			error = '이름과 VIP 서브넷을 입력해주세요';
			return;
		}
		creating = true;
		error = '';
		try {
			const lb = await api.post<{ id: string }>(
				'/api/v1/loadbalancers',
				{ name: form.name, vip_subnet_id: form.vip_subnet_id, description: form.description },
				$auth.token ?? undefined, $auth.projectId ?? undefined
			);
			goto(`/dashboard/network/loadbalancers/${lb.id}`);
		} catch (e) {
			error = e instanceof ApiError ? e.message : '생성 실패';
		} finally {
			creating = false;
		}
	}

	$effect(() => {
		if ($auth.token) untrack(() => loadNetworks());
	});
</script>

<div class="p-4 md:p-8 max-w-lg">
	<div class="flex items-center gap-4 mb-8">
		<button onclick={() => goto('/dashboard/network/loadbalancers')} class="text-ink-3 hover:text-ink-0 transition-colors text-sm">
			← 로드밸런서 목록
		</button>
		<h1 class="text-2xl font-bold text-ink-0">로드밸런서 생성</h1>
	</div>

	<div class="bg-surface-base border border-line-2 rounded-xl p-6 space-y-5">
		{#if error}
			<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm">{error}</div>
		{/if}

		<div>
			<label for="lb-name" class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">이름</label>
			<input
				id="lb-name"
				bind:value={form.name}
				type="text"
				placeholder="my-lb"
				class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2.5 text-ink-0 text-sm focus:outline-none focus:border-action-warm"
			/>
		</div>

		<div>
			<label for="lb-network" class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">네트워크</label>
			<select
				id="lb-network"
				bind:value={form.vip_network_id}
				onchange={onNetworkChange}
				class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2.5 text-ink-0 text-sm focus:outline-none focus:border-action-warm"
			>
				<option value="">네트워크 선택</option>
				{#each networks.filter(n => !n.is_external) as net}
					<option value={net.id}>{net.name}</option>
				{/each}
			</select>
		</div>

		{#if form.vip_network_id}
			<div>
				<label for="lb-subnet" class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">VIP 서브넷</label>
				{#if loadingSubnets}
					<div class="text-ink-3 text-sm">서브넷 로딩 중...</div>
				{:else if subnets.length === 0}
					<div class="text-ink-3 text-sm">서브넷이 없습니다</div>
				{:else}
					<select
						id="lb-subnet"
						bind:value={form.vip_subnet_id}
						class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2.5 text-ink-0 text-sm focus:outline-none focus:border-action-warm"
					>
						<option value="">서브넷 선택</option>
						{#each subnets as subnet}
							<option value={subnet.id}>{subnet.name || subnet.id.slice(0, 8)} ({subnet.cidr})</option>
						{/each}
					</select>
				{/if}
			</div>
		{/if}

		<div>
			<label for="lb-desc" class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">설명 (선택)</label>
			<input
				id="lb-desc"
				bind:value={form.description}
				type="text"
				placeholder="설명"
				class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2.5 text-ink-0 text-sm focus:outline-none focus:border-action-warm"
			/>
		</div>

		<div class="flex justify-end gap-3 pt-2">
			<button
				onclick={() => goto('/dashboard/network/loadbalancers')}
				class="px-4 py-2 text-sm text-ink-2 hover:text-ink-0 transition-colors"
			>
				취소
			</button>
			<button
				onclick={createLb}
				disabled={creating}
				class="px-5 py-2 bg-action-warm hover:bg-action-warm-hover disabled:bg-surface-selected disabled:text-ink-3 text-action-on-warm text-sm font-medium rounded-lg transition-colors"
			>
				{creating ? '생성 중...' : '생성'}
			</button>
		</div>
	</div>
</div>
