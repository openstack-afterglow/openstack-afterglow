<script lang="ts">
	import { useVmCreate } from '$lib/stores/vmCreateStore.svelte';
	import ProgressBar from '$lib/components/ProgressBar.svelte';

	const s = useVmCreate();
</script>

<div class="mb-6">
	<h1 class="text-xl font-bold text-ink-0">VM 생성</h1>
	<p class="text-sm text-ink-3 mt-1">배포 진행 중</p>
</div>

<div class="bg-surface-base rounded-xl border border-line-2 p-6 mb-6">
	<h2 class="text-lg font-semibold text-ink-0 mb-4">VM 배포 진행 중</h2>
	<ProgressBar
		steps={s.progressSteps}
		currentStep={s.currentStep}
		progress={s.progress}
		error={s.deployError}
	/>
	<div class="flex items-center justify-between mt-4">
		<p class="text-ink-2 text-sm">{s.progressMessage}</p>
		{#if s.elapsedSeconds !== null}
			<p class="text-ink-3 text-xs font-mono">{s.elapsedSeconds.toFixed(0)}s 경과</p>
		{/if}
	</div>
</div>
