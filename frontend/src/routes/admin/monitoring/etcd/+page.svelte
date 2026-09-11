<script lang="ts">
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import GrafanaEmbed from '$lib/components/monitoring/GrafanaEmbed.svelte';
</script>

<div class="app-workspace-height overflow-hidden flex flex-col p-4 md:p-6">
	<PageHeader breadcrumb="MONITORING / ETCD" title="etcd 메트릭" />
	<p class="text-xs text-ink-3 mb-2 flex-shrink-0">
		etcd 내장 Prometheus 엔드포인트를 통해 수집된 메트릭입니다.
	</p>
	<div class="flex-1 min-h-0">
		<GrafanaEmbed dashboardKey="etcd" fill />
	</div>
</div>
