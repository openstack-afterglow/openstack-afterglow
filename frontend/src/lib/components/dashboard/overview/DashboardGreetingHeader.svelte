<script lang="ts">
	import { t } from '$lib/i18n/ns/dashboard-home';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import RichText from '$lib/i18n/RichText.svelte';
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

	function formatSyncTime(timestamp: number | null): string {
		if (timestamp === null) return '--:--:--';
		return new Intl.DateTimeFormat(intlLocale(), {
			hour: '2-digit',
			minute: '2-digit',
			second: '2-digit',
			hour12: false,
		}).format(new Date(timestamp));
	}

	const syncLabel = $derived(
		syncStatus === 'waiting'
			? t('greeting.waiting')
			: t(syncStatus === 'partial' ? 'greeting.partial' : 'greeting.complete', { time: formatSyncTime(lastSuccessfulSyncAt) }),
	);
</script>

{#snippet userName(text: string)}<GradientText>{text}</GradientText>{/snippet}

<div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
	<div class="min-w-0">
		<div class="text-xs text-[var(--color-ink-3)] uppercase tracking-widest font-medium mb-1">{t('greeting.eyebrow')}</div>
		<h1 class="text-2xl font-bold text-[var(--color-ink-0)] mb-1 break-words"><RichText segments={t.rich('greeting.hello', { username })} tags={{ user: userName }} /></h1>
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
