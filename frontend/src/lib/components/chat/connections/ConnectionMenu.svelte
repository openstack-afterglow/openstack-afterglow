<script lang="ts">
	import { tick } from 'svelte';
	let { label, items, primary = false, disabled = false }: {
		label: string; items: { label: string; run: () => void }[]; primary?: boolean; disabled?: boolean;
	} = $props();
	const id = $props.id();
	let open = $state(false);
	let group = $state<HTMLDivElement>();
	let trigger = $state<HTMLButtonElement>();
	let menu = $state<HTMLDivElement>();

	function close(restore = false) {
		open = false;
		if (restore) trigger?.focus();
	}

	async function show(last = false, enter = true) {
		if (disabled) return;
		open = true;
		await tick();
		if (!trigger || !menu || !open) return;
		if (typeof menu.showPopover === 'function') {
			menu.setAttribute('popover', 'manual');
			menu.showPopover();
		}
		const anchor = trigger.getBoundingClientRect();
		const box = menu.getBoundingClientRect();
		menu.style.left = `${Math.max(8, Math.min(anchor.right - box.width, window.innerWidth - box.width - 8))}px`;
		menu.style.top = `${anchor.bottom + box.height + 12 <= window.innerHeight ? anchor.bottom + 4 : Math.max(8, anchor.top - box.height - 4)}px`;
		menu.style.visibility = 'visible';
		if (!enter) return;
		const buttons = menu.querySelectorAll('button');
		buttons[last ? buttons.length - 1 : 0]?.focus();
	}

	function keyboard(event: KeyboardEvent) {
		if (event.key === 'Escape' && open) {
			event.preventDefault(); event.stopPropagation(); close(true); return;
		}
		if (event.key === 'Tab' && open) { close(true); return; }
		if (!['ArrowUp', 'ArrowDown', 'Home', 'End'].includes(event.key)) return;
		if (!open && (event.key === 'Home' || event.key === 'End')) return;
		event.preventDefault();
		if (!open) { void show(event.key === 'ArrowUp'); return; }
		const buttons = Array.from(menu?.querySelectorAll('button') ?? []);
		const current = buttons.indexOf(document.activeElement as HTMLButtonElement);
		const next = event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1
			: (current < 0 ? (event.key === 'ArrowUp' ? buttons.length - 1 : 0) : (current + (event.key === 'ArrowUp' ? -1 : 1) + buttons.length) % buttons.length);
		buttons[next]?.focus();
	}

	$effect(() => {
		if (!open) return;
		if (disabled) { close(); return; }
		const outside = (event: MouseEvent) => { if (event.target instanceof Node && !group?.contains(event.target)) close(); };
		const moved = (event: Event) => {
			if (event.target === menu) return;
			close(document.activeElement != null && !!menu?.contains(document.activeElement));
		};
		document.addEventListener('click', outside);
		window.addEventListener('scroll', moved, true);
		window.addEventListener('resize', moved);
		return () => {
			document.removeEventListener('click', outside);
			window.removeEventListener('scroll', moved, true);
			window.removeEventListener('resize', moved);
		};
	});
</script>

<!-- svelte-ignore a11y_no_noninteractive_element_interactions: the presentation wrapper delegates keys to its button and menu items -->
<div class="menu-group" role="presentation" bind:this={group} onkeydown={keyboard}
	onfocusout={(event) => { if (event.relatedTarget instanceof Node && !group?.contains(event.relatedTarget)) close(); }}>
	<button class="trigger" class:primary type="button" bind:this={trigger} {disabled}
		aria-haspopup="menu" aria-expanded={open} aria-controls={open ? id : undefined}
		onclick={(event) => open ? close() : void show(false, event.detail === 0)}>
		{#if primary}<svg aria-hidden="true" viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M8 3v10M3 8h10"/></svg>{/if}
		{label}
		<svg aria-hidden="true" viewBox="0 0 16 16" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.5"><path d="m4 6 4 4 4-4"/></svg>
	</button>
	{#if open}
		<div {id} role="menu" aria-label={label} class="commands" bind:this={menu}>
			{#each items as item (item.label)}
				<button type="button" role="menuitem" tabindex="-1" onclick={() => { close(true); item.run(); }}>{item.label}</button>
			{/each}
		</div>
	{/if}
</div>

<style>
	.menu-group { display: inline-flex; min-inline-size: 0; }
	.trigger { display: inline-flex; align-items: center; justify-content: center; gap: 0.375rem; min-block-size: var(--control-height); padding: 0.375rem 0.625rem; border: 1px solid var(--color-line); border-radius: var(--radius-md); color: var(--color-ink-1); font-size: var(--type-support); font-weight: 500; line-height: 1.2; white-space: nowrap; }
	.trigger:hover:not(:disabled), .trigger[aria-expanded='true'] { background: var(--color-surface-sunken); color: var(--color-ink-0); }
	.trigger.primary { border-color: transparent; background: var(--color-warm); color: var(--color-action-on-warm); }
	.trigger.primary:hover:not(:disabled), .trigger.primary[aria-expanded='true'] { background: color-mix(in oklab, var(--color-warm) 88%, var(--color-ink-0)); }
	.trigger:disabled { opacity: 0.45; cursor: not-allowed; }
	.trigger:focus-visible { outline: 2px solid var(--color-accent); outline-offset: 2px; }
	.commands { position: fixed; inset: 0 auto auto 0; margin: 0; z-index: var(--z-popover); visibility: hidden; min-inline-size: 10rem; max-inline-size: calc(100vw - 1rem); max-block-size: calc(100dvh - 1rem); overflow: auto; padding: 0.25rem; border: 1px solid var(--color-line-2); border-radius: var(--radius-lg); background: var(--color-surface-raised); box-shadow: var(--shadow-popover); }
	.commands button { display: block; inline-size: 100%; min-block-size: var(--control-height); padding: 0.375rem 0.625rem; border-radius: var(--radius-md); text-align: start; font-size: var(--type-support); color: var(--color-ink-0); }
	.commands button:hover, .commands button:focus-visible { background: var(--color-surface-selected); }
	.commands button:focus-visible { outline: 2px solid var(--color-accent); outline-offset: -2px; }
	@media (max-width: 767px), (pointer: coarse) { .trigger, .commands button { min-block-size: var(--control-touch-height); } }
</style>
