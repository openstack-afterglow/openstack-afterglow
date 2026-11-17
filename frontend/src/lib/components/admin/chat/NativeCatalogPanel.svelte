<script lang="ts">
	import { onDestroy, untrack } from 'svelte';
	import { auth, authReady, projectSwitching } from '$lib/stores/auth';
	import { api } from '$lib/api/client';
	import { catalogSourceUrl, type NativeCatalog } from '$lib/api/nativeCatalog';
	import { t } from '$lib/i18n/ns/native-providers';
	import { t as adminT } from '$lib/i18n/ns/admin-chat';
	import Button from '$lib/components/ui/Button.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import ModelCapabilityBadges from '$lib/components/chat/ModelCapabilityBadges.svelte';
	import { modelKindLabel } from './modelPricing';

	let catalog = $state<NativeCatalog | null>(null);
	let loading = $state(false);
	let failed = $state(false);
	let epoch = 0;
	let identity = '';
	let ownerRevision = $state(0);
	let destroyed = false;
	let controller: AbortController | null = null;
	function reset() {
		++epoch; controller?.abort(); controller = null;
		++ownerRevision;
		catalog = null; loading = false; failed = false;
	}
	const unsubscribe = auth.subscribe((state) => {
		const next = JSON.stringify([state.userId, state.sessionId, state.projectId, state.identityDomainId, state.domainId, state.isSystemAdmin, state.roles]);
		if (identity !== next) { identity = next; reset(); }
	});
	const stopReady = authReady.subscribe((ready) => { if (!ready) reset(); });
	const stopSwitching = projectSwitching.subscribe((switching) => { if (switching) reset(); });
	async function load() {
		if (!$auth.token || !$auth.isSystemAdmin || !$authReady || $projectSwitching) return;
		controller?.abort(); controller = new AbortController();
		const requestController = controller, generation = ++epoch;
		const current = () => !destroyed && epoch === generation;
		loading = true; failed = false;
		try {
			const result = await api.get<NativeCatalog>('/api/v1/chat/admin/models/native-catalog', $auth.token, $auth.projectId ?? undefined, { signal: requestController.signal, cache: 'no-store' });
			if (!result || Array.isArray(result) || result.schema_version !== 1 || typeof result.catalog_version !== 'string' || !result.catalog_version.trim() || !Array.isArray(result.providers)) {
				throw new Error('Invalid native catalog response');
			}
			if (current()) catalog = result;
		} catch {
			if (current()) { catalog = null; failed = true; }
		} finally { if (current()) loading = false; }
	}
	$effect(() => {
		void ownerRevision;
		if ($auth.token && $auth.isSystemAdmin && $authReady && !$projectSwitching) untrack(() => void load());
	});
	onDestroy(() => { destroyed = true; reset(); unsubscribe(); stopReady(); stopSwitching(); });
</script>

<section class="mb-6 rounded-lg border border-line p-4" aria-labelledby="native-catalog-heading" data-testid="native-catalog">
	<div class="flex flex-wrap items-center justify-between gap-3">
		<h3 id="native-catalog-heading" class="text-sm font-semibold text-ink-1">{t('catalog.title')}</h3>
		<Button variant="outline" size="sm" onclick={load} disabled={loading} ariaBusy={loading}>{t('catalog.load')}</Button>
	</div>
	<p class="mt-2 text-xs leading-relaxed text-ink-2">{t('catalog.description')}</p>
	{#if loading}
		<LoadingState variant="section" label={t('catalog.load')} class="mt-3" />
	{:else if failed}
		<Alert tone="warning" class="mt-3">{t('catalog.error')}</Alert>
	{:else if catalog}
		<p class="mt-3 text-xs font-medium text-ink-1">{t('catalog.version', { version: catalog.catalog_version })}</p>
		{#each catalog.providers ?? [] as provider (provider.provider_type)}
			<details class="mt-3 border-t border-line pt-3">
				<summary class="cursor-pointer text-sm font-medium text-ink-1">{provider.display_name} · {provider.models.length}</summary>
				<div class="mt-2 flex flex-wrap gap-3">
					{#each provider.pricing_sources as source (source)}
						{#if catalogSourceUrl(source)}<a class="break-all text-xs text-ink-2 underline" href={catalogSourceUrl(source)} target="_blank" rel="noreferrer">{t('catalog.source')} · {new URL(source).hostname}</a>{/if}
					{/each}
				</div>
				<ul class="mt-3 space-y-3">
					{#each provider.models as model (model.id)}
						<li class="min-w-0 border-t border-line pt-3">
							<div class="flex flex-wrap items-center gap-2 text-sm text-ink-1"><span class="break-all font-medium">{model.display_name}</span><code class="break-all text-xs">{model.id}</code><span class="text-xs">{modelKindLabel(model.kind)} · {model.status}</span></div>
							<p class="mt-1 text-xs text-ink-2">{t('catalog.verified', { date: model.verified_at })}</p>
							<p class="mt-1 text-xs text-ink-2">{adminT('configuration.contextLimit')}: {model.context_window ?? '—'} · {model.input_modalities.join(', ')} → {model.output_modalities.join(', ')}</p>
							<ModelCapabilityBadges caps={model.capabilities} />
							{#if model.token_pricing}
								<p class="mt-1 break-words text-xs tabular-nums text-ink-2">{adminT('configuration.input')}: {model.token_pricing.input ?? '—'} · {adminT('configuration.output')}: {model.token_pricing.output ?? '—'} · {adminT('configuration.cacheRead')}: {model.token_pricing.cache_read ?? '—'} · {t('price.cacheWrite')}: {model.token_pricing.cache_write ?? '—'} · {t('price.cacheWriteLong')}: {model.token_pricing.cache_write_long ?? '—'} · {adminT('configuration.usd1mTokens')}</p>
								<pre class="mt-2 overflow-x-auto whitespace-pre-wrap break-words text-xs text-ink-2">{JSON.stringify(model.token_pricing, null, 2)}</pre>
							{/if}
							{#if model.media_pricing}<pre class="mt-2 overflow-x-auto whitespace-pre-wrap break-words text-xs text-ink-2">{JSON.stringify(model.media_pricing, null, 2)}</pre>{/if}
							{#if model.notes}<p class="mt-1 text-xs leading-relaxed text-ink-2">{model.notes}</p>{/if}
							<div class="mt-2 flex flex-wrap gap-3">{#each model.source_urls as source (source)}{#if catalogSourceUrl(source)}<a class="break-all text-xs text-ink-2 underline" href={catalogSourceUrl(source)} target="_blank" rel="noreferrer">{t('catalog.source')} · {new URL(source).hostname}</a>{/if}{/each}</div>
						</li>
					{/each}
				</ul>
			</details>
		{:else}<p class="mt-3 text-sm text-ink-2">{t('catalog.empty')}</p>{/each}
	{/if}
</section>
