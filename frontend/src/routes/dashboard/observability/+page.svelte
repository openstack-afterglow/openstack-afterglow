<script lang="ts">
	import { auth } from '$lib/stores/auth';
	import GrafanaEmbed from '$lib/components/monitoring/GrafanaEmbed.svelte';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import PageShell from '$lib/components/ui/PageShell.svelte';
</script>

<PageShell class="max-w-7xl app-workspace-height flex flex-col">
	<PageHeader breadcrumb="DASHBOARD / OBSERVABILITY" title="VM 메트릭" />

	{#if !$auth.projectId}
		<div class="mt-4 text-sm text-ink-3">
			프로젝트를 선택하면 VM 메트릭이 표시됩니다.
		</div>
	{:else}
		<div class="mt-2 min-h-0 flex-1">
			<GrafanaEmbed
				dashboardKey="node"
				vars={{ project_id: $auth.projectId }}
				range="now-3h"
				height={600}
				desktopHeight={1400}
				title="Node Exporter"
			/>
		</div>
	{/if}
</PageShell>
