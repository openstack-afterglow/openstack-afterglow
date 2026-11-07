<script lang="ts">
	import type { Snippet } from 'svelte';
	import { dialogFocus } from '$lib/utils/dialogFocus';
	import { t } from '$lib/i18n/ns/common';

	interface Props {
		open: boolean;
		title: string;
		subtitle?: string;
		onClose?: () => void;
		dismissible?: boolean;
		children: Snippet;
		footer?: Snippet;
	}

	let { open = $bindable(false), title, subtitle, onClose, dismissible = true, children, footer }: Props = $props();
	const componentId = $props.id();
	const titleId = `${componentId}-title`;

	function close() {
		if (!dismissible) return;
		open = false;
		onClose?.();
	}
</script>

{#if open}
	<div
		use:dialogFocus={{ enabled: open, onEscape: close }}
		class="fixed inset-0 z-[var(--z-modal)] flex justify-end"
		role="dialog"
		aria-modal="true"
		aria-labelledby={titleId}
		tabindex="-1"
	>
		<button
			type="button"
			class="material-scrim motion-fade absolute inset-0 cursor-default bg-surface-scrim"
			onclick={close}
			aria-label={t('dialog.close')}
			tabindex={dismissible ? 0 : -1}
			disabled={!dismissible}
			aria-hidden={!dismissible}
		></button>
		<aside class="motion-slide-left relative z-[1] flex h-full w-full max-w-3xl flex-col border-l border-line bg-surface-raised shadow-xl">
			<header class="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
				<div class="min-w-0">
					<h2 id={titleId} class="break-words text-lg font-semibold text-ink-0">{title}</h2>
					{#if subtitle}<p class="mt-1 break-all text-sm text-ink-2">{subtitle}</p>{/if}
				</div>
				<button type="button" class="min-h-11 min-w-11 rounded-md text-ink-2 hover:bg-surface-sunken" onclick={close} disabled={!dismissible} aria-label={t('dialog.close')}>
					<svg viewBox="0 0 24 24" class="mx-auto h-5 w-5" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
				</button>
			</header>
			<div class="min-h-0 flex-1 space-y-4 overflow-y-auto px-5 py-4">{@render children()}</div>
			{#if footer}<footer class="flex flex-wrap justify-end gap-2 border-t border-line px-5 py-3">{@render footer()}</footer>{/if}
		</aside>
	</div>
{/if}
