<script lang="ts">
	import { t } from '$lib/i18n/ns/chat-studio';
	import { t as panelT } from '$lib/i18n/ns/chat-panel';
	import type { AvailableModel } from '$lib/api/chatTree';
	import Field from '$lib/components/ui/Field.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import ProviderModelSelect from './ProviderModelSelect.svelte';
	import { t as commonT } from '$lib/i18n/ns/common';
	import { compileRegexSearch, matchesRegexSearch } from '$lib/utils/regexSearch';
	import { modelBillingReady } from '$lib/api/modelDomainBilling';
	const uid = $props.id();

	interface Props {
		models: AvailableModel[];
		value?: number | null;
		onSelect: (model: AvailableModel) => void;
		/** 컴팩트: 재생성 인라인용 아이콘 트리거 */
		compact?: boolean;
		disabled?: boolean;
		placeholder?: string;
		align?: 'left' | 'right' | 'center';
		/** 드롭다운 상단 검색 입력 표시(기본: 비컴팩트) */
		searchable?: boolean;
	}
	let {
		models,
		value = null,
		onSelect,
		compact = false,
		disabled = false,
		placeholder,
		align = 'left',
		searchable
	}: Props = $props();

	// 메뉴 최대 높이(px) — CSS 의 max-height 와 일치시켜 개폐 방향 판정에 사용.
	const MENU_MAX = 288;

	let open = $state(false);
	let dropUp = $state(false);
	let filter = $state('');
	let draftId = $state<number | null>(null);
	let root = $state<HTMLDivElement | null>(null);
	let triggerEl = $state<HTMLButtonElement | null>(null);
	let searchEl = $state<HTMLInputElement | null>(null);
	const searchId = `${uid}-model-search`;

	const showSearch = $derived(searchable ?? !compact);
	const current = $derived(models.find((m) => m.id === value) ?? null);
	const label = $derived(current?.display_name ?? placeholder ?? t('modelSelector.select'));
	const compiledFilter = $derived(compileRegexSearch(filter));
	const filtered = $derived(models.filter((model) =>
		matchesRegexSearch(compiledFilter, [
			model.display_name, model.model_name, model.api_model_name ?? '',
			model.api_provider ?? '', model.provider ?? ''
		])
	));
	const draft = $derived(filtered.find((model) => model.id === draftId && modelBillingReady(model)));

	function toggle() {
		if (disabled || models.length === 0) return;
		if (!open) {
			// 메뉴는 아직 언마운트 상태라 측정 불가 → 트리거 rect + 알려진 max-height 로 판정.
			// 아래 공간이 부족하고 위 공간이 더 넓을 때만 위로 연다(최상단에서 잘못 위로 열림 방지).
			const rect = triggerEl?.getBoundingClientRect();
			if (rect) {
				const below = window.innerHeight - rect.bottom;
				const above = rect.top;
				dropUp = below < MENU_MAX && above > below;
			} else {
				dropUp = false;
			}
			filter = '';
			draftId = value;
		}
		open = !open;
	}
	function choose() {
		if (!draft) return;
		open = false;
		onSelect(draft);
	}
	function onWindowClick(e: MouseEvent) {
		if (root && !root.contains(e.target as Node)) open = false;
	}
	function onKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape') open = false;
	}

	// 열릴 때 검색 입력에 포커스
	$effect(() => {
		if (open && showSearch) searchEl?.focus();
	});
</script>

<svelte:window onclick={onWindowClick} onkeydown={onKeydown} />

