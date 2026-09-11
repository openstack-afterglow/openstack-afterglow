<script lang="ts">
	import { useK3sClusterDetailController } from '$lib/stores/k3sClusterDetailController.svelte';
	import type { PodInfo } from '$lib/types/k3s';

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
			error = '로그 조회 실패';
		}
		loading = false;
	}

	$effect(() => {
		void [container, tailLines];
		fetchLog();
	});
</script>

<div
	class="fixed inset-0 z-50 flex items-center justify-center bg-surface-scrim/70"
	onclick={(event) => {
		if (event.target === event.currentTarget) onClose();
	}}
	onkeydown={(event) => event.key === 'Escape' && onClose()}
	tabindex="-1"
	role="dialog"
	aria-modal="true"
>
	<div
		class="bg-surface-canvas border border-line-2 rounded-lg w-[90vw] max-w-4xl max-h-[85vh] flex flex-col shadow-[var(--shadow-restraint)]"
		role="none"
	>
		<!-- Header -->
		<div class="flex items-center justify-between px-5 py-3 border-b border-line">
			<div>
				<span class="text-sm font-semibold text-ink-0">{pod.name}</span>
				<span class="ml-2 text-xs text-ink-2">로그</span>
			</div>
			<div class="flex items-center gap-3">
				{#if pod.containers.length > 1}
					<select
						bind:value={container}
						class="text-xs bg-surface-sunken border border-line-2 text-ink-1 rounded-lg px-2 py-1"
					>
						{#each pod.containers as c}
							<option value={c.name}>{c.name}</option>
						{/each}
					</select>
				{/if}
				<select
					bind:value={tailLines}
					class="text-xs bg-surface-sunken border border-line-2 text-ink-1 rounded-lg px-2 py-1"
				>
					<option value={50}>마지막 50줄</option>
					<option value={200}>마지막 200줄</option>
					<option value={1000}>마지막 1000줄</option>
				</select>
				<button
					onclick={fetchLog}
					disabled={loading}
					class="text-xs px-3 py-1 bg-surface-sunken hover:bg-surface-selected text-ink-2 rounded-lg transition-colors disabled:opacity-40"
				>새로고침</button>
				<button
					onclick={onClose}
					class="text-ink-2 hover:text-ink-0 transition-colors text-lg leading-none"
				>✕</button>
			</div>
		</div>

		<!-- Log body -->
		<div class="flex-1 overflow-auto p-4">
			{#if loading}
				<div class="text-ink-2 text-sm text-center py-8">로딩 중...</div>
			{:else if error}
				<div class="text-red-400 text-sm">{error}</div>
			{:else if !log}
				<div class="text-ink-3 text-sm text-center py-8">로그 없음</div>
			{:else}
				<pre class="text-xs text-ink-1 font-mono whitespace-pre-wrap break-words leading-relaxed">{log}</pre>
			{/if}
		</div>
	</div>
</div>
