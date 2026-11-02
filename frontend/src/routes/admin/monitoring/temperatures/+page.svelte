<script lang="ts">
	import PageShell from '$lib/components/ui/PageShell.svelte';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import GrafanaEmbed from '$lib/components/monitoring/GrafanaEmbed.svelte';
	import { t } from '$lib/i18n/ns/admin-ops';
</script>

<PageShell class="app-workspace-height min-h-0 overflow-hidden flex flex-col">
	<PageHeader breadcrumb={t('monitoring.temperatures.breadcrumb')} title={t('monitoring.temperatures.title')} />
	<p class="text-xs text-ink-2 mb-2 flex-shrink-0">
		{t('monitoring.temperatures.description')}
	</p>
	<div class="flex-1 min-h-0">
		<GrafanaEmbed
			dashboardKey="node-temperatures"
			range="now-6h"
			timezone="browser"
			refresh="auto"
			vars={{ job: '$__all', instance: '$__all', chip: '$__all', sensor: '$__all' }}
			fill
		/>
	</div>
</PageShell>
