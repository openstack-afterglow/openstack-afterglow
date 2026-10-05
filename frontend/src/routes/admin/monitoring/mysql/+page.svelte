<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-ops';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import GrafanaEmbed from '$lib/components/monitoring/GrafanaEmbed.svelte';
</script>

<div class="app-workspace-height overflow-hidden flex flex-col p-4 md:p-6">
	<PageHeader breadcrumb={t('monitoring.mysql.breadcrumb')} title={t('monitoring.mysql.title')} />
	<p class="text-xs text-ink-2 mb-2 flex-shrink-0">
		{t('monitoring.mysql.description')}
	</p>
	<div class="flex-1 min-h-0">
		<GrafanaEmbed dashboardKey="mysqld" fill />
	</div>
</div>
