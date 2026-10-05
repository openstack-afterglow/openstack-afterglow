<script lang="ts">
	import { t } from '$lib/i18n/ns/network-resources';
	import { useNetworkDetailController } from '$lib/stores/networkDetailController.svelte';

	const s = useNetworkDetailController();
</script>

<div class="bg-surface-base border border-line rounded-xl p-4">
	<h3 class="text-xs text-ink-2 uppercase tracking-wide mb-3">{t('network.info.title')}</h3>
	<dl class="space-y-2 text-xs">
		<div class="flex justify-between">
			<dt class="text-ink-2">{t('network.labels.id')}</dt>
			<dd class="text-ink-2 font-mono text-xs break-all">{s.network!.id}</dd>
		</div>
		<div class="flex justify-between">
			<dt class="text-ink-2">{t('network.labels.status')}</dt>
			<dd class="{s.network!.status === 'ACTIVE' ? 'text-green-400' : 'text-ink-2'}">{s.network!.status}</dd>
		</div>
		<div class="flex justify-between">
			<dt class="text-ink-2">{t('network.labels.type')}</dt>
			<dd class="flex gap-1">
				{#if s.network!.is_external}<span class="px-1.5 py-0.5 bg-orange-900/30 text-orange-300 rounded text-xs">{t('network.type.external')}</span>{/if}
				{#if s.network!.is_shared}<span class="px-1.5 py-0.5 bg-surface-selected/30 text-warm-text rounded text-xs">{t('network.type.shared')}</span>{/if}
				{#if !s.network!.is_external && !s.network!.is_shared}<span class="text-ink-2">{t('network.type.internal')}</span>{/if}
			</dd>
		</div>
	</dl>
</div>
