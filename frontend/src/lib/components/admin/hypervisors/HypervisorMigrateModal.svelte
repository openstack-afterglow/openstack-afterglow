<script lang="ts">
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';

	let {
		open = $bindable(false),
		serverId,
		serverName,
		type,
		onMigrated,
	}: {
		open?: boolean;
		serverId: string;
		serverName: string;
		type: 'live' | 'cold';
		onMigrated: () => void;
	} = $props();

	let hosts = $state<{ name: string; cpu_model?: string | null }[]>([]);
	let selectedHost = $state('');
	let loading = $state(false);
	let error = $state('');

	$effect(() => {
		if (open) {
			selectedHost = '';
			error = '';
			hosts = [];
			fetchHosts();
		}
	});

	// 라이브: server_id 전달 + CPU 모델 필터(기본). 콜드: CPU 필터 없이 전체(소스 제외)
	async function fetchHosts() {
		try {
			const params = new URLSearchParams({ server_id: serverId });
			if (type === 'cold') params.set('cpu_filter', 'false');
			hosts = await api.get<{ name: string; cpu_model?: string | null }[]>(
				`/api/v1/admin/compute-hosts?${params.toString()}`,
				$auth.token ?? undefined,
				$auth.projectId ?? undefined,
			);
		} catch {
			hosts = [];
		}
	}

	// 라이브 마이그레이션 CPU 호환 힌트
	const cpuModelHint = $derived(
		type === 'cold'
			? '모든 호스트 표시 (CPU 모델 무관)'
			: hosts.length > 0 && hosts[0].cpu_model
				? `${hosts[0].cpu_model} 호환 호스트만 표시`
				: null
	);

	async function doMigrate() {
		loading = true;
		error = '';
		try {
			if (type === 'live') {
				await api.post(
					`/api/v1/admin/instances/${serverId}/live-migrate`,
					{ host: selectedHost || null, block_migration: 'auto' },
					$auth.token ?? undefined,
					$auth.projectId ?? undefined,
				);
			} else {
				await api.post(
					`/api/v1/admin/instances/${serverId}/cold-migrate`,
					{ host: selectedHost || null },
					$auth.token ?? undefined,
					$auth.projectId ?? undefined,
				);
			}
			open = false;
			onMigrated();
		} catch (e) {
			error = e instanceof ApiError ? e.message : '마이그레이션 실패';
		} finally {
			loading = false;
		}
	}
</script>

<div
	class="fixed inset-0 bg-surface-scrim/60 flex items-center justify-center z-50"
	role="dialog"
	onclick={(event) => { if (event.target === event.currentTarget) (() => { open = false; })(); }}
	onkeydown={(e) => e.key === 'Escape' && (open = false)}
	tabindex="-1"
>
	<div class="bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-md mx-4 shadow-[var(--shadow-restraint)]">
		<h2 class="text-lg font-semibold text-ink-0 mb-1">{type === 'live' ? '라이브 마이그레이션' : '콜드 마이그레이션'}</h2>
		<p class="text-xs text-ink-3 mb-1"><span class="text-ink-2">{serverName}</span></p>
		<p class="text-xs text-ink-3 mb-5">{type === 'live' ? '인스턴스 실행 중에 다른 호스트로 이동합니다.' : '인스턴스를 종료하고 다른 호스트로 이동합니다.'}</p>
		{#if error}
			<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm mb-4">{error}</div>
		{/if}
		<div>
			<div class="flex items-baseline justify-between mb-1.5">
				<label class="text-xs text-ink-2 uppercase tracking-wide" for="field-hypervisormigratemodal-102">대상 호스트 <span class="text-ink-3">(선택 안 하면 자동)</span></label>
				{#if cpuModelHint}
					<span class="text-xs text-ink-3">{cpuModelHint}</span>
				{/if}
			</div>
			<select id="field-hypervisormigratemodal-102" bind:value={selectedHost} class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm">
				<option value="">자동 선택</option>
				{#each hosts as h}
					<option value={h.name}>{h.name}</option>
				{/each}
			</select>
		</div>
		<div class="flex justify-end gap-3 mt-6">
			<button onclick={() => { open = false; }} class="px-4 py-2 bg-surface-selected hover:bg-surface-selected text-ink-0 text-sm font-medium rounded-lg">취소</button>
			<button onclick={doMigrate} disabled={loading} class="px-4 py-2 bg-cyan-700 hover:bg-cyan-600 text-ink-0 text-sm font-medium rounded-lg disabled:opacity-30">
				{loading ? '마이그레이션 중...' : '마이그레이션'}
			</button>
		</div>
	</div>
</div>
