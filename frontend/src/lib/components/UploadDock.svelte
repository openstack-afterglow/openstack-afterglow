<script lang="ts">
	import { onMount } from 'svelte';
	import { uploadQueue, type UploadJob } from '$lib/stores/uploadQueue';
	import { ActivityIndicator, AnimatedNumber, Pill, ProgressTrack } from '$lib/components/ui';
	import { t } from '$lib/i18n/ns/object-storage';
	import { enter, reflow } from '$lib/utils/motion';

	let jobs = $state<UploadJob[]>([]);
	let collapsed = $state(false);

	onMount(() => {
		// 완료·취소 행은 각 행의 닫기 버튼으로만 사라진다. 타이머로 지우면 사용자가 결과를
		// 읽기 전에 사라질 수 있다 (WCAG 2.2.1).
		return uploadQueue.subscribe((list) => {
			jobs = list;
		});
	});

	const visible = $derived(jobs.length > 0);
	const activeCount = $derived(jobs.filter((j) => j.status === 'uploading').length);
	const totalLoaded = $derived(jobs.reduce((s, j) => s + j.loaded, 0));
	const totalBytes = $derived(jobs.reduce((s, j) => s + j.total, 0));
	const aggregatePercent = $derived(totalBytes > 0 ? Math.round(totalLoaded / totalBytes * 100) : 0);

	function formatBytes(n: number): string {
		if (n >= 1073741824) return `${(n / 1073741824).toFixed(1)} GB`;
		if (n >= 1048576) return `${(n / 1048576).toFixed(1)} MB`;
		if (n >= 1024) return `${(n / 1024).toFixed(0)} KB`;
		return `${n} B`;
	}

	function speed(j: UploadJob): number {
		const elapsed = (Date.now() - j.startTime) / 1000;
		return elapsed > 0 ? j.loaded / elapsed : 0;
	}

	function remaining(j: UploadJob): number {
		const s = speed(j);
		return s > 0 && j.total > j.loaded ? (j.total - j.loaded) / s : 0;
	}

	function formatTime(sec: number): string {
		if (!isFinite(sec) || sec <= 0) return t('uploadDock.unknownTime');
		const s = Math.ceil(sec);
		if (s < 60) return t('uploadDock.seconds', { seconds: s });
		const m = Math.floor(s / 60);
		const r = s % 60;
		return r > 0 ? t('uploadDock.minutesSeconds', { minutes: m, seconds: r }) : t('uploadDock.minutes', { minutes: m });
	}

	function statusLabel(j: UploadJob): string {
		if (j.status === 'success') return t('uploadDock.status.success');
		if (j.status === 'error') return t('uploadDock.status.error');
		if (j.status === 'canceled') return t('uploadDock.status.canceled');
		if (j.loaded === 0) return t('uploadDock.preparing');
		const pct = j.total > 0 ? Math.round((j.loaded / j.total) * 100) : 0;
		return t('uploadDock.progress', { percent: pct, speed: formatBytes(speed(j)), time: formatTime(remaining(j)) });
	}

	onMount(() => {
		const handler = (e: BeforeUnloadEvent) => {
			if (jobs.some((j) => j.status === 'uploading')) {
				e.preventDefault();
			}
		};
		window.addEventListener('beforeunload', handler);
		return () => window.removeEventListener('beforeunload', handler);
	});
</script>

