<script lang="ts">
	import { t } from '$lib/i18n/ns/network-resources';
	import type { NetworkDetail } from '$lib/types/networks';

	let { network }: { network: NetworkDetail } = $props();
</script>

<div class="bg-surface-base border border-line rounded-lg p-6 mb-4">
	<h2 class="text-sm font-semibold text-ink-2 uppercase tracking-wide mb-3">{t('network.info.title')}</h2>
	<dl class="grid grid-cols-2 gap-x-8 gap-y-2">
		<div>
			<dt class="text-xs text-ink-2 mb-0.5">{t('network.labels.id')}</dt>
			<dd class="text-sm text-ink-2 font-mono">{network.id}</dd>
		</div>
		<div>
			<dt class="text-xs text-ink-2 mb-0.5">{t('network.info.subnetCount')}</dt>
			<dd class="text-sm text-ink-2">{network.subnets.length}</dd>
		</div>
	</dl>
</div>
