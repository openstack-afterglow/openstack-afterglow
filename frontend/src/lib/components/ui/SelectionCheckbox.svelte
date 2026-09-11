<script lang="ts">
	interface Props {
		checked?: boolean;
		indeterminate?: boolean;
		ariaLabel: string;
		disabled?: boolean;
		unavailable?: boolean;
		title?: string;
		onclick?: (event: MouseEvent) => void;
		class?: string;
	}

	let {
		checked = false,
		indeterminate = false,
		ariaLabel,
		disabled = false,
		title,
		unavailable = false,
		onclick,
		class: className = '',
	}: Props = $props();

	function stopLabelClickPropagation(node: HTMLLabelElement) {
		const onClick = (event: MouseEvent) => {
			if (event.target instanceof HTMLInputElement) return;
			event.stopPropagation();
		};
		node.addEventListener('click', onClick);
		return {
			destroy() {
				node.removeEventListener('click', onClick);
			},
		};
	}

	function handleCheckboxClick(node: HTMLInputElement, callback: Props['onclick']) {
		let currentCallback = callback;
		const onClick = (event: MouseEvent) => {
			event.stopPropagation();
			currentCallback?.(event);
		};
		node.addEventListener('click', onClick);
		return {
			update(nextCallback: Props['onclick']) {
				currentCallback = nextCallback;
			},
			destroy() {
				node.removeEventListener('click', onClick);
			},
		};
	}

	let inputEl = $state<HTMLInputElement | null>(null);

	$effect(() => {
		if (inputEl) inputEl.indeterminate = indeterminate;
	});
</script>

<label
	class="selection-checkbox {className}"
	class:is-checked={checked}
	class:is-indeterminate={indeterminate}
	class:is-disabled={disabled}
	class:is-unavailable={unavailable}
	title={title}
	use:stopLabelClickPropagation
>
	<input
		bind:this={inputEl}
		type="checkbox"
		checked={checked}
		disabled={disabled}
		aria-label={ariaLabel}
		title={title}
		use:handleCheckboxClick={onclick}
	/>
	{#if unavailable}
		<span class="selection-unavailable" aria-hidden="true"></span>
	{:else}
		<span class="selection-box" aria-hidden="true">
			<svg class="selection-check" width="15" height="14" viewBox="0 0 15 14" fill="none">
				<path d="M2 8.36364L6.23077 12L13 2" />
			</svg>
			<span class="selection-minus"></span>
		</span>
	{/if}
</label>

<style>
	.selection-checkbox {
		position: relative;
		display: inline-grid;
		width: 22px;
		height: 22px;
		place-items: center;
		cursor: pointer;
		isolation: isolate;
	}

	.selection-checkbox input {
		position: absolute;
		inset: 0;
		z-index: 2;
		margin: 0;
		cursor: pointer;
		opacity: 0;
	}

	.selection-box {
		position: relative;
		display: grid;
		width: 18px;
		height: 18px;
		place-items: center;
		border: 2px solid color-mix(in oklab, var(--color-ink-3) 72%, transparent);
		border-radius: 5px;
		background: color-mix(in oklab, var(--color-surface-raised) 82%, transparent);
		box-shadow: inset 0 0 0 1px color-mix(in oklab, white 4%, transparent);
		transition:
			border-color var(--motion-duration-base) var(--motion-ease-standard),
			background var(--motion-duration-base) var(--motion-ease-standard),
			box-shadow var(--motion-duration-base) var(--motion-ease-standard),
			transform var(--motion-duration-base) var(--motion-ease-standard);
	}

	.selection-check {
		position: absolute;
		width: 13px;
		height: 12px;
		z-index: 1;
	}

	.selection-check path {
		stroke: var(--color-surface-base);
		stroke-width: 3;
		stroke-linecap: round;
		stroke-linejoin: round;
		stroke-dasharray: 19;
		stroke-dashoffset: 19;
		transition: stroke-dashoffset var(--motion-duration-base) var(--motion-ease-standard);
	}

	.selection-minus {
		width: 8px;
		height: 2px;
		border-radius: 999px;
		background: var(--color-surface-base);
		opacity: 0;
		transform: scaleX(0.4);
		transition:
			opacity var(--motion-duration-base) var(--motion-ease-standard),
			transform var(--motion-duration-base) var(--motion-ease-standard);
	}

	.selection-checkbox:hover .selection-box,
	.selection-checkbox input:focus-visible + .selection-box {
		border-color: var(--color-line-2);
		box-shadow: var(--focus-ring);
	}

	.selection-checkbox input:focus-visible + .selection-box {
		outline: none;
	}

	.selection-checkbox.is-checked .selection-box,
	.selection-checkbox.is-indeterminate .selection-box {
		border-color: var(--color-ink-0);
		background: var(--color-ink-0);
		box-shadow: none;
		animation: selection-pop var(--motion-duration-panel) var(--motion-ease-out);
	}

	.selection-checkbox.is-checked .selection-check path {
		stroke-dashoffset: 0;
	}

	.selection-checkbox.is-indeterminate .selection-minus {
		opacity: 1;
		transform: scaleX(1);
	}

	.selection-checkbox.is-indeterminate .selection-check path {
		stroke-dashoffset: 19;
		transition-delay: 0s;
	}

	.selection-checkbox.is-disabled {
		cursor: not-allowed;
	}

	.selection-unavailable {
		display: none;
		width: 18px;
		height: 18px;
		border: 1px solid color-mix(in oklab, var(--color-ink-3) 68%, transparent);
		border-radius: 50%;
		opacity: 0.7;
		position: relative;
	}

	.selection-unavailable::before,
	.selection-unavailable::after {
		content: '';
		position: absolute;
		top: 7px;
		left: 2px;
		width: 12px;
		height: 1px;
		background: var(--color-ink-3);
		transform: rotate(45deg);
	}

	.selection-unavailable::after {
		transform: rotate(-45deg);
	}

	.selection-checkbox.is-unavailable .selection-unavailable {
		display: block;
	}

	.selection-checkbox input:disabled {
		cursor: not-allowed;
	}

	@keyframes selection-pop {
		0% { transform: scale(0.88); }
		58% { transform: scale(1.08); }
		100% { transform: scale(1); }
	}

	@media (prefers-reduced-motion: reduce) {
		.selection-box,
		.selection-check path,
		.selection-minus {
			transition: none;
		}
		.selection-checkbox.is-checked .selection-box,
		.selection-checkbox.is-indeterminate .selection-box {
			animation: none;
		}
	}
</style>
