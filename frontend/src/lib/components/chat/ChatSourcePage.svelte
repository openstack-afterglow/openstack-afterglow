<script lang="ts">
	import { onDestroy, untrack } from 'svelte';
	import { get } from 'svelte/store';
	import { auth, authReady, projectSwitching } from '$lib/stores/auth';
	import { createPrivateViewScope } from '$lib/utils/privateViewScope';
	import { getChatSourceAsset, getChatSourceDownloadLink, getRegisteredChatSource, type ChatSourceAsset, type RegisteredChatSource } from '$lib/api/chatSources';
	import { citationLabel, isSafeCitationHttpUrl } from '$lib/api/chatCitations';
	import { ApiError } from '$lib/api/errors';
	import { Alert, Button, PageShell } from '$lib/components/ui';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import { t } from '$lib/i18n/ns/chat-panel';
	import { intlLocale } from '$lib/i18n/runtime.svelte';

	interface Props { assetId?: string; runId?: string; citationId?: string }
	let { assetId, runId, citationId }: Props = $props();
	const lifetime = createPrivateViewScope();
	let source = $state<RegisteredChatSource | null>(null);
	let asset = $state<ChatSourceAsset | null>(null);
	let loading = $state(false);
	let downloading = $state(false);
	let error = $state<'expired' | 'denied' | 'unavailable' | 'failed' | null>(null);
	let downloadError = $state(false);
	let revision = $state(0);
	let readinessEpoch = $state(0);
	let serial = 0;
	let controller: AbortController | null = null;
	let downloadController: AbortController | null = null;
	let destroyed = false;
	function retire() {
		serial++;
		controller?.abort();
		downloadController?.abort();
		source = null; asset = null; error = null; downloadError = false;
		loading = false; downloading = false;
	}
	const stopLifetime = lifetime.subscribe((next) => { retire(); revision = next; });
	// Readiness and switch entry edges must invalidate even a same-tick ABA.
	const stopReady = authReady.subscribe((ready) => { if (!ready) { retire(); readinessEpoch++; } });
	const stopSwitch = projectSwitching.subscribe((switching) => { if (switching) retire(); });
	const ready = $derived($authReady && !$projectSwitching && Boolean($auth.token && $auth.projectId && $auth.userId));
	const target = $derived(assetId ?? `${runId ?? ''}:${citationId ?? ''}`);
	const displayTitle = $derived(asset?.name ?? (source ? citationLabel(source) : t('message.sources')));
	const downloadableId = $derived(asset?.id ?? source?.asset_id);
	const externalUrl = $derived.by(() => {
		if (!source || !['web', 'data_source'].includes(source.source_kind) || !source.url || !isSafeCitationHttpUrl(source.url)) return null;
		const url = new URL(source.url);
		return /^\/lumen\/sources\//.test(url.pathname) ? null : source.url;
	});

	async function load() {
		retire();
		if (!ready) return;
		const current = ++serial;
		const owner = get(lifetime);
		const destination = target;
		const identity = get(auth);
		controller = new AbortController();
		const signal = controller.signal;
		const scope = { token: identity.token!, projectId: identity.projectId!, signal };
		const owns = () => !destroyed && serial === current && get(lifetime) === owner && target === destination && get(authReady) && !get(projectSwitching) && !signal.aborted;
		loading = true;
		try {
			if (assetId) {
				const result = await getChatSourceAsset(assetId, scope);
				if (owns()) asset = result;
			} else if (runId && citationId) {
				const result = await getRegisteredChatSource(runId, citationId, scope);
				if (owns()) source = result;
			} else if (owns()) error = 'failed';
		} catch (caught) {
			if (owns()) error = caught instanceof ApiError && caught.status === 410 ? 'expired'
				: caught instanceof ApiError && caught.status === 403 ? 'denied'
				: assetId && caught instanceof ApiError && [404, 409].includes(caught.status) ? 'unavailable' : 'failed';
		}
		finally { if (owns()) loading = false; }
	}
	$effect(() => { void revision; void readinessEpoch; void target; void ready; untrack(() => { void load(); }); });

	async function download() {
		if (!ready || downloading || !downloadableId) return;
		const id = downloadableId;
		const current = serial;
		const owner = get(lifetime);
		const identity = get(auth);
		downloadController = new AbortController();
		const signal = downloadController.signal;
		const owns = () => !destroyed && serial === current && get(lifetime) === owner && get(authReady) && !get(projectSwitching) && !signal.aborted;
		downloading = true; downloadError = false;
		try {
			const url = await getChatSourceDownloadLink(id, { token: identity.token!, projectId: identity.projectId!, signal });
			if (!owns()) return;
			const link = document.createElement('a');
			link.href = url;
			link.rel = 'noopener noreferrer';
			link.referrerPolicy = 'no-referrer';
			link.download = asset?.name ?? source?.title ?? 'download';
			link.click();
		} catch { if (owns()) downloadError = true; }
		finally { if (owns()) downloading = false; }
	}
	onDestroy(() => { destroyed = true; retire(); stopLifetime(); stopReady(); stopSwitch(); });
