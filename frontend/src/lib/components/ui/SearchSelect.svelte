<script module lang="ts">
	export interface SearchSelectOption {
		value: string;
		label: string;
		description?: string;
	}
</script>

<script lang="ts">
	import { tick } from 'svelte';

	interface Props {
		id: string;
		value?: string;
		options: SearchSelectOption[];
		placeholder?: string;
		searchPlaceholder?: string;
		emptyText?: string;
		loading?: boolean;
		disabled?: boolean;
		ariaLabel?: string;
		onchange: (value: string) => void;
	}

	let {
		id,
		value = '',
		options,
		placeholder = '선택하세요',
		searchPlaceholder = '검색...',
		emptyText = '일치하는 항목이 없습니다',
		loading = false,
		disabled = false,
		ariaLabel,
		onchange,
	}: Props = $props();

	let open = $state(false);
	let query = $state('');
	let activeIndex = $state(0);
	let container: HTMLDivElement | null = $state(null);
	let trigger: HTMLButtonElement | null = $state(null);
	let searchInput: HTMLInputElement | null = $state(null);
	let popover: HTMLDivElement | null = $state(null);
	let popoverStyle = $state('');
	const POPOVER_GAP = 4;
	const POPOVER_MAX_HEIGHT = 286;

	function portal(node: HTMLElement) {
		document.body.appendChild(node);
		return { destroy: () => node.remove() };
	}

	function positionPopover() {
		if (!trigger || !popover || typeof window === 'undefined') return;
		const rect = trigger.getBoundingClientRect();
		const viewportPadding = 16;
		const availableBelow = window.innerHeight - rect.bottom - viewportPadding - POPOVER_GAP;
		const availableAbove = rect.top - viewportPadding - POPOVER_GAP;
		const placeAbove = availableBelow < POPOVER_MAX_HEIGHT && availableAbove > availableBelow;
		const available = Math.max(96, placeAbove ? availableAbove : availableBelow);
		const height = Math.min(POPOVER_MAX_HEIGHT, available);
		const width = Math.min(Math.max(rect.width, 320), window.innerWidth - viewportPadding * 2);
		const left = Math.min(Math.max(viewportPadding, rect.left), window.innerWidth - viewportPadding - width);
		const top = placeAbove ? Math.max(viewportPadding, rect.top - POPOVER_GAP - height) : rect.bottom + POPOVER_GAP;
		popoverStyle = `left:${left}px;top:${top}px;width:${width}px;max-height:${height}px;`;
	}

	const listboxId = $derived(`${id}-options`);
	const selected = $derived(options.find((option) => option.value === value) ?? null);
	const filteredOptions = $derived.by(() => {
		const terms = query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
		if (terms.length === 0) return options;
		return options.filter((option) => {
			const haystack = `${option.label} ${option.description ?? ''}`.toLocaleLowerCase();
			return terms.every((term) => haystack.includes(term));
		});
	});
	const activeOption = $derived(filteredOptions[activeIndex] ?? null);

	function optionId(option: SearchSelectOption): string {
		return `${id}-option-${option.value.replace(/[^a-zA-Z0-9_-]/g, '-')}`;
	}

	async function openMenu() {
		if (disabled || loading) return;
		query = '';
		open = true;
		const selectedIndex = options.findIndex((option) => option.value === value);
		activeIndex = selectedIndex >= 0 ? selectedIndex : 0;
		await tick();
		positionPopover();
		searchInput?.focus();
	}

	function closeMenu(restoreFocus = false) {
		open = false;
		query = '';
		if (restoreFocus) trigger?.focus();
	}

	function choose(option: SearchSelectOption) {
		onchange(option.value);
		closeMenu(true);
	}

	function handleSearchInput(event: Event) {
		query = (event.currentTarget as HTMLInputElement).value;
		activeIndex = 0;
	}

	function handleSearchKeydown(event: KeyboardEvent) {
		if (event.key === 'Escape') {
			event.preventDefault();
			closeMenu(true);
			return;
		}
		if (filteredOptions.length === 0) return;
		if (event.key === 'ArrowDown') {
			event.preventDefault();
			activeIndex = (activeIndex + 1) % filteredOptions.length;
			return;
		}
		if (event.key === 'ArrowUp') {
			event.preventDefault();
			activeIndex = (activeIndex - 1 + filteredOptions.length) % filteredOptions.length;
			return;
		}
		if (event.key === 'Enter' && activeOption) {
			event.preventDefault();
			choose(activeOption);
		}
	}

	$effect(() => {
		if (!open || typeof document === 'undefined') return;
		const handlePointerDown = (event: PointerEvent) => {
			const target = event.target as Node;
			if (!container?.contains(target) && !popover?.contains(target)) closeMenu();
		};
		const handleViewportChange = () => positionPopover();
		document.addEventListener('pointerdown', handlePointerDown);
		window.addEventListener('resize', handleViewportChange);
		window.addEventListener('scroll', handleViewportChange, true);
		return () => {
			document.removeEventListener('pointerdown', handlePointerDown);
			window.removeEventListener('resize', handleViewportChange);
			window.removeEventListener('scroll', handleViewportChange, true);
		};
	});
