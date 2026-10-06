<script lang="ts">
	import type { Snippet } from 'svelte';
	import { dialogFocus } from '$lib/utils/dialogFocus';
	import { t } from '$lib/i18n/ns/common';

	interface Props {
		open: boolean;
		onClose?: () => void;
		dismissible?: boolean;
		ariaLabel?: string;
		labelledBy?: string;
		children: Snippet;
	}

	let {
		open = $bindable(false),
		onClose,
		dismissible = true,
		ariaLabel,
		labelledBy,
		children,
	}: Props = $props();

	function close() {
		if (!dismissible) return;
		open = false;
		onClose?.();
	}
</script>

{#if open}
	<div
		use:dialogFocus={{ enabled: open, onEscape: close }}
		class="fixed inset-0 z-[var(--z-modal)] flex items-center justify-center p-4"
		role="dialog"
		aria-modal="true"
		aria-label={labelledBy ? undefined : ariaLabel}
		aria-labelledby={labelledBy}
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
		<div class="motion-pop relative z-[1] max-h-full max-w-full overflow-y-auto">
			{@render children()}
		</div>
	</div>
{/if}