</script>

<svelte:head><title>{t('message.sources')} · Lumen</title><meta name="referrer" content="no-referrer" /></svelte:head>
<main id="main-content" tabindex="-1" class="min-h-[100dvh] min-w-0 pt-[var(--app-header-height)] focus:outline-none">
	<PageShell>
		<h1 class="mb-6 break-words text-2xl font-semibold text-ink-0">{ready ? displayTitle : t('message.sources')}</h1>
		{#if !ready}
			<p class="text-sm text-ink-2">{t('sourcePage.scopeRequired')}</p>
		{:else if loading}
			<LoadingState label={t('window.loading')} />
		{:else if error}
			<div class="space-y-4">
				<Alert tone={error === 'expired' || error === 'unavailable' ? 'warning' : 'danger'}>{error === 'expired' ? t('sourcePage.expired') : error === 'denied' ? t('sourcePage.denied') : error === 'unavailable' ? t('sourcePage.assetUnavailable') : t('sourcePage.failed')}</Alert>
				{#if error === 'failed'}<Button variant="secondary" onclick={load}>{t('sourcePage.retry')}</Button>{/if}
			</div>
		{:else if source || asset}
			<section class="space-y-4 break-words" aria-label={t('message.sources')}>
				{#if source?.snippet}<p class="whitespace-pre-wrap text-sm leading-relaxed text-ink-1">{source.snippet}</p>{/if}
				{#if asset}<p class="text-sm text-ink-2">{asset.mime_type} · {new Intl.NumberFormat(intlLocale()).format(asset.size_bytes)} B</p>{/if}
				{#if source?.source_id}<p class="break-all font-mono text-xs text-ink-2">{source.source_id}</p>{/if}
				{#if source?.observed_at}<time class="block text-xs text-ink-2" datetime={source.observed_at}>{source.observed_at}</time>{/if}
				{#if source?.provenance && Object.keys(source.provenance).length}
					<dl class="grid gap-2 text-sm md:grid-cols-[max-content_minmax(0,1fr)]">
						{#each Object.entries(source.provenance) as [key, value] (key)}<dt class="text-ink-2">{key}</dt><dd class="min-w-0 whitespace-pre-wrap text-ink-1">{typeof value === 'string' ? value : JSON.stringify(value)}</dd>{/each}
					</dl>
				{/if}
				{#if externalUrl}<a class="inline-flex min-h-11 items-center break-all text-sm text-accent underline" href={externalUrl} target="_blank" rel="noopener noreferrer nofollow" referrerpolicy="no-referrer">{t('sourcePage.open')} · {externalUrl}</a>{/if}
				{#if downloadableId}
					<p class="text-sm text-ink-2">{t('sourcePage.downloadHint')}</p>
					<Button disabled={downloading} onclick={download}>{downloading ? t('toolCall.downloading') : t('toolCall.downloadFile', { name: displayTitle })}</Button>
				{/if}
				{#if downloadError}<Alert tone="danger">{t('toolCall.downloadFailed')}</Alert>{/if}
			</section>
		{/if}
	</PageShell>
</main>
