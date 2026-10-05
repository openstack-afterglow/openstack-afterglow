<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-ops';
	import QuotaDonut from '$lib/components/QuotaDonut.svelte';
	import type { Overview } from '$lib/types/adminOverview';

	let { overview }: { overview: Overview } = $props();
</script>

<div class="bg-surface-base border border-line rounded-lg p-5">
	<div class="text-ink-0 text-[15px] font-semibold mb-5">{t('overview.resources.title')}</div>
	<div class="grid grid-cols-1 sm:grid-cols-3 gap-8">
		<div class="flex flex-col items-center gap-3">
			<QuotaDonut label={t('overview.resources.cpuCores')} used={overview.vcpus.used} limit={overview.vcpus.allowed} size="lg" />
		</div>
		<div class="flex flex-col items-center gap-3">
			<QuotaDonut label={t('overview.resources.memory')} used={overview.ram_gb.used} limit={overview.ram_gb.total} unit="GB" size="lg" />
		</div>
		<div class="flex flex-col items-center gap-3">
			<QuotaDonut label={t('overview.resources.blockStorage')} used={overview.disk_gb.used} limit={overview.disk_gb.total} unit="GB" size="lg" />
		</div>
	</div>
</div>
