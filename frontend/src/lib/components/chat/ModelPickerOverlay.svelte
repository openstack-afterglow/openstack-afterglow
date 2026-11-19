<script lang="ts">
	import { t } from '$lib/i18n/ns/chat-studio';
	import RichText from '$lib/i18n/RichText.svelte';
	import type { AvailableModel } from '$lib/api/chatTree';
	import Button from '$lib/components/ui/Button.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import { toast } from '$lib/stores/toast';
	import ModelCapabilityBadges from './ModelCapabilityBadges.svelte';
	import { dialogFocus } from '$lib/utils/dialogFocus';
	import Field from '$lib/components/ui/Field.svelte';
	import { t as commonT } from '$lib/i18n/ns/common';
	import { compileRegexSearch, matchesRegexSearch } from '$lib/utils/regexSearch';
	import ProviderModelSelect from './ProviderModelSelect.svelte';
	import { modelBillingReason } from '$lib/api/modelDomainBilling';
	const uid = $props.id();

	interface Props {
		open: boolean;
		models: AvailableModel[];
		value: number | null;
		onSelect: (row: AvailableModel) => void;
		onClose: () => void;
		onRefresh?: () => void;
		refreshing?: boolean;
		refreshError?: string;
	}
	let { open, models, value, onSelect, onClose, onRefresh, refreshing = false, refreshError = '' }: Props = $props();

	let query = $state('');
	let activeProvider = $state<string | null>(null);
	let activeProviderName = $state<string | null>(null);

	function providerLabel(provider: string | null): string {
		return provider ?? t('modelPicker.otherProvider');
	}

	function apiModelName(model: AvailableModel): string {
		return model.api_model_name || model.model_name;
	}

	function apiProvider(model: AvailableModel): string {
		return model.api_provider || model.provider || 'unknown';
	}
	const compiledQuery = $derived(compileRegexSearch(query));
	function matchesModel(model: AvailableModel): boolean {
		return matchesRegexSearch(compiledQuery, [
			model.display_name, model.model_name, apiModelName(model), apiProvider(model), model.provider ?? ''
		]);
	}

	function pick(m: AvailableModel | null) {
		if (!m || modelBillingReason(m) !== null) return;
		onSelect(m);
		onClose();
	}

	async function copyModelName(modelName: string) {
		try {
			await navigator.clipboard.writeText(modelName);
			toast.success(t('modelPicker.idCopied'));
		} catch {
			toast.error(t('modelPicker.copyFailed'));
		}
	}
</script>


