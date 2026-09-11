<script lang="ts">
	interface TabItem {
		value: string;
		label: string;
		panelId: string;
		disabled?: boolean;
		dataTour?: string;
	}

	interface Props {
		value: string;
		items: TabItem[];
		onchange: (value: string) => void;
		ariaLabel: string;
		id: string;
		class?: string;
	}

	let { value, items, onchange, ariaLabel, id, class: className = '' }: Props = $props();
	let tablistEl = $state<HTMLDivElement | null>(null);
	const tabElements = new Map<string, HTMLButtonElement>();
	let focusedValue = $state('');

	const enabledItems = $derived(items.filter((item) => !item.disabled));
	const rovingValue = $derived(
		enabledItems.some((item) => item.value === focusedValue)
			? focusedValue
			: enabledItems.find((item) => item.value === value)?.value ?? enabledItems[0]?.value ?? '',
	);

	function registerTab(node: HTMLButtonElement, tabValue: string) {
		tabElements.set(tabValue, node);
		return {
			update(nextValue: string) {
				if (nextValue === tabValue) return;
				tabElements.delete(tabValue);
				tabValue = nextValue;
				tabElements.set(tabValue, node);
			},
			destroy() {
				tabElements.delete(tabValue);
			},
		};
	}

	function focusTab(nextValue: string) {
		focusedValue = nextValue;
		queueMicrotask(() => tabElements.get(nextValue)?.focus());
	}

	function handleKeydown(event: KeyboardEvent, item: TabItem) {
		if (item.disabled) return;
		const currentIndex = enabledItems.findIndex((candidate) => candidate.value === item.value);
		if (currentIndex < 0) return;

		let nextIndex: number | null = null;
		if (event.key === 'ArrowRight') nextIndex = (currentIndex + 1) % enabledItems.length;
		else if (event.key === 'ArrowLeft') nextIndex = (currentIndex - 1 + enabledItems.length) % enabledItems.length;
		else if (event.key === 'Home') nextIndex = 0;
		else if (event.key === 'End') nextIndex = enabledItems.length - 1;
		else if (event.key === 'Enter' || event.key === ' ') {
			event.preventDefault();
			onchange(item.value);
			return;
		}
		if (nextIndex === null) return;
		event.preventDefault();
		focusTab(enabledItems[nextIndex].value);
	}

	function handleFocusOut(event: FocusEvent) {
		if (event.relatedTarget instanceof Node && tablistEl?.contains(event.relatedTarget)) return;
		focusedValue = '';
	}
</script>

<div
	bind:this={tablistEl}
	id={id}
	role="tablist"
	aria-label={ariaLabel}
	class="tabs {className}"
	onfocusout={handleFocusOut}
>
	{#each items as item (item.value)}
		<button
			type="button"
			id={`${id}-${item.value}`}
			use:registerTab={item.value}
			role="tab"
			data-tab-value={item.value}
			aria-controls={item.panelId}
			data-tour={item.dataTour}
			aria-selected={value === item.value}
			disabled={item.disabled}
			tabindex={rovingValue === item.value ? 0 : -1}
			onfocus={() => { focusedValue = item.value; }}
			onkeydown={(event) => handleKeydown(event, item)}
			onclick={() => {
				if (item.disabled) return;
				focusedValue = item.value;
				onchange(item.value);
			}}
		>
			{item.label}
		</button>
	{/each}
</div>

<style>
	.tabs {
		display: flex;
		align-items: center;
		gap: 0.25rem;
		overflow-x: auto;
		border-bottom: 1px solid var(--color-line);
		scrollbar-width: thin;
	}
	button {
		min-height: 2.5rem;
		margin-bottom: -1px;
		padding: 0.5rem 0.75rem;
		border-bottom: 2px solid transparent;
		color: var(--color-ink-2);
		font-size: 0.8125rem;
		font-weight: 500;
		white-space: nowrap;
		transition: color var(--motion-duration-fast) var(--motion-ease-standard), background var(--motion-duration-fast) var(--motion-ease-standard), border-color var(--motion-duration-fast) var(--motion-ease-standard);
	}
	button:hover:not(:disabled) {
		color: var(--color-ink-0);
		background: var(--color-surface-selected);
	}
	button[aria-selected='true'] {
		border-color: var(--color-action-warm);
		color: var(--color-ink-0);
	}
	button:focus-visible {
		position: relative;
		z-index: 1;
		border-radius: 0.375rem 0.375rem 0 0;
		outline: none;
		box-shadow: var(--focus-ring);
	}
	button:disabled {
		cursor: not-allowed;
		color: var(--color-ink-3);
		opacity: 0.55;
	}
	@media (pointer: coarse) {
		button { min-height: 2.75rem; }
	}
</style>
