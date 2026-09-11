<script lang="ts">
	import { useAdminVolumeDetailController } from '$lib/stores/adminVolumeDetailController.svelte';

	const s = useAdminVolumeDetailController();
</script>

<div class="bg-surface-base border border-line rounded-xl p-4">
	<h3 class="text-xs text-ink-3 uppercase tracking-wide mb-3">속성</h3>
	<dl class="space-y-2 text-xs">
		<div class="flex justify-between">
			<dt class="text-ink-2">부트 가능</dt>
			<dd class="{s.volume?.bootable ? 'text-green-400' : 'text-ink-3'}">{s.volume?.bootable ? '예' : '아니오'}</dd>
		</div>
		<div class="flex justify-between">
			<dt class="text-ink-2">암호화</dt>
			<dd class="{s.volume?.encrypted ? 'text-yellow-400' : 'text-ink-3'}">{s.volume?.encrypted ? '예' : '아니오'}</dd>
		</div>
		<div class="flex justify-between">
			<dt class="text-ink-2">다중 연결</dt>
			<dd class="{s.volume?.multiattach ? 'text-action-warm' : 'text-ink-3'}">{s.volume?.multiattach ? '예' : '아니오'}</dd>
		</div>
	</dl>
</div>
