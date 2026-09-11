<script lang="ts">
	import { page } from '$app/stores';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';

	const instanceId = $derived($page.params.id ?? '');
	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	let log = $state('');
	let loading = $state(false);
	let error = $state('');
	let lastLoaded = $state<Date | null>(null);

	async function load() {
		if (!instanceId) return;
		loading = true;
		error = '';
		try {
			const data = await api.get<{ output: string }>(
				`/api/v1/instances/${instanceId}/log?length=100000`,
				token,
				projectId
			);
			log = data.output ?? '';
			lastLoaded = new Date();
		} catch (e) {
			error = e instanceof ApiError ? e.message : String(e);
		} finally {
			loading = false;
		}
	}

	$effect(() => {
		if (instanceId && token) load();
	});

	function formatTime(d: Date | null) {
		if (!d) return '';
		return d.toLocaleTimeString('ko-KR', { hour12: false });
	}
</script>

<svelte:head>
	<title>콘솔 로그 — {instanceId.slice(0, 8)}</title>
</svelte:head>

<div class="min-h-screen bg-surface-scrim text-ink-1 font-mono text-xs">
	<div class="sticky top-0 bg-surface-base border-b border-line px-4 py-2 flex items-center gap-3 z-10">
		<span class="text-action-warm font-semibold">콘솔 로그</span>
		<span class="text-ink-3 truncate max-w-md" title={instanceId}>{instanceId}</span>
		<div class="ml-auto flex items-center gap-2">
			{#if lastLoaded}
				<span class="text-ink-3 text-xs">마지막 로드: {formatTime(lastLoaded)}</span>
			{/if}
			{#if loading}
				<span class="text-ink-3 text-xs">로딩...</span>
			{/if}
			<button
				onclick={load}
				disabled={loading}
				class="text-xs text-ink-2 hover:text-ink-0 border border-line-2 hover:border-line-2 disabled:text-ink-3 disabled:border-line px-3 py-1 rounded transition-colors"
			>
				새로고침
			</button>
			<button
				onclick={() => window.close()}
				class="text-xs text-ink-2 hover:text-ink-0 px-2 py-1"
				title="창 닫기"
			>
				×
			</button>
		</div>
	</div>

	{#if error}
		<div class="p-4 text-red-400">로그 조회 실패: {error}</div>
	{:else if loading && !log}
		<div class="p-4 text-ink-3">로딩 중...</div>
	{:else if !log}
		<div class="p-4 text-ink-3">(로그 없음)</div>
	{:else}
		<pre class="p-4 whitespace-pre-wrap break-all leading-relaxed">{log}</pre>
	{/if}
</div>

<style>
	:global(body) {
		background: #000;
	}
</style>
