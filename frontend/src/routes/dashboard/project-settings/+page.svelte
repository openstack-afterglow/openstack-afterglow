<script lang="ts">
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import ProjectsSection from '$lib/components/account/ProjectsSection.svelte';
	import ProjectSettingsSection from '$lib/components/account/ProjectSettingsSection.svelte';
</script>

<div class="p-4 md:p-6 max-w-5xl">
	<div class="flex items-center gap-3 mb-4">
		<a
			href="/dashboard"
			class="inline-flex items-center gap-1.5 text-xs text-ink-2 hover:text-ink-0 transition-colors px-2.5 py-1.5 rounded-md hover:bg-surface-sunken"
		>
			<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7"></path></svg>
			대시보드로 돌아가기
		</a>
	</div>

	<PageHeader breadcrumb="" title="프로젝트 설정" />
	<div class="grid grid-cols-1 gap-4">
		<ProjectsSection />
		<ProjectSettingsSection />
	</div>
</div>
