<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-storage';
	import { projectNames } from '$lib/stores/projectNames';
	import { useAdminVolumeDetailController } from '$lib/stores/adminVolumeDetailController.svelte';

	const s = useAdminVolumeDetailController();
</script>

<div class="bg-surface-base border border-line rounded-xl p-4">
	<h3 class="text-xs text-ink-2 uppercase tracking-wide mb-3">{t('volumeDetail.basicInfo')}</h3>
	<dl class="space-y-2 text-xs">
		<div class="flex justify-between">
			<dt class="text-ink-2">{t('volumeDetail.id')}</dt>
			<dd class="text-ink-2 font-mono text-xs">{s.volume?.id}</dd>
		</div>
		<div class="flex justify-between">
			<dt class="text-ink-2">{t('volumeDetail.volumeType')}</dt>
			<dd class="text-ink-2">{s.volume?.volume_type || '-'}</dd>
		</div>
		<div class="flex justify-between">
			<dt class="text-ink-2">{t('volumeDetail.project')}</dt>
			<dd class="text-ink-2">
				{s.volume?.project_id ? ($projectNames.get(s.volume.project_id) ?? s.volume.project_id.slice(0, 8)) : '-'}
			</dd>
		</div>
		<div class="flex justify-between">
			<dt class="text-ink-2">{t('volumeDetail.createdAt')}</dt>
			<dd class="text-ink-2">{s.volume?.created_at?.slice(0, 19) ?? '-'}</dd>
		</div>
		{#if s.volume?.description}
			<div class="flex justify-between">
				<dt class="text-ink-2">{t('volumeDetail.description')}</dt>
				<dd class="text-ink-2">{s.volume.description}</dd>
			</div>
		{/if}
	</dl>
</div>
