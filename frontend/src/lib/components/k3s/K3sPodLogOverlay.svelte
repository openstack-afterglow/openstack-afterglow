<script lang="ts">
	import { t } from '$lib/i18n/ns/drover';
	import RichText from '$lib/i18n/RichText.svelte';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import { useK3sClusterDetailController } from '$lib/stores/k3sClusterDetailController.svelte';
	import type { PodInfo } from '$lib/types/k3s';
	import { dialogFocus } from '$lib/utils/dialogFocus';

	interface Props {
		pod: PodInfo;
		onClose: () => void;
	}

	let { pod, onClose }: Props = $props();

	const s = useK3sClusterDetailController();

	let container = $state<string | undefined>();
	let tailLines = $state(200);
	let log = $state('');
	let loading = $state(false);
	let error = $state('');

	$effect(() => {
		container = pod.containers[0]?.name;
	});

	async function fetchLog() {
		loading = true;
		error = '';
		const result = await s.fetchPodLog(pod.name, { container, tailLines });
		if (result) {
			log = result.log;
		} else {
			error = t('podLog.loadFailed');
		}
		loading = false;
	}

	$effect(() => {
		void [container, tailLines];
		fetchLog();
	});
</script>

{#snippet podName(text: string)}<span class="text-sm font-semibold text-ink-0">{text}</span>{/snippet}
{#snippet logLabel(text: string)}<span class="ml-2 text-xs text-ink-2">{text}</span>{/snippet}

<!-- svelte-ignore a11y_click_events_have_key_events -->
<!-- svelte-ignore a11y_no_static_element_interactions -->
<div
		use:dialogFocus={{ enabled: true, onEscape: () => onClose() }}
	class="fixed inset-0 z-50 flex items-center justify-center bg-surface-scrim/70"
	onclick={(event) => {
		if (event.target === event.currentTarget) onClose();
	}}
	tabindex="-1"
	role="dialog"
	aria-modal="true"
>
	<div
		class="motion-enter bg-surface-canvas border border-line-2 rounded-lg w-[90vw] max-w-4xl max-h-[85vh] flex flex-col shadow-[var(--shadow-restraint)]"
		role="none"
	>
		<!-- Header -->
		<div class="flex items-center justify-between px-5 py-3 border-b border-line">
			<div>
				<RichText segments={t.rich('podLog.title', { name: pod.name })} tags={{ name: podName, label: logLabel }} />
			</div>
			<div class="flex items-center gap-3">
				{#if pod.containers.length > 1}
					<select
						bind:value={container}
						class="text-xs bg-surface-sunken border border-line-2 text-ink-1 rounded-md px-2 py-1"
					>
						{#each pod.containers as c}
							<option value={c.name}>{c.name}</option>
						{/each}
					</select>
				{/if}
				<select
					bind:value={tailLines}
					class="text-xs bg-surface-sunken border border-line-2 text-ink-1 rounded-md px-2 py-1"
				>
					<option value={50}>{t('podLog.tailLines', { count: 50 })}</option>
					<option value={200}>{t('podLog.tailLines', { count: 200 })}</option>
					<option value={1000}>{t('podLog.tailLines', { count: 1000 })}</option>
				</select>
				<button
					onclick={fetchLog}
					disabled={loading}
					class="text-xs px-3 py-1 bg-surface-sunken hover:bg-surface-selected text-ink-2 rounded-md transition-colors disabled:opacity-40"
				>{t('podLog.refresh')}</button>
				<button
					onclick={onClose}
					class="text-ink-2 hover:text-ink-0 transition-colors text-lg leading-none"
				>✕</button>
			</div>
		</div>

		<!-- Log body -->
		<div class="flex-1 overflow-auto p-4">
			{#if loading}
				<div class="text-ink-2 text-sm text-center py-8"><ActivityIndicator label={t('podLog.loading')} /></div>
			{:else if error}
				<div class="text-red-400 text-sm">{error}</div>
			{:else if !log}
				<div class="text-ink-2 text-sm text-center py-8">{t('podLog.empty')}</div>
			{:else}
				<pre class="text-xs text-ink-1 font-mono whitespace-pre-wrap break-words leading-relaxed">{log}</pre>
			{/if}
		</div>
	</div>
</div>
