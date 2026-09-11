<script lang="ts">
	import { useInstanceDetailController } from '$lib/stores/instanceDetailController.svelte';

	const s = useInstanceDetailController();

	const strategyLabel: Record<string, string> = {
		prebuilt: '사전 빌드',
		dynamic: '동적 생성',
	};
</script>

<div class="bg-surface-base border border-line rounded-lg p-6 mb-4">
	<h2 class="text-sm font-semibold text-ink-2 uppercase tracking-wide mb-4">Afterglow 정보</h2>
	<dl class="grid grid-cols-1 @3xl/panel:grid-cols-2 gap-x-8 gap-y-3">
		<div>
			<dt class="text-xs text-ink-3 mb-0.5">전략</dt>
			<dd class="text-sm text-ink-2">
				{s.instance!.union_strategy ? strategyLabel[s.instance!.union_strategy] ?? s.instance!.union_strategy : '-'}
			</dd>
		</div>
		<div>
			<dt class="text-xs text-ink-3 mb-0.5">라이브러리</dt>
			<dd class="flex flex-wrap gap-1">
				{#each s.instance!.union_libraries.filter(Boolean) as lib}
					<span class="px-1.5 py-0.5 bg-surface-selected/40 text-action-warm rounded text-xs">{lib}</span>
				{:else}
					<span class="text-sm text-ink-3">-</span>
				{/each}
			</dd>
		</div>
		{#if s.instance!.union_upper_volume_id}
			<div class="col-span-2">
				<dt class="text-xs text-ink-3 mb-0.5">Upper 볼륨</dt>
				<dd>
					<a
						href="/dashboard/volumes/{s.instance!.union_upper_volume_id}"
						class="text-sm text-action-warm hover:text-action-warm-hover font-mono transition-colors"
					>
						{s.instance!.union_upper_volume_id}
					</a>
				</dd>
			</div>
		{/if}
		{#if (s.instance!.union_share_ids ?? []).filter(Boolean).length > 0}
			<div class="col-span-2">
				<dt class="text-xs text-ink-3 mb-1.5">연결된 파일 스토리지</dt>
				<dd class="flex flex-col gap-1">
					{#each (s.instance!.union_share_ids ?? []).filter(Boolean) as sid}
						<a
							href="/dashboard/file-storage/{sid}"
							class="text-sm text-action-warm hover:text-action-warm-hover font-mono transition-colors"
						>
							{sid}
						</a>
					{/each}
				</dd>
			</div>
		{/if}
	</dl>
</div>

{#if Object.keys(s.instance!.metadata ?? {}).length > 0}
	<div class="bg-surface-base border border-line rounded-lg p-6">
		<h2 class="text-sm font-semibold text-ink-2 uppercase tracking-wide mb-4">메타데이터</h2>
		<table class="w-full text-sm">
			<tbody>
				{#each Object.entries(s.instance!.metadata ?? {}) as [k, v]}
					<tr class="border-b border-line/50">
						<td class="py-2 pr-4 text-ink-3 text-xs w-1/3">{k}</td>
						<td class="py-2 text-ink-2 font-mono text-xs break-all">{v}</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
{/if}
