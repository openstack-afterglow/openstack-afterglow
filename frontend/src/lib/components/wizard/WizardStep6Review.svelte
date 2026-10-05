<script lang="ts">
	import { wizard } from '$lib/stores/wizard';
	import { useVmCreate } from '$lib/stores/vmCreateStore.svelte';
	import { normalizeGithubUsername, normalizeRequestedInstanceName } from '$lib/utils/instanceCreate';
	import { t } from '$lib/i18n/ns/vm-wizard';

	const s = useVmCreate();
	const reviewFlavor = $derived(s.flavors.find((f: any) => f.id === $wizard.flavorId));
	const reviewGpu = $derived.by(() => {
		if (!reviewFlavor) return '';
		const alias = reviewFlavor.extra_specs?.['pci_passthrough:alias'] ?? '';
		if (!alias) return '';
		const parts = alias.split(',').filter((e: string) => e.includes(':') && !e.toLowerCase().includes('audio'));
		return parts.map((e: string) => {
			const idx = e.lastIndexOf(':');
			return `${e.slice(0, idx).trim()} × ${parseInt(e.slice(idx + 1)) || 1}`;
		}).join(', ');
	});
	const reviewInstanceName = $derived(normalizeRequestedInstanceName($wizard.instanceName));
	const reviewSshAccess = $derived.by(() => {
		if ($wizard.sshAccessMode !== 'github') return $wizard.keyName ?? t('review.ssh.none');
		const profile = $wizard.githubProfile;
		const login = profile?.login ?? normalizeGithubUsername($wizard.githubUsername);
		if (!profile) return t('review.ssh.unverified', { login });
		return profile.name
			? t('review.ssh.verifiedWithName', { login, name: profile.name })
			: t('review.ssh.verified', { login });
	});
</script>

<h2 class="text-lg font-semibold text-ink-0 mb-4">{t('review.title')}</h2>