{#if open}
	<button
		type="button"
		class="overlay"
		tabindex="-1"
		aria-label={t('modelPicker.close')}
		onclick={onClose}
	></button>
	<div
		use:dialogFocus={{ enabled: true, onEscape: onClose }}
		class="panel"
		role="dialog"
		aria-label={t('modelPicker.select')}
		aria-describedby="model-picker-help"
		aria-modal="true"
		tabindex="-1"
	>
		<header class="head">
			<h2>{t('modelPicker.select')}</h2>
			{#if onRefresh}
				<Button variant="secondary" size="sm" onclick={onRefresh} disabled={refreshing}>
					{refreshing ? t('modelPicker.refreshing') : t('modelPicker.refresh')}
				</Button>
			{/if}
			<button type="button" class="close" onclick={onClose} aria-label={t('modelPicker.close')}>
				<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M18 6L6 18M6 6l12 12" stroke-linecap="round" /></svg>
			</button>
		</header>
		{#if refreshError}
			<Alert tone="danger" class="mx-4 mb-2">{refreshError}</Alert>
		{/if}

		<Field for="model-picker-search" label={t('modelPicker.search')} help={commonT('table.regexHelp')} error={compiledQuery.error ? commonT('table.regexError') : undefined} class="mx-4 mt-3">
			<div class="search">
				<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="11" cy="11" r="7" /><path d="M21 21l-4.3-4.3" stroke-linecap="round" /></svg>
				<!-- svelte-ignore a11y_autofocus -->
				<input id="model-picker-search" type="text" placeholder={t('modelPicker.search')} bind:value={query} aria-invalid={compiledQuery.error} aria-describedby="model-picker-search-message" autofocus />
			</div>
		</Field>
		<p id="model-picker-help" class="help"><RichText segments={t.rich('modelPicker.help')} /></p>

		<ProviderModelSelect {models} {value} onSelect={pick} modelLabel={t('modelPicker.select')}>
		{#snippet picker(groups, select)}
			{@const providers = activeProvider !== null && !groups.some((group) => group.key === activeProvider)
				? [...groups, { key: activeProvider, label: activeProviderName, models: [] }] : groups}
			{@const showProviderNav = providers.length > 1 || activeProvider !== null}
			{@const grouped = groups.filter((group) => activeProvider === null || group.key === activeProvider)
				.map((group) => ({ ...group, models: group.models.filter(matchesModel) })).filter((group) => group.models.length)}
		<div class="picker-body" class:with-providers={showProviderNav}>
			{#if showProviderNav}
				<nav class="provider-nav" aria-label={t('modelPicker.providers')}>
					<button
						type="button"
						class:active={activeProvider === null}
						aria-pressed={activeProvider === null}
						onclick={() => { activeProvider = null; activeProviderName = null; }}
					>
						<span>{t('modelPicker.all')}</span>
						<span class="provider-count">{models.length}</span>
					</button>
					{#each providers as provider (provider.key)}
						<button
							type="button"
							class:active={activeProvider === provider.key}
							aria-pressed={activeProvider === provider.key}
							onclick={() => { activeProvider = provider.key; activeProviderName = provider.label; }}
						>
							<span>{providerLabel(provider.label)}</span>
							<span class="provider-count">{provider.models.length}</span>
						</button>
					{/each}
				</nav>
			{/if}
			<div class="list">
				{#if grouped.length === 0}
					<p class="empty">{t('modelPicker.noResults')}</p>
				{:else}
					{#each grouped as g (g.key)}
						<div class="group-label">{providerLabel(g.label)}</div>
						{#each g.models as m (m.id)}
							{@const reason = modelBillingReason(m)}
							<div class="model-row" class:active={m.id === value} class:unready={reason !== null}>
								<button
									type="button"
									class="model-select"
									aria-label={t('modelPicker.selectModel', { name: m.display_name })}
									aria-pressed={m.id === value}
									aria-disabled={reason !== null}
									aria-describedby={reason === null ? undefined : `${uid}-billing-${m.id}`}
									onclick={() => select(m)}
								>
									<span class="model-main">
										<span class="model-name" title={m.display_name}>{m.display_name}</span>
										<span class="model-id"><RichText segments={t.rich('modelPicker.apiId', { id: apiModelName(m) })} /></span>
										<span class="model-provider"><RichText segments={t.rich('modelPicker.apiProvider', { provider: apiProvider(m) })} /></span>
										{#if reason !== null}
											<span class="model-billing" id={`${uid}-billing-${m.id}`}>{reason}</span>
										{/if}
									</span>
									<span class="model-caps"><ModelCapabilityBadges caps={m.capabilities} size="xs" /></span>
									{#if m.id === value}
										<svg class="check" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.2" aria-hidden="true"><path d="M20 6L9 17l-5-5" stroke-linecap="round" stroke-linejoin="round" /></svg>
									{/if}
								</button>
								<Button
									variant="ghost"
									size="sm"
									class="min-h-11 shrink-0"
									ariaLabel={t('modelPicker.copyModelId', { id: apiModelName(m) })}
									title={t('modelPicker.apiModel', { id: apiModelName(m) })}
									onclick={() => copyModelName(apiModelName(m))}
								>
									{t('modelPicker.copyId')}
								</Button>
							</div>
						{/each}
					{/each}
				{/if}
			</div>
		</div>
		{/snippet}
		</ProviderModelSelect>
	</div>
{/if}

<style>
	.overlay {
		position: fixed;
		inset: 0;
		background: color-mix(in oklab, var(--color-ink-0) 55%, transparent);
		z-index: 50;
		border: none;
	}
	/* 다크 테마에서는 밝은 ink 토큰이 아닌 canvas를 섞어 회색 막을 방지한다. */
	:global(:root:not(.light)) .overlay {
		background: color-mix(in oklab, var(--color-surface-canvas) 68%, transparent);
	}
	.panel {
		position: fixed;
		inset: 50% auto auto 50%;
		transform: translate(-50%, -50%);
		width: min(56rem, 94vw);
		height: min(80vh, 44rem);
		background: var(--color-surface-base);
		border: 1px solid var(--color-line);
		border-radius: 1rem;
		z-index: 51;
		display: flex;
		flex-direction: column;
		box-shadow: 0 24px 64px color-mix(in oklab, var(--color-ink-0) 30%, transparent);
		overflow: hidden;
	}
	.head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 1rem 1.1rem 0.7rem;
	}
	.head h2 {
		margin: 0;
		font-size: 1.05rem;
		font-weight: 650;
		color: var(--color-ink-0);
	}
	.close {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 2rem;
		height: 2rem;
		border-radius: 0.45rem;
		border: none;
		background: transparent;
		color: var(--color-ink-2);
		cursor: pointer;
	}
	.close:hover {
		background: var(--color-surface-sunken);
		color: var(--color-ink-0);
	}
	.search {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.6rem 0.8rem;
		border-radius: 0.7rem;
		border: 1px solid var(--color-line);
		background: var(--color-surface-sunken);
		color: var(--color-ink-2);
	}
	.search input {
		flex: 1;
		min-width: 0;
		border: none;
		outline: none;
		background: transparent;
		color: var(--color-ink-0);
		font-size: 0.9rem;
	}
	.search input::placeholder {
		color: var(--color-ink-3);
	}
	.help {
		margin: 0 1.1rem 0.6rem;
		font-size: 0.75rem;
		color: var(--color-ink-2);
	}
	.picker-body {
		display: flex;
		flex: 1;
		min-height: 0;
		flex-direction: column;
	}
	.provider-nav {
		display: flex;
		max-height: 7rem;
		flex-shrink: 0;
		flex-wrap: wrap;
		gap: 0.25rem;
		overflow-y: auto;
		padding: 0.15rem 0.75rem 0.65rem;
		border-bottom: 1px solid var(--color-line);
	}
	.provider-nav button {
		display: inline-flex;
		min-height: 2.5rem;
		max-width: 100%;
		flex-shrink: 0;
		align-items: center;
		justify-content: space-between;
		gap: 0.65rem;
		padding: 0.45rem 0.65rem;
		border: 1px solid transparent;
		border-radius: 0.55rem;
		background: transparent;
		color: var(--color-ink-2);
		font-size: 0.8rem;
		font-weight: 600;
		cursor: pointer;
		white-space: nowrap;
	}
	.provider-nav button > span:first-child {
		min-width: 0;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.provider-nav button:hover {
		background: var(--color-surface-sunken);
		color: var(--color-ink-0);
	}
	.provider-nav button:focus-visible {
		outline: none;
		box-shadow: var(--focus-ring);
	}
	.provider-nav button.active {
		border-color: var(--color-line-2);
		background: var(--color-surface-raised);
		color: var(--color-ink-0);
	}
	.provider-count {
		color: var(--color-ink-2);
		font-family: var(--font-mono);
		font-size: 0.68rem;
		flex-shrink: 0;
	}
	.list {
		flex: 1;
		min-width: 0;
		min-height: 0;
		overflow-y: auto;
		padding: 0 0.6rem 0.8rem;
	}
	.empty {
		padding: 2rem;
		text-align: center;
		color: var(--color-ink-2);
		font-size: 0.85rem;
	}
	.group-label {
		padding: 0.7rem 0.6rem 0.35rem;
		font-size: 0.7rem;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		color: var(--color-ink-2);
	}
	.model-row {
		display: flex;
		align-items: center;
		gap: 0.25rem;
		width: 100%;
		padding: 0.25rem 0.5rem 0.25rem 0;
		border: 1px solid transparent;
		border-radius: 0.6rem;
		background: transparent;
	}
	.model-row:hover {
		background: var(--color-surface-sunken);
	}
	.model-row.active {
		background: var(--color-surface-raised);
		border-color: var(--color-accent);
	}
	.model-select {
		flex: 1;
		min-width: 0;
		display: grid;
		grid-template-columns: minmax(0, 1fr) auto;
		align-items: center;
		gap: 0.5rem;
		padding: 0.5rem 0.7rem;
		border: none;
		border-radius: 0.5rem;
		background: transparent;
		cursor: pointer;
		text-align: left;
	}
	.model-select:focus-visible {
		outline: none;
		box-shadow: var(--focus-ring);
	}
	.model-caps {
		grid-column: 1;
		grid-row: 2;
	}
	.model-caps:empty {
		display: none;
	}
	.model-main {
		flex: 1;
		min-width: 0;
		display: flex;
		flex-direction: column;
		gap: 0.1rem;
	}
	.model-name {
		font-size: 0.88rem;
		font-weight: 600;
		color: var(--color-ink-0);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.model-id {
		font-size: 0.75rem;
		color: var(--color-ink-2);
		overflow-wrap: anywhere;
	}
	.model-id :global(code) {
		font-family: var(--font-mono);
	}
	.model-provider {
		font-size: 0.7rem;
		color: var(--color-ink-2);
		overflow-wrap: anywhere;
	}
	.model-provider :global(code) {
		font-family: var(--font-mono);
	}
	.model-billing {
		font-size: 0.72rem;
		color: var(--color-state-warning);
		overflow-wrap: anywhere;
	}
	.model-row.unready .model-select {
		cursor: not-allowed;
	}
	.model-row.unready .model-name {
		color: var(--color-ink-2);
	}
	.check {
		grid-column: 2;
		grid-row: 1 / 3;
		flex-shrink: 0;
		color: var(--color-accent);
	}
	@media (min-width: 768px) {
		.picker-body.with-providers {
			display: grid;
			grid-template-columns: 12rem minmax(0, 1fr);
		}
		.provider-nav {
			min-width: 0;
			flex-direction: column;
			max-height: none;
			flex-wrap: nowrap;
			overflow-x: visible;
			overflow-y: auto;
			padding: 0.25rem 0.6rem 0.8rem;
			border-right: 1px solid var(--color-line);
			border-bottom: none;
		}
		.provider-nav button {
			width: 100%;
		}
		.model-select {
			display: flex;
			gap: 0.7rem;
		}
		.model-caps {
			flex-shrink: 0;
		}
	}
</style>