<div class="model-selector" class:compact bind:this={root}>
	<button
		type="button"
		class="trigger"
		class:compact
		bind:this={triggerEl}
		{disabled}
		aria-controls={open ? `${uid}-model-menu` : undefined}
		aria-expanded={open}
		title={compact ? t('modelSelector.regenerate') : label}
		onclick={toggle}
	>
		{#if compact}
			<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.8">
				<path d="M4 4v6h6M20 20v-6h-6" stroke-linecap="round" stroke-linejoin="round" />
				<path d="M20 10a8 8 0 0 0-14.9-3M4 14a8 8 0 0 0 14.9 3" stroke-linecap="round" stroke-linejoin="round" />
			</svg>
		{:else}
			<span class="trigger-label">{label}</span>
			<svg class="chev" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
				<path d="M6 9l6 6 6-6" stroke-linecap="round" stroke-linejoin="round" />
			</svg>
		{/if}
	</button>

	{#if open}
		<div id={`${uid}-model-menu`} class="menu" class:right={align === 'right'} class:up={dropUp}>
			{#if showSearch && models.length > 0}
				<Field for={searchId} label={t('modelSelector.search')} help={commonT('table.regexHelp')} error={compiledFilter.error ? commonT('table.regexError') : undefined} class="px-3 py-2">
					<div class="search">
						<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="11" cy="11" r="7" /><path d="M21 21l-4.3-4.3" stroke-linecap="round" /></svg>
						<input id={searchId} bind:this={searchEl} bind:value={filter} type="text" placeholder={t('modelSelector.search')} aria-invalid={compiledFilter.error} aria-describedby={`${searchId}-message`} />
					</div>
				</Field>
			{/if}
			<div class="picker">
				{#if filtered.length === 0}
					<p class="empty">{t('modelSelector.noResults')}</p>
				{:else}
					<ProviderModelSelect models={filtered} value={draftId} modelLabel={t('modelSelector.select')}
						onSelect={(row) => { draftId = row?.id ?? null; }} />
					<Button variant="secondary" size="sm" onclick={choose} disabled={!draft}>
						{compact ? panelT('message.regenerate') : t('modelSelector.select')}
					</Button>
				{/if}
			</div>
		</div>
	{/if}
</div>

<style>
	.model-selector {
		position: relative;
		display: inline-block;
	}
	.trigger {
		display: inline-flex;
		align-items: center;
		gap: 0.4rem;
		max-width: 100%;
		padding: 0.4rem 0.6rem;
		border-radius: 0.5rem;
		border: 1px solid var(--color-line);
		background: var(--color-surface-base);
		color: var(--color-ink-1);
		font-size: 0.8125rem;
		cursor: pointer;
		transition: background 0.15s, border-color 0.15s, color 0.15s;
	}
	.trigger:hover:not(:disabled) {
		background: var(--color-surface-sunken);
		border-color: var(--color-line-2);
		color: var(--color-ink-0);
	}
	.trigger:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}
	.trigger.compact {
		padding: 0.25rem;
		border-color: transparent;
		background: transparent;
		color: var(--color-ink-2);
	}
	.trigger.compact:hover:not(:disabled) {
		color: var(--color-ink-0);
		background: var(--color-surface-sunken);
	}
	.trigger-label {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.chev {
		flex-shrink: 0;
		color: var(--color-ink-2);
	}
	.menu {
		position: absolute;
		z-index: 30;
		top: calc(100% + 0.35rem);
		left: 0;
		display: flex;
		flex-direction: column;
		min-width: 13rem;
		max-width: 20rem;
		max-height: 18rem;
		padding: 0.3rem;
		border-radius: 0.6rem;
		border: 1px solid var(--color-line);
		background: var(--color-surface-raised);
		box-shadow: var(--shadow-popover);
	}
	.menu.right {
		left: auto;
		right: 0;
	}
	/* 아래 공간 부족 시 위로 */
	.menu.up {
		top: auto;
		bottom: calc(100% + 0.35rem);
	}
	.search {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		margin-bottom: 0.3rem;
		padding: 0.4rem 0.5rem;
		border-radius: 0.45rem;
		border: 1px solid var(--color-line);
		background: var(--color-surface-base);
		color: var(--color-ink-2);
	}
	.search input {
		flex: 1;
		min-width: 0;
		border: none;
		outline: none;
		background: transparent;
		color: var(--color-ink-1);
		font-size: 0.8125rem;
	}
	.search input::placeholder {
		color: var(--color-ink-3);
	}
	.picker {
		display: grid;
		gap: 0.5rem;
		overflow-y: auto;
		padding: 0.5rem;
	}
	.empty {
		padding: 0.5rem 0.55rem;
		font-size: 0.8125rem;
		color: var(--color-ink-2);
		list-style: none;
	}
</style>
