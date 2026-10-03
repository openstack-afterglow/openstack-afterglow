<script lang="ts">
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import GrafanaEmbed from '$lib/components/monitoring/GrafanaEmbed.svelte';
</script>

<div class="app-workspace-height overflow-hidden flex flex-col p-4 md:p-6">
	<PageHeader breadcrumb="MONITORING / PROXYSQL" title="ProxySQL — MariaDB 접속 경로" />
	<p class="text-xs text-ink-2 mb-2 flex-shrink-0">
		ProxySQL의 클라이언트 연결, 쓰기 노드와 MariaDB 백엔드 상태를 확인합니다.
	</p>
	<div class="flex-1 min-h-0">
		<GrafanaEmbed dashboardKey="proxysql" fill />
	</div>
</div>
