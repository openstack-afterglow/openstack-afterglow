<script lang="ts">
	import { t } from '$lib/i18n/ns/file-storage';
	import { ResponsiveTable, CompactResourceCard } from '$lib/components/ui';
	let { metadata }: { metadata: Record<string, string> } = $props();
</script>

{#if Object.keys(metadata).length > 0}
	<div class="bg-surface-base border border-line rounded-lg p-6">
		<h2 class="text-sm font-semibold text-ink-2 uppercase tracking-wide mb-4">{t('metadata.title')}</h2>
		<ResponsiveTable>
			{#snippet cards()}
				{#each Object.entries(metadata) as [k, v] (k)}
					<CompactResourceCard><strong class="text-xs break-all">{k}</strong><p class="font-mono text-xs break-all text-ink-2 line-clamp-2">{v}</p>{#snippet details()}<p class="font-mono break-all whitespace-pre-wrap">{v}</p>{/snippet}</CompactResourceCard>
				{/each}
			{/snippet}
		<table class="w-full text-sm">
			<tbody>
				{#each Object.entries(metadata) as [k, v]}
					<tr class="border-b border-line/50">
						<td class="py-2 pr-4 text-ink-2 text-xs w-1/3">{k}</td>
						<td class="py-2 text-ink-2 font-mono text-xs break-all">{v}</td>
					</tr>
				{/each}
			</tbody>
		</table>
		</ResponsiveTable>
	</div>
{/if}
