<script lang="ts">
	import { onMount } from 'svelte';
	import { api } from '$lib/api/client';
	import MetricsPanel from '$lib/components/instance/MetricsPanel.svelte';

	interface AdminInstance {
		id: string;
		name: string;
		status: string;
		project_id: string | null;
		flavor: string;
		host: string | null;
	}

	interface PagedResponse<T> {
		items: T[];
		next_marker: string | null;
		count: number;
	}

	let {
		token,
		projectId,
		onReload,
		loadingInstances = $bindable(false),
	}: {
		token: string | undefined;
		projectId: string | undefined;
		onReload?: (fn: () => void) => void;
		loadingInstances?: boolean;
	} = $props();

	let instanceList = $state<AdminInstance[]>([]);
	let nextMarker = $state<string | null>(null);
	let search = $state('');
	let selectedInst = $state<AdminInstance | null>(null);

	const filtered = $derived(
		search
			? instanceList.filter(i =>
				i.name.toLowerCase().includes(search.toLowerCase()) ||
				(i.project_id ?? '').includes(search)
			)
			: instanceList
	);

	async function loadInstances(reset = false) {
		if (loadingInstances) return;
		if (reset) { instanceList = []; nextMarker = null; selectedInst = null; }
		loadingInstances = true;
		try {
			const marker = nextMarker && !reset ? `&marker=${nextMarker}` : '';
			const resp = await api.get<PagedResponse<AdminInstance>>(
				`/api/v1/admin/all-instances?limit=50${marker}`,
				token,
				projectId,
			);
			instanceList = reset ? resp.items : [...instanceList, ...resp.items];
			nextMarker = resp.next_marker;
		} catch {
			// 목록 로드 실패는 UI에 빈 상태로 처리
		} finally {
			loadingInstances = false;
		}
	}

	$effect(() => {
		onReload?.(() => loadInstances(true));
	});

	onMount(() => loadInstances(true));
</script>

<div class="flex flex-col md:flex-row gap-4 h-[calc(100vh-180px)] overflow-hidden">
	<!-- 왼쪽: 인스턴스 목록 -->
	<div data-tour="admin-monitoring-list" class="w-full md:w-72 flex-shrink-0 bg-surface-base border border-line rounded-xl overflow-hidden flex flex-col
		{selectedInst ? 'hidden md:flex' : 'flex'}">
		<div class="p-3 border-b border-line">
			<input
				type="text"
				placeholder="이름 또는 프로젝트 ID 검색"
				bind:value={search}
				class="w-full bg-surface-sunken rounded-lg px-3 py-1.5 text-sm text-ink-2 placeholder-ink-3 outline-none focus:ring-1 focus:ring-line-2"
			/>
		</div>

		<div class="overflow-y-auto flex-1">
			{#if loadingInstances && instanceList.length === 0}
				<div class="p-4 text-ink-3 text-sm text-center">인스턴스 목록 로딩 중...</div>
			{:else if filtered.length === 0}
				<div class="p-4 text-ink-3 text-sm text-center" data-tour="admin-monitoring-list-ready">
					{search ? '검색 결과 없음' : '인스턴스 없음'}
				</div>
			{:else}
				<div data-tour="admin-monitoring-list-ready"></div>
				{#each filtered as inst, index (inst.id)}
					<button
						onclick={() => (selectedInst = inst)}
						class="w-full text-left px-3 py-2.5 border-b border-line hover:bg-surface-sunken transition-colors
							{selectedInst?.id === inst.id ? 'bg-surface-sunken border-l-2 border-l-blue-500 pl-2.5' : ''}"
						data-tour={index === 0 ? 'admin-monitoring-row' : undefined}
					>
						<div class="flex items-center gap-2">
							<div class="w-1.5 h-1.5 rounded-full flex-shrink-0
								{inst.status === 'ACTIVE' ? 'bg-green-400' : inst.status === 'ERROR' ? 'bg-red-400' : 'bg-surface-selected'}"></div>
							<span class="text-sm text-ink-1 truncate">{inst.name}</span>
							{#if inst.flavor.toLowerCase().startsWith('gpu.')}
								<span class="text-xs text-purple-400 bg-purple-900/30 px-1 rounded flex-shrink-0">GPU</span>
							{/if}
						</div>
						<div class="text-xs text-ink-3 pl-3.5 mt-0.5 truncate font-mono">
							{inst.project_id?.slice(0, 12) ?? '-'}
						</div>
					</button>
				{/each}
			{/if}

			{#if nextMarker && !search}
				<button
					onclick={() => loadInstances()}
					disabled={loadingInstances}
					class="w-full py-2.5 text-xs text-action-warm hover:text-action-warm-hover disabled:text-ink-3 transition-colors"
				>
					{loadingInstances ? '로딩 중...' : '더 불러오기'}
				</button>
			{/if}
		</div>

		<div class="px-3 py-2 border-t border-line text-xs text-ink-3">
			{filtered.length}개 표시 / 총 {instanceList.length}개 로드
		</div>
	</div>

	<!-- 오른쪽: MetricsPanel -->
	<div class="flex-1 min-w-0 overflow-y-auto {selectedInst ? 'block' : 'hidden md:block'}">
		{#if selectedInst}
			<div class="bg-surface-base border border-line rounded-xl p-5">
				<button
					onclick={() => (selectedInst = null)}
					class="md:hidden mb-3 text-sm text-action-warm hover:text-action-warm-hover flex items-center gap-1"
					data-tour="admin-monitoring-back"
				>
					← 목록으로
				</button>
				<div class="flex items-center gap-3 mb-5">
					<span class="text-ink-0 font-semibold">{selectedInst.name}</span>
					<span class="text-xs text-ink-3 font-mono">{selectedInst.id.slice(0, 8)}…</span>
					<span class="text-xs px-2 py-0.5 rounded
						{selectedInst.status === 'ACTIVE' ? 'bg-green-900/30 text-green-400' :
						 selectedInst.status === 'ERROR' ? 'bg-red-900/30 text-red-400' :
						 'bg-surface-sunken text-ink-2'}"
					>{selectedInst.status}</span>
					{#if selectedInst.flavor}
						<span class="text-xs text-ink-3">{selectedInst.flavor}</span>
					{/if}
				</div>
				<div data-tour="admin-monitoring-metrics">
					<MetricsPanel
						instanceId={selectedInst.id}
						isGpu={selectedInst.flavor.toLowerCase().startsWith('gpu.')}
					/>
				</div>
			</div>
		{:else}
			<div class="flex items-center justify-center h-64 bg-surface-base border border-line rounded-xl">
				<div class="text-center">
					<div class="text-ink-3 text-sm mb-1">인스턴스를 선택하세요</div>
					<div class="text-ink-3 text-xs">왼쪽 목록에서 VM을 클릭하면 메트릭이 표시됩니다</div>
				</div>
			</div>
		{/if}
	</div>
</div>
