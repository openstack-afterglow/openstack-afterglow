<script lang="ts">
	import { projectNames } from '$lib/stores/projectNames';
	import { useAdminVolumeDetailController } from '$lib/stores/adminVolumeDetailController.svelte';

	const s = useAdminVolumeDetailController();
</script>

<div class="bg-surface-base border border-line rounded-xl p-4">
	<h3 class="text-xs text-ink-3 uppercase tracking-wide mb-3">기본 정보</h3>
	<dl class="space-y-2 text-xs">
		<div class="flex justify-between">
			<dt class="text-ink-2">ID</dt>
			<dd class="text-ink-2 font-mono text-xs">{s.volume?.id}</dd>
		</div>
		<div class="flex justify-between">
			<dt class="text-ink-2">볼륨 유형</dt>
			<dd class="text-ink-2">{s.volume?.volume_type || '-'}</dd>
		</div>
		<div class="flex justify-between">
			<dt class="text-ink-2">프로젝트</dt>
			<dd class="text-ink-2">
				{s.volume?.project_id ? ($projectNames.get(s.volume.project_id) ?? s.volume.project_id.slice(0, 8)) : '-'}
			</dd>
		</div>
		<div class="flex justify-between">
			<dt class="text-ink-2">생성일</dt>
			<dd class="text-ink-2">{s.volume?.created_at?.slice(0, 19) ?? '-'}</dd>
		</div>
		{#if s.volume?.description}
			<div class="flex justify-between">
				<dt class="text-ink-2">설명</dt>
				<dd class="text-ink-2">{s.volume.description}</dd>
			</div>
		{/if}
	</dl>
</div>
