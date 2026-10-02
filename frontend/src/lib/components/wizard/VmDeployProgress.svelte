<script lang="ts">
	import { t } from '$lib/i18n/ns/vm-wizard';
	import { useVmCreate } from '$lib/stores/vmCreateStore.svelte';
	import ProgressBar from '$lib/components/ProgressBar.svelte';

	const s = useVmCreate();
</script>

<div class="mb-6">
	<h1 class="text-xl font-bold text-ink-0">{t('progress.title')}</h1>
	<p class="text-sm text-ink-2 mt-1">{t('progress.subtitle')}</p>
</div>

<div class="bg-surface-base rounded-xl border border-line-2 p-6 mb-6">
	<h2 class="text-lg font-semibold text-ink-0 mb-4">{t('progress.heading')}</h2>
	<ProgressBar
		steps={s.progressSteps}
		currentStep={s.currentStep}
		progress={s.progress}
		error={s.deployError}
	/>
	<div class="flex items-center justify-between mt-4">
		<p class="text-ink-2 text-sm">{s.progressMessage}</p>
		{#if s.elapsedSeconds !== null}
			<p class="text-ink-2 text-xs font-mono">{t('progress.elapsed', { seconds: s.elapsedSeconds.toFixed(0) })}</p>
		{/if}
	</div>
</div>