</script>

<div class="search-select" bind:this={container}>
	<button
		bind:this={trigger}
		{id}
		type="button"
		class="search-select-trigger"
		disabled={disabled || loading}
		aria-label={ariaLabel}
		aria-haspopup="listbox"
		aria-expanded={open}
		aria-controls={open ? listboxId : undefined}
		onclick={() => (open ? closeMenu() : void openMenu())}
	>
		<span class:selected={selected}>{loading ? '불러오는 중...' : selected?.label ?? placeholder}</span>
		<span class="chevron" aria-hidden="true"></span>
	</button>

	{#if open}
		<div use:portal bind:this={popover} class="search-select-popover" style={popoverStyle}>
			<input
				bind:this={searchInput}
				type="search"
				class="search-select-input"
				value={query}
				placeholder={searchPlaceholder}
				role="combobox"
				aria-label={searchPlaceholder}
				aria-autocomplete="list"
				aria-controls={listboxId}
				aria-expanded="true"
				aria-activedescendant={activeOption ? optionId(activeOption) : undefined}
				oninput={handleSearchInput}
				onkeydown={handleSearchKeydown}
			/>
			<div id={listboxId} class="search-select-options" role="listbox" aria-label={ariaLabel ?? placeholder}>
				{#each filteredOptions as option, index (option.value)}
					<button
						id={optionId(option)}
						type="button"
						role="option"
						class="search-select-option"
						class:active={index === activeIndex}
						class:selected={option.value === value}
						aria-selected={option.value === value}
						onmouseenter={() => (activeIndex = index)}
						onclick={() => choose(option)}
					>
						<span>{option.label}</span>
						{#if option.description}<small>{option.description}</small>{/if}
					</button>
				{/each}
				{#if filteredOptions.length === 0}
					<p class="search-select-empty">{emptyText}</p>
				{/if}
			</div>
		</div>
	{/if}
</div>

<style>
	.search-select { position: relative; min-width: 0; }
	.search-select-trigger,
	.search-select-input {
		width: 100%;
		border: 1px solid var(--color-line-2);
		border-radius: 0.375rem;
		background: var(--color-surface-sunken);
		color: var(--color-ink-0);
		font-size: 0.875rem;
		line-height: 1.4;
	}
	.search-select-trigger {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.75rem;
		min-height: 2.375rem;
		padding: 0.5rem 0.75rem;
		text-align: left;
		transition: border-color var(--motion-duration-fast) var(--motion-ease-standard), box-shadow var(--motion-duration-fast) var(--motion-ease-standard), background var(--motion-duration-fast) var(--motion-ease-standard);
	}
	.search-select-trigger > span:first-child { min-width: 0; overflow: hidden; color: var(--color-ink-2); text-overflow: ellipsis; white-space: nowrap; }
	.search-select-trigger > span.selected { color: var(--color-ink-0); }
	.search-select-trigger:focus-visible,
	.search-select-input:focus-visible { outline: none; border-color: var(--color-line-2); box-shadow: var(--focus-ring); }
	.search-select-trigger:disabled { cursor: not-allowed; opacity: 0.55; }
	.chevron { width: 0.5rem; height: 0.5rem; flex: 0 0 auto; border-right: 1px solid currentColor; border-bottom: 1px solid currentColor; transform: translateY(-0.125rem) rotate(45deg); color: var(--color-ink-2); }
	.search-select-popover { position: fixed; z-index: var(--z-popover); display: grid; grid-template-rows: auto minmax(0, 1fr); overflow: hidden; border: 1px solid var(--color-line-2); border-radius: 0.5rem; background: var(--color-surface-raised); box-shadow: var(--shadow-restraint); }
	.search-select-input { border: 0; border-bottom: 1px solid var(--color-line); border-radius: 0; padding: 0.625rem 0.75rem; }
	.search-select-input::placeholder { color: var(--color-ink-3); }
	.search-select-options { min-height: 0; overflow-y: auto; }
	.search-select-option { display: grid; width: 100%; gap: 0.125rem; border: 0; border-bottom: 1px solid var(--color-line); background: transparent; padding: 0.625rem 0.75rem; color: var(--color-ink-1); text-align: left; }
	.search-select-option:last-child { border-bottom: 0; }
	.search-select-option:hover,
	.search-select-option.active,
	.search-select-option.selected { background: var(--color-surface-selected); color: var(--color-ink-0); }
	.search-select-option small { overflow: hidden; color: var(--color-ink-3); font-family: var(--font-mono); font-size: 0.6875rem; text-overflow: ellipsis; white-space: nowrap; }
	.search-select-empty { margin: 0; padding: 0.75rem; color: var(--color-ink-2); font-size: 0.8125rem; }
	@media (forced-colors: active) { .search-select-trigger:focus-visible, .search-select-input:focus-visible { outline: 2px solid CanvasText; outline-offset: 2px; } }
</style>