<div class="rounded-xl bg-surface-base border border-line overflow-hidden mb-4">
	<!-- 이름 -->
	<div class="grid grid-cols-[140px_1fr_auto] gap-4 items-center px-4 py-3.5 border-b border-line">
		<span class="text-xs text-ink-2 font-medium">{t('review.name.label')}</span>
		<span class="text-sm text-ink-0 font-semibold font-mono">{reviewInstanceName ?? t('review.name.automatic')}</span>
		<button onclick={() => s.goTo(5)} class="review-edit-btn">{t('review.edit')}</button>
	</div>
	<!-- 이미지 / 볼륨 -->
	<div class="grid grid-cols-[140px_1fr_auto] gap-4 items-center px-4 py-3.5 border-b border-line">
		<span class="text-xs text-ink-2 font-medium">
			{$wizard.bootSource === 'volume' ? t('review.bootVolume') : t('review.image')}
		</span>
		<span class="flex flex-col gap-0.5 min-w-0 text-sm text-ink-0 font-mono">
			{#if $wizard.bootSource === 'volume'}
				{$wizard.bootVolumeName ?? $wizard.bootVolumeId ?? '-'}
			{:else}
				<span class="font-semibold truncate">{$wizard.imageName ?? '-'}</span>
			{/if}
		</span>
		<button onclick={() => s.goTo(1)} class="review-edit-btn">{t('review.edit')}</button>
	</div>
	<!-- 플레이버 -->
	<div class="grid grid-cols-[140px_1fr_auto] gap-4 items-start px-4 py-3.5 border-b border-line">
		<span class="text-xs text-ink-2 font-medium mt-0.5">{t('review.flavor')}</span>
		<span class="flex flex-col gap-2 min-w-0">
			<span class="text-sm text-ink-0 font-mono font-semibold">{$wizard.flavorName ?? '-'}</span>
			{#if reviewFlavor}
				<div class="grid grid-cols-4 gap-2">
					<div class="flex flex-col gap-0.5 px-2.5 py-2 rounded-md bg-surface-sunken/70 border border-line-2">
						<span class="text-[9.5px] uppercase tracking-wider text-ink-2 font-mono font-bold">vCPU</span>
						<span class="font-mono text-sm font-semibold text-ink-0">{reviewFlavor.vcpus}</span>
					</div>
					<div class="flex flex-col gap-0.5 px-2.5 py-2 rounded-md bg-surface-sunken/70 border border-line-2">
						<span class="text-[9.5px] uppercase tracking-wider text-ink-2 font-mono font-bold">RAM</span>
						<span class="font-mono text-sm font-semibold text-ink-0">{reviewFlavor.ram >= 1024 ? Math.round(reviewFlavor.ram / 1024) + 'G' : reviewFlavor.ram + 'M'}</span>
					</div>
					<div class="flex flex-col gap-0.5 px-2.5 py-2 rounded-md bg-surface-sunken/70 border border-line-2">
						<span class="text-[9.5px] uppercase tracking-wider text-ink-2 font-mono font-bold">{t('review.disk')}</span>
						<span class="font-mono text-sm font-semibold text-ink-0">{reviewFlavor.disk}G</span>
					</div>
					<div class="flex flex-col gap-0.5 px-2.5 py-2 rounded-md bg-surface-sunken/70 border border-line-2">
						<span class="text-[9.5px] uppercase tracking-wider text-ink-2 font-mono font-bold">GPU</span>
						<span class="font-mono text-sm font-semibold {reviewGpu ? 'text-purple-400' : 'text-ink-2'}">{reviewGpu || '—'}</span>
					</div>
				</div>
			{/if}
		</span>
		<button onclick={() => s.goTo(2)} class="review-edit-btn mt-0.5">{t('review.edit')}</button>
	</div>
	<!-- 라이브러리 -->
	{#if $wizard.libraries.length > 0}
	<div class="grid grid-cols-[140px_1fr_auto] gap-4 items-center px-4 py-3.5 border-b border-line">
		<span class="text-xs text-ink-2 font-medium">{t('review.libraries')}</span>
		<span class="flex flex-wrap gap-1.5">
			{#each $wizard.libraries as lib}
				<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-surface-selected/30 border border-action-warm text-warm-text font-mono text-xs">{lib}</span>
			{/each}
		</span>
		<button onclick={() => s.goTo(3)} class="review-edit-btn">{t('review.edit')}</button>
	</div>
	{/if}
	<!-- SSH 접근 -->
	<div class="grid grid-cols-[140px_1fr_auto] gap-4 items-center px-4 py-3.5 border-b border-line">
		<span class="text-xs text-ink-2 font-medium">{t('review.ssh.label')}</span>
		<span class="text-sm text-ink-0 font-mono">{reviewSshAccess}</span>
		<button onclick={() => s.goTo(5)} class="review-edit-btn">{t('review.edit')}</button>
	</div>
	{#if s.visibleStepIds.includes(4)}
	<!-- 전략 -->
	<div class="grid grid-cols-[140px_1fr_auto] gap-4 items-center px-4 py-3.5 border-b border-line">
		<span class="text-xs text-ink-2 font-medium">{t('review.strategy.label')}</span>
		<span class="text-sm text-ink-0">
			{t('review.strategy.summary', { scheduling: $wizard.scheduling, strategy: $wizard.strategy || 'none' })}
		</span>
		<button onclick={() => s.goTo(4)} class="review-edit-btn">{t('review.edit')}</button>
	</div>
	{/if}
	<!-- 네트워크 -->
	<div class="grid grid-cols-[140px_1fr_auto] gap-4 items-center px-4 py-3.5 border-b border-line">
		<span class="text-xs text-ink-2 font-medium">{t('review.network.label')}</span>
		<span class="text-sm text-ink-0 font-mono">{$wizard.networkName ?? t('review.network.default')}</span>
		<button onclick={() => s.goTo(5)} class="review-edit-btn">{t('review.edit')}</button>
	</div>
	<!-- 루트 디스크 -->
	{#if $wizard.bootSource === 'image'}
	<div class="grid grid-cols-[140px_1fr_auto] gap-4 items-center px-4 py-3.5 {$wizard.dataMounts.length > 0 ? 'border-b border-line' : ''}">
		<span class="text-xs text-ink-2 font-medium">{t('review.rootDisk.label')}</span>
		<span class="text-sm text-ink-0 font-mono">
			{$wizard.bootVolumeSizeGb} GB
			<span class="text-ink-2 text-xs ml-1">{t('review.rootDisk.retention', { deleteWithVm: $wizard.deleteBootVolumeOnTermination })}</span>
		</span>
		<button onclick={() => s.goTo(5)} class="review-edit-btn">{t('review.edit')}</button>
	</div>
	{/if}
	<!-- 파일 스토리지 마운트 -->
	{#if $wizard.dataMounts.length > 0}
	<div class="grid grid-cols-[140px_1fr_auto] gap-4 items-start px-4 py-3.5">
		<span class="text-xs text-ink-2 font-medium mt-0.5">{t('review.mounts')}</span>
		<div class="flex flex-col gap-1.5">
			{#each $wizard.dataMounts as dm}
				<div class="flex items-center gap-2 text-xs font-mono">
					<span class="text-ink-2 truncate max-w-[140px]">{dm.fileStorageId ? (s.fileStorages.find(f => f.id === dm.fileStorageId)?.name ?? dm.fileStorageId.slice(0, 12)) : '—'}</span>
					<span class="text-ink-2">→</span>
					<span class="text-cyan-400">{dm.mountPoint || '—'}</span>
					{#if dm.readOnly}<span class="text-warm-text/80 text-xs">ro</span>{/if}
				</div>
			{/each}
		</div>
		<button onclick={() => s.goTo(5)} class="review-edit-btn mt-0.5">{t('review.edit')}</button>
	</div>
	{/if}
</div>

{#if $wizard.libraries.length > 0}
	<div class="p-3 rounded-lg bg-yellow-900/20 border border-yellow-700/40 text-yellow-300 text-xs flex items-start gap-2 mb-4">
		<svg class="w-4 h-4 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
			<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/>
		</svg>
		<span>{t('review.overlayNotice')}</span>
	</div>
{/if}

<!-- deploy banner -->
<div class="flex items-center gap-3.5 px-4 py-3.5 rounded-lg bg-blue-950/30 border border-action-warm/50 mb-4">
	<div class="w-9 h-9 rounded-full bg-action-warm text-action-on-warm flex items-center justify-center flex-shrink-0">
		<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
			<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7l5 5m0 0l-5 5m5-5H6"/>
		</svg>
	</div>
	<div class="flex-1">
		<b class="block text-sm text-ink-0 font-semibold mb-0.5">{t('review.ready')}</b>
		<small class="text-[11.5px] text-ink-2 leading-relaxed">
			{t('review.deployHelp')}
		</small>
	</div>
</div>

{#if s.deployError}
	<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm mb-4">
		{s.deployError}
	</div>
{/if}

<style>
  .review-edit-btn {
    font-size: 11.5px;
    color: var(--color-ink-2);
    padding: 2px 10px;
    border-radius: 6px;
    border: 1px solid var(--color-line-2);
    transition: all 0.15s;
    white-space: nowrap;
    flex-shrink: 0;
  }
  .review-edit-btn:hover {
    color: var(--color-accent);
    border-color: color-mix(in srgb, var(--color-accent) 70%, transparent);
    background: color-mix(in srgb, var(--color-accent) 12%, transparent);
  }
</style>
