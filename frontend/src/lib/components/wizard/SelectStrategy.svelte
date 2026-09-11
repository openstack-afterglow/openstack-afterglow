<script lang="ts">
	import { betaFeatures } from '$lib/stores/betaFeatures';
	let {
		scheduling,
		onSchedulingChange,
		strategy,
		hasLibraries,
		hasPrebuilt,
		onStrategyChange,
		mountProtocol,
		onProtocolChange,
	}: {
		scheduling: 'standard' | 'ha';
		onSchedulingChange: (s: 'standard' | 'ha') => void;
		strategy: 'prebuilt' | 'dynamic' | null;
		hasLibraries: boolean;
		hasPrebuilt: boolean;
		onStrategyChange: (s: 'prebuilt' | 'dynamic') => void;
		mountProtocol: 'CEPHFS' | 'NFS';
		onProtocolChange: (p: 'CEPHFS' | 'NFS') => void;
	} = $props();

	$effect(() => {
		if (!$betaFeatures.haDeploy && scheduling === 'ha') {
			onSchedulingChange('standard');
		}
	});
</script>

<!-- 섹션 A: 스케줄링 (항상) -->
<div class="mb-6">
	<p class="text-xs font-semibold text-ink-3 uppercase tracking-wide mb-3">스케줄링 / 내고장성</p>
	<div class="flex flex-col gap-3">
		<button
			onclick={() => onSchedulingChange('standard')}
			class="flex items-start gap-3 p-4 rounded-xl border text-left transition-all {scheduling === 'standard'
				? 'border-action-warm bg-surface-selected/15 ring-1 ring-line-2/30'
				: 'border-line-2 bg-surface-base hover:border-line-2'}"
		>
			<div class="w-5 h-5 rounded-md flex-shrink-0 mt-0.5 flex items-center justify-center border transition-colors
				{scheduling === 'standard' ? 'bg-action-warm border-action-warm' : 'border-line-2 bg-surface-sunken'}">
				{#if scheduling === 'standard'}
					<svg class="w-3 h-3 text-ink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7"/>
					</svg>
				{/if}
			</div>
			<div class="flex-1 flex flex-col gap-1.5">
				<div class="flex items-center gap-2.5 flex-wrap">
					<b class="text-sm font-semibold text-ink-0">일반 배포</b>
					<span class="ml-auto text-ink-3 font-mono text-[11.5px]">⚡ ~30초 부팅</span>
				</div>
				<p class="text-xs text-ink-2 leading-relaxed">단일 호스트 고정 배치. 호스트 장애 시 수동 복구가 필요합니다.</p>
			</div>
		</button>

		{#if $betaFeatures.haDeploy}
		<button
			onclick={() => onSchedulingChange('ha')}
			class="flex items-start gap-3 p-4 rounded-xl border text-left transition-all {scheduling === 'ha'
				? 'border-action-warm bg-surface-selected/15 ring-1 ring-line-2/30'
				: 'border-line-2 bg-surface-base hover:border-line-2'}"
		>
			<div class="w-5 h-5 rounded-md flex-shrink-0 mt-0.5 flex items-center justify-center border transition-colors
				{scheduling === 'ha' ? 'bg-action-warm border-action-warm' : 'border-line-2 bg-surface-sunken'}">
				{#if scheduling === 'ha'}
					<svg class="w-3 h-3 text-ink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7"/>
					</svg>
				{/if}
			</div>
			<div class="flex-1 flex flex-col gap-1.5">
				<div class="flex items-center gap-2.5 flex-wrap">
					<b class="text-sm font-semibold text-ink-0">HA 배포</b>
					<span class="px-1.5 py-0.5 rounded bg-surface-selected/30 border border-action-warm text-action-warm text-[11px] font-mono">권장</span>
					<span class="ml-auto text-ink-3 font-mono text-[11.5px]">🛡 고가용성</span>
				</div>
				<p class="text-xs text-ink-2 leading-relaxed">호스트 장애 시 자동 evacuate. Masakari 등 HA 솔루션 활성화 시 동작합니다.</p>
			</div>
		</button>
		{/if}
	</div>
</div>

<!-- 섹션 B: 레이어 마운트 방식 (라이브러리 선택 시에만) -->
{#if hasLibraries}
	<div class="border-t border-line pt-5">
		<p class="text-xs font-semibold text-ink-3 uppercase tracking-wide mb-3">레이어 마운트 방식</p>

		{#if !hasPrebuilt}
			<div class="mb-3 px-3 py-2 rounded-lg bg-yellow-900/20 border border-yellow-800 text-yellow-400 text-xs">
				선택된 라이브러리 중 사전 빌드 가능한 항목이 없어 동적 생성만 가능합니다.
			</div>
		{/if}

		<div class="flex flex-col gap-3">
			<button
				onclick={() => { if (hasPrebuilt) onStrategyChange('prebuilt'); }}
				disabled={!hasPrebuilt}
				class="flex items-start gap-3 p-4 rounded-xl border text-left transition-all {strategy === 'prebuilt'
					? 'border-action-warm bg-surface-selected/15 ring-1 ring-line-2/30'
					: 'border-line-2 bg-surface-base hover:border-line-2'} {!hasPrebuilt ? 'opacity-40 cursor-not-allowed' : ''}"
			>
				<div class="w-5 h-5 rounded-md flex-shrink-0 mt-0.5 flex items-center justify-center border transition-colors
					{strategy === 'prebuilt' ? 'bg-action-warm border-action-warm' : 'border-line-2 bg-surface-sunken'}">
					{#if strategy === 'prebuilt'}
						<svg class="w-3 h-3 text-ink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7"/>
						</svg>
					{/if}
				</div>
				<div class="flex-1 flex flex-col gap-1.5">
					<div class="flex items-center gap-2.5 flex-wrap">
						<b class="text-sm font-semibold text-ink-0">사전 빌드 레이어 사용</b>
						<span class="ml-auto text-ink-3 font-mono text-[11.5px]">⚡ 빠른 부팅</span>
					</div>
					<p class="text-xs text-ink-2 leading-relaxed">미리 빌드된 OverlayFS 레이어를 읽기 전용 마운트. 부팅이 빠릅니다.</p>
				</div>
			</button>

			<button
				onclick={() => onStrategyChange('dynamic')}
				class="flex items-start gap-3 p-4 rounded-xl border text-left transition-all {strategy === 'dynamic'
					? 'border-action-warm bg-surface-selected/15 ring-1 ring-line-2/30'
					: 'border-line-2 bg-surface-base hover:border-line-2'}"
			>
				<div class="w-5 h-5 rounded-md flex-shrink-0 mt-0.5 flex items-center justify-center border transition-colors
					{strategy === 'dynamic' ? 'bg-action-warm border-action-warm' : 'border-line-2 bg-surface-sunken'}">
					{#if strategy === 'dynamic'}
						<svg class="w-3 h-3 text-ink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7"/>
						</svg>
					{/if}
				</div>
				<div class="flex-1 flex flex-col gap-1.5">
					<div class="flex items-center gap-2.5 flex-wrap">
						<b class="text-sm font-semibold text-ink-0">cloud-init 동적 생성</b>
						<span class="ml-auto text-ink-3 font-mono text-[11.5px]">⏱ ~3-5분 부팅</span>
					</div>
					<p class="text-xs text-ink-2 leading-relaxed">첫 부팅 시 cloud-init 스크립트로 레이어를 직접 빌드. 유연하게 조합 가능합니다.</p>
				</div>
			</button>
		</div>

		<!-- mountProtocol 토글 (dynamic 선택 시) -->
		{#if strategy === 'dynamic'}
			<div class="mt-4 flex items-center gap-3">
				<span class="text-xs text-ink-3">마운트 프로토콜</span>
				{#each (['CEPHFS', 'NFS'] as const) as p}
					<button
						onclick={() => onProtocolChange(p)}
						class="px-3 py-1 rounded-md text-xs font-mono border transition-colors {mountProtocol === p
							? 'bg-surface-selected/40 border-action-warm text-action-warm'
							: 'border-line-2 text-ink-3 hover:border-line-2'}"
					>{p}</button>
				{/each}
			</div>
		{/if}
	</div>
{/if}
