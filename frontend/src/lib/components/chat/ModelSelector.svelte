<script lang="ts">
	import type { AvailableModel } from '$lib/api/chatTree';

	interface Props {
		models: AvailableModel[];
		value?: string;
		onSelect: (modelName: string) => void;
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
		value = '',
		onSelect,
		compact = false,
		disabled = false,
		placeholder = '모델 선택',
		align = 'left',
		searchable
	}: Props = $props();

	// 메뉴 최대 높이(px) — CSS 의 max-height 와 일치시켜 개폐 방향 판정에 사용.
	const MENU_MAX = 288;

	let open = $state(false);
	let dropUp = $state(false);
	let filter = $state('');
	let root = $state<HTMLDivElement | null>(null);
	let triggerEl = $state<HTMLButtonElement | null>(null);
	let searchEl = $state<HTMLInputElement | null>(null);

	const showSearch = $derived(searchable ?? !compact);
	const current = $derived(models.find((m) => m.model_name === value) ?? null);
	const label = $derived(current?.display_name ?? placeholder);
	const filtered = $derived.by(() => {
		const q = filter.trim().toLowerCase();
		if (!q) return models;
		return models.filter(
			(m) =>
				m.display_name.toLowerCase().includes(q) ||
				(m.api_model_name || m.model_name).toLowerCase().includes(q) ||
				(m.api_provider ?? '').toLowerCase().includes(q) ||
				(m.provider ?? '').toLowerCase().includes(q)
		);
	});

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
		}
		open = !open;
	}
	function choose(name: string) {
		open = false;
		onSelect(name);
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
		aria-haspopup="listbox"
		aria-expanded={open}
		title={compact ? '다른 모델로 재생성' : label}
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
		<div class="menu" class:right={align === 'right'} class:up={dropUp} role="listbox" aria-label="모델 선택">
			{#if showSearch && models.length > 0}
				<div class="search">
					<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="11" cy="11" r="7" /><path d="M21 21l-4.3-4.3" stroke-linecap="round" /></svg>
					<input bind:this={searchEl} bind:value={filter} type="text" placeholder="모델 검색" />
				</div>
			{/if}
			<ul class="items">
				{#if models.length === 0}
					<li class="empty">사용 가능한 모델 없음</li>
				{:else if filtered.length === 0}
					<li class="empty">검색 결과 없음</li>
				{:else}
					{#each filtered as m (m.model_name)}
						<li>
							<button
								type="button"
								role="option"
								aria-selected={m.model_name === value}
								class="item"
								class:active={m.model_name === value}
								onclick={() => choose(m.model_name)}
							>
								<span class="item-main">
									<span class="item-label">{m.display_name}</span>
									{#if m.provider}<span class="item-provider">{m.provider}</span>{/if}
								</span>
								{#if m.model_name === value}
									<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.2">
										<path d="M20 6L9 17l-5-5" stroke-linecap="round" stroke-linejoin="round" />
									</svg>
								{/if}
							</button>
						</li>
					{/each}
				{/if}
			</ul>
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
		color: var(--color-ink-3);
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
		color: var(--color-ink-3);
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
		box-shadow: 0 12px 32px rgba(0, 0, 0, 0.28);
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
		color: var(--color-ink-3);
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
	.items {
		flex: 1;
		min-height: 0;
		overflow-y: auto;
		margin: 0;
		padding: 0;
		list-style: none;
	}
	.item {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.6rem;
		width: 100%;
		padding: 0.45rem 0.55rem;
		border-radius: 0.4rem;
		background: transparent;
		border: none;
		text-align: left;
		font-size: 0.8125rem;
		color: var(--color-ink-1);
		cursor: pointer;
		transition: background 0.12s, color 0.12s;
	}
	.item:hover {
		background: var(--color-surface-sunken);
		color: var(--color-ink-0);
	}
	.item.active {
		color: var(--color-accent);
	}
	.item-main {
		display: flex;
		flex-direction: column;
		gap: 0.05rem;
		min-width: 0;
	}
	.item-label {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.item-provider {
		font-size: 0.68rem;
		color: var(--color-ink-3);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.empty {
		padding: 0.5rem 0.55rem;
		font-size: 0.8125rem;
		color: var(--color-ink-3);
		list-style: none;
	}
</style>
