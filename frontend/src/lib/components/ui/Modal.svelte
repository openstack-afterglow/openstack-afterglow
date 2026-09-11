<script lang="ts">
	import type { Snippet } from 'svelte';
	import { dialogFocus } from '$lib/utils/dialogFocus';

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
			class="absolute inset-0 cursor-default bg-surface-scrim"
			onclick={close}
			aria-label="대화상자 닫기"
			tabindex={dismissible ? 0 : -1}
		></button>
		<div class="relative z-[1] max-h-full max-w-full">
			{@render children()}
		</div>
	</div>
{/if}
