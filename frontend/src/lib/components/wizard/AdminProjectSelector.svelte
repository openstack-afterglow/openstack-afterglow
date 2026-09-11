<script lang="ts">
	import { closeWizard } from '$lib/stores/wizard';
	import { useVmCreate } from '$lib/stores/vmCreateStore.svelte';
	import LoadingSpinner from '$lib/components/LoadingSpinner.svelte';

	const s = useVmCreate();
</script>

<div class="flex items-start justify-between mb-6">
	<div>
		<h1 class="text-xl font-bold text-ink-0">VM 생성 <span class="text-sm font-normal text-action-warm ml-1">관리자</span></h1>
		<p class="text-sm text-ink-3 mt-0.5">대상 프로젝트 선택</p>
	</div>
	<!-- 닫기는 SlidePanel(`[data-slide-panel-close]`)과 하단 취소 버튼이 담당한다. -->
</div>

<p class="text-sm text-ink-2 mb-4">VM을 생성할 프로젝트를 선택하세요. 선택한 프로젝트의 네트워크, 볼륨, 보안 그룹을 사용합니다.</p>

{#if s.adminProjectsLoading}
	<div class="flex items-center justify-center py-10">
		<LoadingSpinner size="md" color="blue">프로젝트 로드 중...</LoadingSpinner>
	</div>
{:else if s.adminProjects.length === 0}
	<div class="text-center py-10 text-ink-3 text-sm">프로젝트 목록을 불러올 수 없습니다.</div>
{:else}
	<div class="relative mb-3">
		<svg class="w-4 h-4 text-ink-3 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" fill="none" stroke="currentColor" viewBox="0 0 24 24">
			<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-4.35-4.35M10 18a8 8 0 100-16 8 8 0 000 16z"/>
		</svg>
		<input
			type="text"
			bind:value={s.adminProjectSearch}
			placeholder="프로젝트 이름 또는 ID 검색..."
			class="w-full bg-surface-sunken border border-line-2 text-sm text-ink-1 rounded-lg pl-9 pr-9 py-2 focus:outline-none focus:border-action-warm placeholder-ink-3"
		/>
		{#if s.adminProjectSearch}
			<button
				onclick={() => (s.adminProjectSearch = '')}
				class="absolute right-3 top-1/2 -translate-y-1/2 text-ink-3 hover:text-ink-0 text-sm"
				aria-label="검색어 지우기"
			>✕</button>
		{/if}
	</div>

	{#if s.filteredAdminProjects.length === 0}
		<div class="text-center py-10 text-ink-3 text-sm">검색 결과가 없습니다.</div>
	{:else}
		<div class="space-y-2 max-h-[60vh] overflow-y-auto pr-1">
			{#each s.filteredAdminProjects as proj}
				{@const q = s.adminProjectQuotas.get(proj.id)}
				<button
					onclick={() => s.selectAdminProject(proj.id, proj.name)}
					class="w-full text-left px-4 py-3 rounded-lg bg-surface-sunken hover:bg-surface-selected border border-line-2 hover:border-line-2 transition-colors"
				>
					<div class="flex items-start justify-between gap-3">
						<div class="min-w-0 flex-1">
							<div class="text-ink-0 text-sm font-medium truncate">{proj.name}</div>
							<div class="text-ink-3 text-xs font-mono mt-0.5 truncate">{proj.id}</div>
						</div>
						{#if s.adminProjectQuotas.size === 0}
							<div class="text-ink-3 text-xs flex-shrink-0">quota 로딩 중...</div>
						{:else if q}
							<div class="flex flex-wrap items-center gap-1.5 flex-shrink-0 justify-end">
								<span class="px-1.5 py-0.5 rounded text-[11px] font-mono {s.isExhausted(q.instances) ? 'bg-red-900/40 text-red-300 border border-red-800/50' : 'bg-surface-base text-ink-2 border border-line-2'}" title="남은 인스턴스 (사용 {q.instances?.used ?? 0} / {q.instances?.quota < 0 ? '∞' : q.instances?.quota})">
									VM {s.fmtRemaining(q.instances)}
								</span>
								<span class="px-1.5 py-0.5 rounded text-[11px] font-mono {s.isExhausted(q.cpu) ? 'bg-red-900/40 text-red-300 border border-red-800/50' : 'bg-surface-base text-ink-2 border border-line-2'}" title="남은 vCPU (사용 {q.cpu?.used ?? 0} / {q.cpu?.quota < 0 ? '∞' : q.cpu?.quota})">
									CPU {s.fmtRemaining(q.cpu)}
								</span>
								<span class="px-1.5 py-0.5 rounded text-[11px] font-mono {s.isExhausted(q.ram_mb) ? 'bg-red-900/40 text-red-300 border border-red-800/50' : 'bg-surface-base text-ink-2 border border-line-2'}" title="남은 RAM MB (사용 {q.ram_mb?.used ?? 0} / {q.ram_mb?.quota < 0 ? '∞' : q.ram_mb?.quota})">
									RAM {q.ram_mb && q.ram_mb.quota >= 0 ? Math.max(0, Math.floor((q.ram_mb.quota - q.ram_mb.used) / 1024)) + 'GB' : '∞'}
								</span>
								<span class="px-1.5 py-0.5 rounded text-[11px] font-mono {s.isExhausted(q.disk_gb) ? 'bg-red-900/40 text-red-300 border border-red-800/50' : 'bg-surface-base text-ink-2 border border-line-2'}" title="남은 디스크 GB (사용 {q.disk_gb?.used ?? 0} / {q.disk_gb?.quota < 0 ? '∞' : q.disk_gb?.quota})">
									DISK {s.fmtRemaining(q.disk_gb)}{q.disk_gb && q.disk_gb.quota >= 0 ? 'GB' : ''}
								</span>
							</div>
						{:else}
							<div class="text-ink-3 text-xs flex-shrink-0">quota 없음</div>
						{/if}
					</div>
				</button>
			{/each}
		</div>
	{/if}
{/if}

<div class="flex justify-start mt-6 pt-4 border-t border-line">
	<button
		onclick={closeWizard}
		class="px-4 py-2 text-sm text-ink-2 hover:text-ink-0 border border-line-2 rounded-lg hover:border-line-2 transition-colors"
	>취소</button>
</div>
