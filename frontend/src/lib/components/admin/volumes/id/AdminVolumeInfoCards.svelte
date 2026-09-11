<script lang="ts">
	import type { AdminVolumeDetail } from '$lib/types/volume';
	import { projectNames } from '$lib/stores/projectNames';
	import { formatNumber } from '$lib/utils/format';

	let { volume }: { volume: AdminVolumeDetail } = $props();
</script>

<div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
	<!-- 기본 정보 -->
	<div class="bg-surface-base border border-line rounded-xl p-4">
		<h3 class="text-xs text-ink-3 uppercase tracking-wide mb-3">기본 정보</h3>
		<dl class="space-y-2 text-sm">
			<div class="flex justify-between">
				<dt class="text-ink-2">ID</dt>
				<dd class="font-mono text-xs text-ink-2">{volume.id}</dd>
			</div>
			<div class="flex justify-between">
				<dt class="text-ink-2">볼륨 타입</dt>
				<dd class="text-ink-2">{volume.volume_type || '-'}</dd>
			</div>
			<div class="flex justify-between">
				<dt class="text-ink-2">프로젝트</dt>
				<dd class="text-ink-2">{volume.project_id ? ($projectNames.get(volume.project_id) ?? volume.project_id.slice(0, 12)) : '-'}</dd>
			</div>
			<div class="flex justify-between">
				<dt class="text-ink-2">생성일</dt>
				<dd class="text-ink-2">{volume.created_at ? volume.created_at.slice(0, 10) : '-'}</dd>
			</div>
			{#if volume.description}
				<div class="flex justify-between">
					<dt class="text-ink-2">설명</dt>
					<dd class="text-ink-2 text-right max-w-48 break-words">{volume.description}</dd>
				</div>
			{/if}
		</dl>
	</div>

	<!-- 속성 -->
	<div class="bg-surface-base border border-line rounded-xl p-4">
		<h3 class="text-xs text-ink-3 uppercase tracking-wide mb-3">속성</h3>
		<dl class="space-y-2 text-sm">
			<div class="flex justify-between">
				<dt class="text-ink-2">부팅 가능</dt>
				<dd class="text-ink-2">{volume.bootable === true ? '예' : volume.bootable === false ? '아니오' : '-'}</dd>
			</div>
			<div class="flex justify-between">
				<dt class="text-ink-2">암호화</dt>
				<dd class="text-ink-2">{volume.encrypted === true ? '예' : volume.encrypted === false ? '아니오' : '-'}</dd>
			</div>
			<div class="flex justify-between">
				<dt class="text-ink-2">멀티 연결</dt>
				<dd class="text-ink-2">{volume.multiattach === true ? '예' : volume.multiattach === false ? '아니오' : '-'}</dd>
			</div>
		</dl>
	</div>
</div>
