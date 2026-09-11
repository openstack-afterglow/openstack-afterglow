<script lang="ts">
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import GrafanaEmbed from '$lib/components/monitoring/GrafanaEmbed.svelte';
</script>

<div class="app-workspace-height overflow-hidden flex flex-col p-4 md:p-6">
	<PageHeader breadcrumb="MONITORING / LIBVIRT" title="Libvirt 메트릭" />
	<p class="text-xs text-ink-3 mb-2 flex-shrink-0">
		libvirt_exporter 를 통해 수집된 KVM/QEMU 가상 도메인 메트릭입니다.
	</p>
	<div class="flex-1 min-h-0">
		<GrafanaEmbed dashboardKey="libvirt" fill />
	</div>
</div>
