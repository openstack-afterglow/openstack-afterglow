<script lang="ts">
	import { useImageDetailController, isReservedKey } from '$lib/stores/imageDetailController.svelte';

	const s = useImageDetailController();
</script>

<div class="bg-surface-base border border-line rounded-lg p-5">
	<div class="flex items-center justify-between mb-3">
		<h3 class="text-xs font-semibold text-ink-2 uppercase tracking-wide">
			추가 속성 <span class="normal-case font-normal text-ink-3">({Object.keys(s.image!.properties).length})</span>
		</h3>
		{#if s.canEditMetadata && !s.editingProps}
			<button onclick={() => s.startEditProps()} class="text-xs text-action-warm hover:text-action-warm-hover">편집</button>
		{/if}
	</div>

	{#if !s.editingProps}
		{#if Object.keys(s.image!.properties).length === 0}
			<p class="text-xs text-ink-3">추가 속성이 없습니다.</p>
		{:else}
			<table class="w-full text-xs">
				<tbody>
					{#each Object.entries(s.image!.properties) as [k, v]}
						<tr class="border-b border-line/50">
							<td class="py-1.5 pr-4 text-ink-2 font-mono w-2/5">{k}</td>
							<td class="py-1.5 text-ink-2 font-mono break-all">{v}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		{/if}
	{:else}
		<table class="w-full text-xs mb-3">
			<tbody>
				{#each Object.entries(s.propsDraft) as [k, v]}
					<tr class="border-b border-line/50">
						<td class="py-1.5 pr-2 font-mono w-2/5 {isReservedKey(k) ? 'text-ink-3' : 'text-ink-2'}">
							{k}{#if isReservedKey(k)}&nbsp;<span class="text-[10px] text-ink-3">(예약)</span>{/if}
						</td>
						<td class="py-1.5 pr-2">
							{#if isReservedKey(k)}
								<span class="text-ink-3 font-mono break-all">{v}</span>
							{:else}
								<input bind:value={s.propsDraft[k]}
									class="w-full bg-surface-sunken border border-line-2 rounded px-2 py-1 text-ink-2 font-mono text-xs focus:outline-none focus:border-action-warm" />
							{/if}
						</td>
						<td class="py-1.5 text-right w-10">
							{#if !isReservedKey(k)}
								<button onclick={() => s.removeProperty(k)} class="text-red-400 hover:text-red-300 text-xs">삭제</button>
							{/if}
						</td>
					</tr>
				{/each}
			</tbody>
		</table>

		<div class="flex gap-2 mb-3">
			<input bind:value={s.newPropKey} placeholder="키"
				class="flex-1 bg-surface-sunken border border-line-2 rounded px-2 py-1 text-xs text-ink-0 font-mono focus:outline-none focus:border-action-warm"
				onkeydown={(e) => e.key === 'Enter' && s.addProperty()} />
			<input bind:value={s.newPropValue} placeholder="값"
				class="flex-1 bg-surface-sunken border border-line-2 rounded px-2 py-1 text-xs text-ink-0 font-mono focus:outline-none focus:border-action-warm"
				onkeydown={(e) => e.key === 'Enter' && s.addProperty()} />
			<button onclick={() => s.addProperty()} class="text-xs text-action-warm hover:text-action-warm-hover px-2 shrink-0">+ 추가</button>
		</div>

		{#if s.propsError}
			<p class="text-red-400 text-xs mb-2">{s.propsError}</p>
		{/if}

		<div class="flex gap-2 justify-end">
			<button onclick={() => s.cancelEditProps()} disabled={s.savingProps}
				class="text-xs text-ink-2 hover:text-ink-0 px-3 py-1 border border-line-2 rounded disabled:opacity-50">취소</button>
			<button onclick={() => s.saveProperties()} disabled={s.savingProps}
				class="text-xs text-action-on-warm bg-action-warm hover:bg-action-warm-hover disabled:bg-surface-selected px-3 py-1 rounded">
				{s.savingProps ? '저장 중...' : '저장'}
			</button>
		</div>
	{/if}
</div>
