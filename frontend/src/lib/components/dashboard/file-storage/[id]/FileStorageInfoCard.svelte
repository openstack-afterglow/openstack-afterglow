<script lang="ts">
	import { t } from '$lib/i18n/ns/file-storage';
	import type { FileStorage } from '$lib/types/fileStorage';
	import ProgressTrack from '$lib/components/ui/ProgressTrack.svelte';

	let { fileStorage }: { fileStorage: FileStorage } = $props();
	const progressing = $derived(fileStorage.status === 'creating' || fileStorage.status === 'extending');
	const progressPct = $derived.by(() => {
		const match = fileStorage.progress?.match(/^(\d+(?:\.\d+)?)%$/);
		return match ? Number(match[1]) : null;
	});
</script>

<div class="bg-surface-base border border-line rounded-lg p-6 mb-4">
	<h2 class="text-sm font-semibold text-ink-2 uppercase tracking-wide mb-4">{t('infoCard.title')}</h2>
	<dl class="grid grid-cols-2 gap-x-8 gap-y-3">
		<div>
			<dt class="text-xs text-ink-2 mb-0.5">ID</dt>
			<dd class="text-sm text-ink-2 font-mono">{fileStorage.id}</dd>
		</div>
		<div>
			<dt class="text-xs text-ink-2 mb-0.5">{t('infoCard.size')}</dt>
			<dd class="text-sm text-ink-2">{fileStorage.size} GB</dd>
		</div>
		{#if progressing || fileStorage.progress}
			<div class="col-span-2">
				<dt class="text-xs text-ink-2 mb-0.5">{t('info.progress')}</dt>
				<dd class="space-y-2">
					<span class="text-sm text-ink-2">{fileStorage.progress || (fileStorage.status === 'extending' ? t('storageCard.extending') : t('actions.creating'))}</span>
					{#if progressing || (progressPct !== null && progressPct < 100)}
						<ProgressTrack value={progressPct} label={`${fileStorage.name || fileStorage.id} · ${t('info.progress')}`} valueText={fileStorage.progress || (fileStorage.status === 'extending' ? t('storageCard.extending') : t('actions.creating'))} active={progressing} />
					{/if}
				</dd>
			</div>
		{/if}
		{#if fileStorage.library_name}
			<div>
				<dt class="text-xs text-ink-2 mb-0.5">{t('infoCard.library')}</dt>
				<dd class="text-sm text-ink-2">{fileStorage.library_name}</dd>
			</div>
			<div>
				<dt class="text-xs text-ink-2 mb-0.5">{t('infoCard.version')}</dt>
				<dd class="text-sm text-ink-2">{fileStorage.library_version ?? '-'}</dd>
			</div>
			{#if fileStorage.built_at}
				<div class="col-span-2">
					<dt class="text-xs text-ink-2 mb-0.5">{t('infoCard.builtAt')}</dt>
					<dd class="text-sm text-ink-2">{fileStorage.built_at}</dd>
				</div>
			{/if}
		{/if}
	</dl>
</div>
