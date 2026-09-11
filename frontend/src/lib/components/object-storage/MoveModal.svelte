<script lang="ts">
	import { useObjectBrowser } from '$lib/stores/objectBrowser.svelte';

	interface Props { bulk?: boolean; }
	let { bulk = false }: Props = $props();

	const s = useObjectBrowser();
	const show = $derived(bulk ? s.showBulkMove : s.showMove);
</script>

{#if show}
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-surface-scrim/70"
		onclick={() => { if (bulk) s.showBulkMove = false; else s.showMove = false; }}
		role="dialog" aria-modal="true" tabindex="-1"
		onkeydown={(e) => e.key === 'Escape' && (bulk ? (s.showBulkMove = false) : (s.showMove = false))}
	>
		<div
			class="bg-surface-base border border-line rounded-xl p-6 w-full max-w-md shadow-[var(--shadow-restraint)]"
			onclick={(e) => e.stopPropagation()}
			role="none"
			onkeydown={(e) => e.stopPropagation()}
		>
			{#if bulk}
				<h2 class="text-ink-0 font-semibold mb-1">일괄 이동</h2>
				<p class="text-indigo-400 text-xs mb-4">{s.selectedCount}개 항목 선택됨</p>
			{:else}
				<h2 class="text-ink-0 font-semibold mb-1">파일 이동</h2>
				<p class="text-indigo-400 text-sm mb-4 break-all">{s.displayName(s.moveTarget)}</p>
			{/if}

			{#if s.moveError}
				<div class="bg-red-900/20 border border-red-800 rounded-lg px-3 py-2 text-red-400 text-xs mb-3">{s.moveError}</div>
			{/if}

			<label class="text-ink-2 text-xs mb-1 block font-medium" for="field-movemodal-36">대상 버킷</label>
			{#if s.moveContainers.length > 0}
				<select id="field-movemodal-36"
					value={s.moveDestContainer}
					onchange={(e) => s.onMoveContainerChange((e.target as HTMLSelectElement).value)}
					class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0 mb-4 focus:outline-none focus:border-indigo-500"
				>
					{#each s.moveContainers as c}
						<option value={c.name}>{c.name} ({c.count} items)</option>
					{/each}
				</select>
			{:else}
				<input
					type="text"
					bind:value={s.moveDestContainer}
					placeholder="버킷 이름"
					class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0 mb-4 focus:outline-none focus:border-indigo-500"
				/>
			{/if}

			<label class="text-ink-2 text-xs mb-1 block font-medium" for="field-movemodal-56">대상 디렉토리</label>
			{#if s.moveLoadingDirs}
				<div class="bg-surface-sunken border border-line-2 rounded-lg p-3 mb-3">
					<p class="text-ink-3 text-xs">디렉토리 목록 로딩 중...</p>
				</div>
			{:else}
				<div class="bg-surface-sunken border border-line-2 rounded-lg max-h-48 overflow-y-auto mb-3">
					{#each s.moveDirectories.filter(d =>
						d === '/ (루트)' ||
						(bulk
							? ![...s.selected].some(sel => d === sel || d.startsWith(sel))
							: (d !== s.moveTarget && !d.startsWith(s.moveTarget)))
					) as dir}
						{@const isSelected = (dir === '/ (루트)' && s.moveSelectedDir === '') || dir === s.moveSelectedDir}
						<button id="field-movemodal-56"
							onclick={() => bulk ? s.selectBulkMoveDir(dir) : s.selectMoveDir(dir)}
							class="w-full text-left px-3 py-2 text-sm flex items-center gap-2 transition-colors {isSelected ? 'bg-indigo-600/20 text-indigo-300 border-l-2 border-indigo-500' : 'text-ink-2 hover:bg-surface-selected/50'}"
						>
							<svg class="w-4 h-4 shrink-0 {isSelected ? 'text-indigo-400' : 'text-action-warm'}" viewBox="0 0 20 20" fill="currentColor">
								<path d="M2 6a2 2 0 012-2h4l2 2h6a2 2 0 012 2v6a2 2 0 01-2 2H4a2 2 0 01-2-2V6z"/>
							</svg>
							<span class="truncate">{dir === '/ (루트)' ? '/ (루트)' : dir}</span>
							{#if isSelected}
								<svg class="w-4 h-4 ml-auto text-indigo-400 shrink-0" viewBox="0 0 20 20" fill="currentColor">
									<path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd"/>
								</svg>
							{/if}
						</button>
					{/each}
					{#if !bulk && s.moveDirectories.length <= 1}
						<p class="text-ink-3 text-xs px-3 py-2">디렉토리가 없습니다. 루트로 이동됩니다.</p>
					{/if}
				</div>
			{/if}

			{#if s.moveDestinationChosen}
				<div class="bg-surface-sunken/50 border border-line-2 rounded px-3 py-2 mb-4">
					<p class="text-[10px] text-ink-3 uppercase tracking-wider mb-0.5">{bulk ? '이동 위치' : '이동 경로'}</p>
					<p class="text-ink-0 text-sm font-mono break-all">{s.moveDestContainer} / {s.moveDest || '(루트)'}</p>
				</div>
			{/if}

			<div class="flex gap-2 justify-end">
				<button
					onclick={() => { if (bulk) s.showBulkMove = false; else s.showMove = false; }}
					class="text-xs text-ink-2 hover:text-ink-0 px-4 py-2 rounded-lg border border-line-2 transition-colors"
				>취소</button>
				<button
					onclick={bulk ? s.doBulkMove : s.doMove}
					disabled={bulk ? s.bulkMoving || !s.moveDestinationChosen : (s.moving || !s.moveDestinationChosen)}
					class="text-xs text-ink-0 bg-indigo-600 hover:bg-indigo-500 disabled:bg-surface-selected disabled:text-ink-3 px-4 py-2 rounded-lg border border-indigo-500 disabled:border-line-2 transition-colors"
				>
					{#if bulk}
						{s.bulkMoving ? '이동 중...' : `${s.selectedCount}개 이동`}
					{:else}
						{s.moving ? '이동 중...' : '이동'}
					{/if}
				</button>
			</div>
		</div>
	</div>
{/if}
