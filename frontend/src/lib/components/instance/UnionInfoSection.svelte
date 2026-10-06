<script lang="ts">
	import { useInstanceDetailController } from '$lib/stores/instanceDetailController.svelte';
	import { t } from '$lib/i18n/ns/instance';

	const s = useInstanceDetailController();

	const strategyLabel: Record<string, string> = {
		get prebuilt() { return t('union.prebuilt'); },
		get dynamic() { return t('union.dynamic'); },
	};
</script>

<div class="motion-enter bg-surface-base border border-line rounded-lg p-6 mb-4">
	<h2 class="text-sm font-semibold text-ink-2 uppercase tracking-wide mb-4">{t('union.title')}</h2>
	<dl class="grid grid-cols-1 @3xl/panel:grid-cols-2 gap-x-8 gap-y-3">
		<div>
			<dt class="text-xs text-ink-2 mb-0.5">{t('union.strategy')}</dt>
			<dd class="text-sm text-ink-2">
				{s.instance!.union_strategy ? strategyLabel[s.instance!.union_strategy] ?? s.instance!.union_strategy : '-'}
			</dd>
		</div>
		<div>
			<dt class="text-xs text-ink-2 mb-0.5">{t('union.libraries')}</dt>
			<dd class="flex flex-wrap gap-1">
				{#each s.instance!.union_libraries.filter(Boolean) as lib}
					<span class="px-1.5 py-0.5 bg-surface-selected/40 text-warm-text rounded text-xs">{lib}</span>
				{:else}
					<span class="text-sm text-ink-2">-</span>
				{/each}
			</dd>
		</div>
		{#if s.instance!.union_upper_volume_id}
			<div class="col-span-2">
				<dt class="text-xs text-ink-2 mb-0.5">{t('union.upperVolume')}</dt>
				<dd>
					<a
						href="/dashboard/volumes/{s.instance!.union_upper_volume_id}"
						class="text-sm text-warm-text hover:text-warm-text-hover font-mono transition-colors"
					>
						{s.instance!.union_upper_volume_id}
					</a>
				</dd>
			</div>
		{/if}
		{#if (s.instance!.union_share_ids ?? []).filter(Boolean).length > 0}
			<div class="col-span-2">
				<dt class="text-xs text-ink-2 mb-1.5">{t('union.attachedFileStorage')}</dt>
				<dd class="flex flex-col gap-1">
					{#each (s.instance!.union_share_ids ?? []).filter(Boolean) as sid}
						<a
							href="/dashboard/file-storage/{sid}"
							class="text-sm text-warm-text hover:text-warm-text-hover font-mono transition-colors"
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
	<div class="motion-enter bg-surface-base border border-line rounded-lg p-6">
		<h2 class="text-sm font-semibold text-ink-2 uppercase tracking-wide mb-4">{t('union.metadata')}</h2>
		<table class="w-full text-sm">
			<tbody>
				{#each Object.entries(s.instance!.metadata ?? {}) as [k, v]}
					<tr class="border-b border-line/50">
						<td class="py-2 pr-4 text-ink-2 text-xs w-1/3">{k}</td>
						<td class="py-2 text-ink-2 font-mono text-xs break-all">{v}</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
{/if}
