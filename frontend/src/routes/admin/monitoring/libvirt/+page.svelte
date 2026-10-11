<script lang="ts">
	import PageShell from '$lib/components/ui/PageShell.svelte';
	import { t } from '$lib/i18n/ns/admin-ops';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import GrafanaEmbed from '$lib/components/monitoring/GrafanaEmbed.svelte';
</script>

<PageShell class="app-workspace-height min-h-0 overflow-hidden flex flex-col">
	<PageHeader breadcrumb={t('monitoring.libvirt.breadcrumb')} title={t('monitoring.libvirt.title')} />
	<p class="text-xs text-ink-2 mb-2 flex-shrink-0">
		{t('monitoring.libvirt.description')}
	</p>
	<div class="flex-1 min-h-0">
		<GrafanaEmbed dashboardKey="libvirt" fill />
	</div>
</PageShell>
