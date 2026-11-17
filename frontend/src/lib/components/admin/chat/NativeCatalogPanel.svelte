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
	import Field from '$lib/components/ui/Field.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import SelectInput from '$lib/components/ui/SelectInput.svelte';
	import Pagination from '$lib/components/ui/Pagination.svelte';
	import Pill from '$lib/components/ui/Pill.svelte';
	import NativeCatalogPricing from './NativeCatalogPricing.svelte';
	import ModelCapabilityBadges from '$lib/components/chat/ModelCapabilityBadges.svelte';
	import { modelKindLabel, type ModelKind } from './modelPricing';

	let catalog = $state<NativeCatalog | null>(null);
	let loading = $state(false);
	let failed = $state(false);
	let epoch = 0;
	let identity = '';
	let ownerRevision = $state(0);
	let destroyed = false;
	let controller: AbortController | null = null;
	const panelId = $props.id();
	const kinds: ModelKind[] = ['text', 'image', 'tts', 'stt', 'realtime', 'embedding'];
	let query = $state('');
	let kind = $state('');
	let pageSize = $state('5');
	let pages = $state<Record<string, number>>({});
	let expanded = $state<Record<string, boolean>>({});
	const providerViews = $derived.by(() => {
		const needle = query.trim().toLocaleLowerCase();
		return (catalog?.providers ?? []).map(provider => ({
			provider,
			models: provider.models.filter(model => (!kind || model.kind === kind) &&
				(!needle || model.id.toLocaleLowerCase().includes(needle) || model.display_name.toLocaleLowerCase().includes(needle)))
		}));
	});
	const totalModels = $derived(catalog?.providers.reduce((total, provider) => total + provider.models.length, 0) ?? 0);
	const filteredModels = $derived(providerViews.reduce((total, view) => total + view.models.length, 0));
	function resetPages() { pages = {}; }
	function reset() {
		++epoch; controller?.abort(); controller = null;
		++ownerRevision;
		catalog = null; loading = false; failed = false;
		query = ''; kind = ''; pageSize = '5'; pages = {}; expanded = {};
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

<section class="mb-6 min-w-0 rounded-lg border border-line p-4" aria-labelledby={`${panelId}-heading`} data-testid="native-catalog">
	<div class="flex flex-wrap items-center justify-between gap-3">
		<h3 id={`${panelId}-heading`} class="text-sm font-semibold text-ink-1">{t('catalog.title')}</h3>
		<Button variant="outline" size="sm" onclick={load} disabled={loading} ariaBusy={loading}>{t('catalog.load')}</Button>
	</div>
	<p class="mt-2 text-xs leading-relaxed text-ink-2">{t('catalog.description')}</p>
	{#if loading}
		<LoadingState variant="section" label={t('catalog.load')} class="mt-3" />
	{:else if failed}
		<Alert tone="warning" class="mt-3">{t('catalog.error')}</Alert>
	{:else if catalog}
		<p class="mt-3 text-xs font-medium text-ink-1">{t('catalog.version', { version: catalog.catalog_version })}</p>
		<div class="mt-3 grid min-w-0 gap-3 md:grid-cols-[minmax(0,1fr)_minmax(0,12rem)_minmax(0,8rem)]">
			<Field label={t('catalog.filter')} for={`${panelId}-filter`} help={t('catalog.filterHelp')}>
				<TextInput id={`${panelId}-filter`} type="search" bind:value={query} oninput={resetPages} />
			</Field>
			<Field label={t('catalog.kind')} for={`${panelId}-kind`}>
				<SelectInput id={`${panelId}-kind`} bind:value={kind} onchange={resetPages}>
					<option value="">{t('catalog.allKinds')}</option>
					{#each kinds as value (value)}<option value={value}>{modelKindLabel(value)}</option>{/each}
				</SelectInput>
			</Field>
			<Field label={t('catalog.pageSize')} for={`${panelId}-page-size`}>
				<SelectInput id={`${panelId}-page-size`} bind:value={pageSize} onchange={resetPages}>
					<option value="5">5</option><option value="10">10</option>
				</SelectInput>
			</Field>
		</div>
		<p class="mt-3 text-xs tabular-nums text-ink-2" role="status">{t('catalog.count', { filtered: filteredModels, total: totalModels })}</p>
		{#each providerViews as { provider, models } (provider.provider_type)}
			{@const page = Math.min(pages[provider.provider_type] ?? 1, Math.max(1, Math.ceil(models.length / Number(pageSize))))}
			<section class="mt-3 min-w-0 border-t border-line pt-3" aria-labelledby={`${panelId}-${provider.provider_type}`}>
				<h4 id={`${panelId}-${provider.provider_type}`}>
					<Button variant="subtle" size="sm" class="max-w-full whitespace-normal text-left" ariaExpanded={!!expanded[provider.provider_type]} onclick={() => { expanded[provider.provider_type] = !expanded[provider.provider_type]; }}>
						{provider.display_name} · {t('catalog.count', { filtered: models.length, total: provider.models.length })}
					</Button>
				</h4>
				{#if expanded[provider.provider_type]}
					<div class="mt-2 flex flex-wrap gap-3">
						{#each provider.pricing_sources as source (source)}
							{#if catalogSourceUrl(source)}<a class="break-all text-xs text-ink-2 underline" href={catalogSourceUrl(source)} target="_blank" rel="noreferrer">{t('catalog.source')} · {new URL(source).hostname}</a>{/if}
						{/each}
					</div>
					<ul class="mt-3 min-w-0 space-y-3">
						{#each models.slice((page - 1) * Number(pageSize), page * Number(pageSize)) as model (model.id)}
							<li class="min-w-0 border-t border-line pt-3" data-testid="catalog-model">
								<div class="flex flex-wrap items-center gap-2 text-sm text-ink-1">
									<span class="break-all font-medium">{model.display_name}</span><code class="break-all text-xs">{model.id}</code>
									<Pill size="xs">{modelKindLabel(model.kind)}</Pill>
									<Pill size="xs" tone={model.status === 'deprecated' ? 'warning' : 'neutral'}>{t(`status.${model.status}`)}</Pill>
								</div>
								<p class="mt-1 text-xs text-ink-2">{t('catalog.verified', { date: model.verified_at })}</p>
								<p class="mt-1 break-words text-xs text-ink-2">{adminT('configuration.contextLimit')}: {model.context_window ?? '—'} · {t('catalog.maxOutput')}: {model.max_output_tokens ?? '—'}</p>
								<p class="mt-1 break-words text-xs text-ink-2">{adminT('configuration.input')}: {model.input_modalities.join(', ')} · {adminT('configuration.output')}: {model.output_modalities.join(', ')}</p>
								<ModelCapabilityBadges caps={model.capabilities} />
								{#if model.embedding}
									<section class="mt-3" aria-label={t('embedding.title')} data-testid="catalog-embedding">
										<h5 class="mb-2 text-xs font-medium text-ink-1">{t('embedding.title')}</h5>
										<dl class="embedding-facts">
											<div><dt>{t('embedding.default')}</dt><dd>{model.embedding.default_dimensions ?? '—'}</dd></div>
											<div><dt>{t('embedding.adjustable')}</dt><dd>{t(model.embedding.supports_dimensions ? 'embedding.yes' : 'embedding.no')}</dd></div>
											<div><dt>{t('embedding.range')}</dt><dd>{model.embedding.min_dimensions ?? '—'} – {model.embedding.max_dimensions ?? '—'}</dd></div>
											<div><dt>{t('embedding.choices')}</dt><dd>{model.embedding.allowed_dimensions?.join(', ') || '—'}</dd></div>
										</dl>
									</section>
								{/if}
								<NativeCatalogPricing tokens={model.token_pricing} media={model.media_pricing} />
								{#if model.notes}<p class="mt-2 break-words text-xs leading-relaxed text-ink-2">{model.notes}</p>{/if}
								<div class="mt-2 flex flex-wrap gap-3">{#each model.source_urls as source (source)}{#if catalogSourceUrl(source)}<a class="break-all text-xs text-ink-2 underline" href={catalogSourceUrl(source)} target="_blank" rel="noreferrer">{t('catalog.source')} · {new URL(source).hostname}</a>{/if}{/each}</div>
							</li>
						{:else}<li class="text-sm text-ink-2">{t('catalog.noMatches')}</li>{/each}
					</ul>
					{#if models.length}
						<Pagination {page} totalPages={Math.ceil(models.length / Number(pageSize))} hasPrev={page > 1} hasNext={page * Number(pageSize) < models.length}
							onPrev={() => { pages[provider.provider_type] = page - 1; }} onNext={() => { pages[provider.provider_type] = page + 1; }}
							total={models.length} pageSize={Number(pageSize)} />
					{/if}
				{/if}
			</section>
		{:else}<p class="mt-3 text-sm text-ink-2">{t('catalog.empty')}</p>{/each}
	{/if}
</section>

<style>
	.embedding-facts { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 12rem), 1fr)); gap: 0.5rem 1rem; min-width: 0; font-size: var(--type-support); color: var(--color-ink-2); }
	.embedding-facts div { min-width: 0; }
	.embedding-facts dd { margin: 0.25rem 0 0; color: var(--color-ink-1); font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
</style>
