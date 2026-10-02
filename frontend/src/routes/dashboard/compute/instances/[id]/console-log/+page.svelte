<script lang="ts">
	import { t } from '$lib/i18n/ns/instance';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
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
		return d.toLocaleTimeString(intlLocale(), { hour12: false });
	}
</script>

<svelte:head>
	<title>{t('consoleLog.pageTitle', { id: instanceId.slice(0, 8) })}</title>
</svelte:head>

<div class="min-h-screen bg-surface-canvas text-ink-1 font-mono text-xs">
	<div class="sticky top-0 bg-surface-base border-b border-line px-4 py-2 flex items-center gap-3 z-10">
		<span class="text-warm-text font-semibold">{t('consoleLog.title')}</span>
		<span class="text-ink-2 truncate max-w-md" title={instanceId}>{instanceId}</span>
		<div class="ml-auto flex items-center gap-2">
			{#if lastLoaded}
				<span class="text-ink-2 text-xs">{t('consoleLog.lastLoaded', { time: formatTime(lastLoaded) })}</span>
			{/if}
			{#if loading}
				<span class="text-ink-2 text-xs">{t('consoleLog.loading')}</span>
			{/if}
			<button
				onclick={load}
				disabled={loading}
				class="text-xs text-ink-2 hover:text-ink-0 border border-line-2 hover:border-line-2 disabled:text-ink-3 disabled:border-line px-3 py-1 rounded transition-colors"
			>
				{t('consoleLog.refresh')}
			</button>
			<button
				onclick={() => window.close()}
				class="text-xs text-ink-2 hover:text-ink-0 px-2 py-1"
				title={t('consoleLog.closeWindow')}
			>
				×
			</button>
		</div>
	</div>

	{#if error}
		<div class="p-4 text-red-400">{t('consoleLog.queryFailed', { error })}</div>
	{:else if loading && !log}
		<div class="p-4 text-ink-2">{t('consoleLog.loadingLog')}</div>
	{:else if !log}
		<div class="p-4 text-ink-2">{t('consoleLog.empty')}</div>
	{:else}
		<pre class="p-4 whitespace-pre-wrap break-all leading-relaxed">{log}</pre>
	{/if}
</div>

<style>
	/* 예전에는 body 를 #000 으로 강제해 라이트 테마에서 로그가 1.72:1 로 떨어졌다.
	   페이지는 콘솔의 다른 화면과 같은 canvas 표면을 쓴다. */
	:global(body) {
		background: var(--color-surface-canvas);
	}
</style>
