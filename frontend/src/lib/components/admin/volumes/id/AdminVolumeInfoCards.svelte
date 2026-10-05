<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-storage';
	import type { AdminVolumeDetail } from '$lib/types/volume';
	import { projectNames } from '$lib/stores/projectNames';
	import { formatNumber } from '$lib/utils/format';

	let { volume }: { volume: AdminVolumeDetail } = $props();
</script>

<div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
	<!-- 기본 정보 -->
	<div class="bg-surface-base border border-line rounded-xl p-4">
		<h3 class="text-xs text-ink-2 uppercase tracking-wide mb-3">{t('volumeDetail.basicInfo')}</h3>
		<dl class="space-y-2 text-sm">
			<div class="flex justify-between">
				<dt class="text-ink-2">{t('volumeDetail.id')}</dt>
				<dd class="font-mono text-xs text-ink-2">{volume.id}</dd>
			</div>
			<div class="flex justify-between">
				<dt class="text-ink-2">{t('volumeDetail.type')}</dt>
				<dd class="text-ink-2">{volume.volume_type || '-'}</dd>
			</div>
			<div class="flex justify-between">
				<dt class="text-ink-2">{t('volumeDetail.project')}</dt>
				<dd class="text-ink-2">{volume.project_id ? ($projectNames.get(volume.project_id) ?? volume.project_id.slice(0, 12)) : '-'}</dd>
			</div>
			<div class="flex justify-between">
				<dt class="text-ink-2">{t('volumeDetail.createdAt')}</dt>
				<dd class="text-ink-2">{volume.created_at ? volume.created_at.slice(0, 10) : '-'}</dd>
			</div>
			{#if volume.description}
				<div class="flex justify-between">
					<dt class="text-ink-2">{t('volumeDetail.description')}</dt>
					<dd class="text-ink-2 text-right max-w-48 break-words">{volume.description}</dd>
				</div>
			{/if}
		</dl>
	</div>

	<!-- 속성 -->
	<div class="bg-surface-base border border-line rounded-xl p-4">
		<h3 class="text-xs text-ink-2 uppercase tracking-wide mb-3">{t('volumeDetail.properties')}</h3>
		<dl class="space-y-2 text-sm">
			<div class="flex justify-between">
				<dt class="text-ink-2">{t('volumeDetail.bootableCard')}</dt>
				<dd class="text-ink-2">{volume.bootable === true ? t('volumeDetail.yes') : volume.bootable === false ? t('volumeDetail.no') : '-'}</dd>
			</div>
			<div class="flex justify-between">
				<dt class="text-ink-2">{t('volumeDetail.encrypted')}</dt>
				<dd class="text-ink-2">{volume.encrypted === true ? t('volumeDetail.yes') : volume.encrypted === false ? t('volumeDetail.no') : '-'}</dd>
			</div>
			<div class="flex justify-between">
				<dt class="text-ink-2">{t('volumeDetail.multiattachCard')}</dt>
				<dd class="text-ink-2">{volume.multiattach === true ? t('volumeDetail.yes') : volume.multiattach === false ? t('volumeDetail.no') : '-'}</dd>
			</div>
		</dl>
	</div>
</div>
