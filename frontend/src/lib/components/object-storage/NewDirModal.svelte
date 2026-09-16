<script lang="ts">
	import { useObjectBrowser } from '$lib/stores/objectBrowser.svelte';
	const s = useObjectBrowser();
</script>

{#if s.showNewDir}
	<div class="fixed inset-0 z-50 flex items-center justify-center bg-surface-scrim/70">
		<div class="bg-surface-base border border-line rounded-xl p-6 w-full max-w-sm shadow-[var(--shadow-restraint)]">
			<h2 class="text-ink-0 font-semibold mb-4">새 폴더 만들기</h2>
			{#if s.dirError}<p class="text-red-400 text-xs mb-2">{s.dirError}</p>{/if}
			<input
				type="text"
				bind:value={s.newDirName}
				placeholder="폴더 이름"
				class="w-full bg-surface-sunken border border-line-2 rounded px-3 py-2 text-ink-0 text-sm mb-4 focus:outline-none focus:border-indigo-500"
				onkeydown={(e) => e.key === 'Enter' && s.createDirectory()}
			/>
			<div class="flex gap-2 justify-end">
				<button
					onclick={() => { s.showNewDir = false; }}
					class="text-xs text-ink-2 hover:text-ink-0 px-3 py-1.5 rounded border border-line-2"
				>취소</button>
				<button
					onclick={s.createDirectory}
					disabled={s.creatingDir}
					class="text-xs text-ink-0 bg-indigo-600 hover:bg-indigo-500 disabled:bg-surface-selected px-3 py-1.5 rounded border border-indigo-500 disabled:border-line-2"
				>{s.creatingDir ? '생성 중...' : '만들기'}</button>
			</div>
		</div>
	</div>
{/if}
