<script lang="ts">
	import { onMount } from 'svelte';
	import { uploadQueue, type UploadJob } from '$lib/stores/uploadQueue';

	let jobs = $state<UploadJob[]>([]);
	let collapsed = $state(false);

	// 자동 dismiss 타이머 (job id → timer id)
	const timers = new Map<string, ReturnType<typeof setTimeout>>();

	onMount(() => {
		const unsub = uploadQueue.subscribe((list) => {
			jobs = list;

			// 새로 완료된 job 에 5초 dismiss 타이머
			for (const j of list) {
				if ((j.status === 'success' || j.status === 'canceled') && !timers.has(j.id)) {
					const t = setTimeout(() => {
						uploadQueue.remove(j.id);
						timers.delete(j.id);
					}, 5000);
					timers.set(j.id, t);
				}
			}

			// 더 이상 목록에 없는 job 의 타이머 정리
			for (const [id, t] of timers) {
				if (!list.find((j) => j.id === id)) {
					clearTimeout(t);
					timers.delete(id);
				}
			}
		});
		return unsub;
	});

	const visible = $derived(jobs.length > 0);
	const activeCount = $derived(jobs.filter((j) => j.status === 'uploading').length);
	const totalLoaded = $derived(jobs.reduce((s, j) => s + j.loaded, 0));
	const totalBytes = $derived(jobs.reduce((s, j) => s + j.total, 0));

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
		if (!isFinite(sec) || sec <= 0) return '--';
		const s = Math.ceil(sec);
		if (s < 60) return `${s}초`;
		const m = Math.floor(s / 60);
		const r = s % 60;
		return r > 0 ? `${m}분 ${r}초` : `${m}분`;
	}

	function statusLabel(j: UploadJob): string {
		if (j.status === 'success') return '완료';
		if (j.status === 'error') return '오류';
		if (j.status === 'canceled') return '취소됨';
		const pct = j.total > 0 ? Math.round((j.loaded / j.total) * 100) : 0;
		return `${pct}% · ${formatBytes(speed(j))}/s · ${formatTime(remaining(j))} 남음`;
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
	<div class="fixed bottom-4 right-4 z-40 w-80 shadow-[var(--shadow-restraint)] rounded-xl overflow-hidden border border-line-2 bg-surface-base">
		<!-- 헤더 -->
		<button
			onclick={() => (collapsed = !collapsed)}
			class="w-full flex items-center justify-between px-4 py-3 bg-surface-sunken hover:bg-gray-750 transition-colors"
		>
			<span class="text-sm font-medium text-ink-0">
				{#if activeCount > 0}
					{activeCount}개 업로드 중 · {formatBytes(totalLoaded)} / {formatBytes(totalBytes)}
				{:else}
					업로드 완료
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
		{#if !collapsed}
			<div class="max-h-64 overflow-y-auto divide-y divide-line">
				{#each jobs as j (j.id)}
					<div class="px-4 py-3">
						<div class="flex items-start justify-between gap-2 mb-1.5">
							<div class="flex items-center gap-1.5 min-w-0 flex-1">
								{#if j.kind === 'image'}
									<span class="shrink-0 text-[10px] px-1.5 py-0.5 rounded bg-purple-900/40 border border-purple-800 text-purple-300">이미지</span>
								{/if}
								<span class="text-xs text-ink-1 truncate" title={j.name}>{j.name}</span>
							</div>
							{#if j.status === 'uploading'}
								<button
									onclick={() => uploadQueue.cancel(j.id)}
									class="shrink-0 text-ink-3 hover:text-red-400 transition-colors text-xs"
									title="취소"
								>✕</button>
							{:else}
								<button
									onclick={() => uploadQueue.remove(j.id)}
									class="shrink-0 text-ink-3 hover:text-ink-2 transition-colors text-xs"
									title="닫기"
								>✕</button>
							{/if}
						</div>

						{#if j.status === 'uploading'}
							<div class="bg-surface-sunken rounded-full h-1.5 mb-1 overflow-hidden">
								<div
									class="bg-indigo-500 h-1.5 rounded-full transition-all duration-300"
									style="width: {j.total > 0 ? Math.round((j.loaded / j.total) * 100) : 0}%"
								></div>
							</div>
						{:else if j.status === 'error'}
							<div class="bg-surface-sunken rounded-full h-1.5 mb-1 overflow-hidden">
								<div class="bg-red-500 h-1.5 rounded-full w-full"></div>
							</div>
						{:else}
							<div class="bg-surface-sunken rounded-full h-1.5 mb-1 overflow-hidden">
								<div class="bg-green-500 h-1.5 rounded-full w-full transition-all"></div>
							</div>
						{/if}

						<div class="text-[10px] {j.status === 'error' ? 'text-red-400' : j.status === 'success' ? 'text-green-400' : 'text-ink-3'}">
							{#if j.status === 'error'}
								{j.error ?? '업로드 실패'}
							{:else}
								{statusLabel(j)}
							{/if}
						</div>
					</div>
				{/each}
			</div>
		{/if}
	</div>
{/if}