{#if visible}
	<div class="motion-enter fixed bottom-4 right-4 z-40 w-80 max-w-[calc(100vw-2rem)] shadow-[var(--shadow-overlay-compact)] rounded-xl overflow-hidden border border-line-2 bg-surface-base">
		<!-- 헤더 -->
		<button
			onclick={() => (collapsed = !collapsed)}
			aria-expanded={!collapsed}
			aria-controls="upload-dock-jobs"
			class="w-full flex items-center justify-between gap-2 px-4 py-3 bg-surface-sunken hover:bg-surface-selected transition-colors"
		>
			<span class="text-sm font-medium text-ink-0">
				{#if activeCount > 0}
					<ActivityIndicator variant="upload" size="xs" label={t('uploadDock.uploadingCount', { count: activeCount })} />
					<span class="block mt-1 text-xs text-ink-2">{formatBytes(totalLoaded)} / {formatBytes(totalBytes)} · <AnimatedNumber value={aggregatePercent} format={(n) => `${Math.round(n)}%`} /></span>
				{:else}
					{t('uploadDock.results')}
				{/if}
			</span>
			<svg
				class="w-4 h-4 text-ink-2 transition-transform {collapsed ? 'rotate-180' : ''}"
				viewBox="0 0 20 20" fill="currentColor"
			>
				<path fill-rule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clip-rule="evenodd" />
			</svg>
		</button>

		<!-- 작업 목록 -->
			<div id="upload-dock-jobs" hidden={collapsed} class="max-h-64 overflow-y-auto divide-y divide-line">
				{#each jobs as j (j.id)}
					<div class="px-4 py-3" in:enter animate:reflow aria-busy={j.status === 'uploading'}>
						<!-- 44px close targets overlap the row padding (negative margins) so they do not stretch the row. -->
						<div class="flex items-center justify-between gap-2 mb-1.5">
							<div class="flex items-center gap-1.5 min-w-0 flex-1">
								{#if j.kind === 'image'}
									<span class="shrink-0 text-xs px-1.5 py-0.5 rounded bg-surface-selected border border-line text-accent">{t('uploadDock.image')}</span>
								{/if}
								<span class="text-xs text-ink-1 truncate" title={j.name}>{j.name}</span>
							</div>
							{#if j.status === 'uploading'}
								<button
									onclick={() => uploadQueue.cancel(j.id)}
									class="shrink-0 -my-3.5 -mr-3 min-h-11 min-w-11 text-ink-2 hover:text-state-danger-text transition-colors text-xs"
									title={t('uploadDock.cancel')}
									aria-label={t('uploadDock.cancelNamed', { name: j.name })}
								>{t('uploadDock.closeSymbol')}</button>
							{:else}
								<button
									onclick={() => uploadQueue.remove(j.id)}
									class="shrink-0 -my-3.5 -mr-3 min-h-11 min-w-11 text-ink-2 hover:text-ink-0 transition-colors text-xs"
									title={t('uploadDock.close')}
									aria-label={t('uploadDock.closeNamed', { name: j.name })}
								>{t('uploadDock.closeSymbol')}</button>
							{/if}
						</div>

						<ProgressTrack
							value={j.status === 'uploading' && j.loaded === 0 ? null : j.status === 'success' ? 100 : j.total > 0 ? j.loaded / j.total * 100 : 0}
							active={j.status === 'uploading'}
							tone={j.status === 'error' ? 'danger' : j.status === 'success' ? 'success' : j.status === 'canceled' ? 'neutral' : 'accent'}
							label={t('uploadDock.progressLabel', { name: j.name })}
							valueText={statusLabel(j)}
							size="xs"
							class="mb-1"
						/>

						<div class="flex items-center gap-2">
							{#if j.status === 'success'}
								<svg class="motion-pop h-4 w-4 shrink-0 text-state-success-text" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m5 12 4 4L19 6" /></svg>
							{/if}
							<div class="text-xs {j.status === 'error' ? 'text-state-danger-text' : j.status === 'success' ? 'text-state-success-text' : 'text-ink-2'}">
								{#if j.status === 'error'}
									{j.error ?? t('uploadDock.failed')}
								{:else}
									{statusLabel(j)}
								{/if}
							</div>
							{#if j.status === 'success' && j.sha256}
								<Pill tone="success" size="xs" dot class="shrink-0">{t('uploadDock.verified')}</Pill>
							{/if}
						</div>
					</div>
				{/each}
			</div>
	</div>
{/if}
