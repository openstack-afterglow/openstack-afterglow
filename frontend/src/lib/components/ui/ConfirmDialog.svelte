<script lang="ts">
	import { dialogState } from '$lib/stores/confirm.svelte';
	import { dialogFocus } from '$lib/utils/dialogFocus';
	import Button from './Button.svelte';
	import Card from './Card.svelte';
</script>

{#if dialogState.open}
	<div
		use:dialogFocus={{ enabled: dialogState.open, onEscape: dialogState.reject }}
		class="confirm-overlay"
		role="dialog"
		aria-modal="true"
		aria-labelledby="confirm-dialog-message"
		tabindex="-1"
	>
		<div class="confirm-frame">
			<Card surface="modal" padding="lg">
				<p id="confirm-dialog-message" class="confirm-message">{dialogState.message}</p>
				<div class="confirm-actions">
					<Button onclick={dialogState.reject} variant="secondary">취소</Button>
					<Button onclick={dialogState.accept} variant="danger">확인</Button>
				</div>
			</Card>
		</div>
	</div>
{/if}

<style>
	.confirm-overlay {
		position: fixed;
		inset: 0;
		z-index: var(--z-confirmation);
		display: flex;
		align-items: center;
		justify-content: center;
		background: color-mix(in oklab, var(--color-surface-canvas) 72%, transparent);
	}
	.confirm-frame {
		width: min(calc(100vw - 2rem), 24rem);
		max-height: calc(100dvh - 2rem);
		overflow-y: auto;
	}
	.confirm-message {
		margin: 0 0 1.5rem;
		white-space: pre-wrap;
		font-size: 0.875rem;
		line-height: 1.5;
		color: var(--color-ink-1);
	}
	.confirm-actions {
		display: flex;
		justify-content: flex-end;
		gap: 0.75rem;
	}
</style>
