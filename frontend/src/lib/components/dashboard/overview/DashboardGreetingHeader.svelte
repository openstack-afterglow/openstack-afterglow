<script lang="ts">
	import type { AutoRefreshController } from '$lib/utils/autoRefresh.svelte';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import GradientText from '$lib/components/ui/GradientText.svelte';

	let {
		username,
		projectName,
		ar,
		refreshing,
		onForceRefresh,
		syncStatus,
		lastSuccessfulSyncAt,
	}: {
		username: string;
		projectName: string;
		ar: AutoRefreshController;
		refreshing: boolean;
		onForceRefresh: () => void;
		syncStatus: 'waiting' | 'partial' | 'complete';
		lastSuccessfulSyncAt: number | null;
	} = $props();

	function formatKoreanTime(timestamp: number | null): string {
		if (timestamp === null) return '--:--:--';
		return new Intl.DateTimeFormat('ko-KR', {
			hour: '2-digit',
			minute: '2-digit',
			second: '2-digit',
			hour12: false,
		}).format(new Date(timestamp));
	}

	const syncLabel = $derived(
		syncStatus === 'waiting'
			? '동기화 대기 중'
			: `${syncStatus === 'partial' ? '일부 동기화' : '최근 동기화'} ${formatKoreanTime(lastSuccessfulSyncAt)}`,
	);
</script>

<div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
	<div class="min-w-0">
		<div class="text-xs text-[var(--color-ink-3)] uppercase tracking-widest font-medium mb-1">OVERVIEW · 대시보드</div>
		<h1 class="text-2xl font-bold text-[var(--color-ink-0)] mb-1 break-words">안녕하세요, <GradientText>{username}</GradientText>님</h1>
		<div class="text-[var(--color-ink-2)] text-[13px] break-words">
			{projectName} · {syncLabel}
		</div>
	</div>
	<AutoRefreshControl
		bind:active={ar.active}
		bind:intervalSeconds={ar.intervalSeconds}
		intervalOptions={ar.intervalOptions}
		{refreshing}
		onManualRefresh={onForceRefresh}
	/>
</div>
