<script lang="ts">
	import { dialogState } from '$lib/stores/confirm.svelte';
	import { dialogFocus } from '$lib/utils/dialogFocus';
	import Button from './Button.svelte';
	import Card from './Card.svelte';
	import Field from './Field.svelte';
	import TextInput from './TextInput.svelte';
	import { t } from '$lib/i18n/ns/common';

	let requiredValue = $state('');
	const canConfirm = $derived(dialogState.requiredText === undefined || requiredValue === dialogState.requiredText);

	$effect(() => {
		// A new request can replace a closed dialog before the next render.
		dialogState.requestId;
		requiredValue = '';
	});

	function handleInputKeydown(event: KeyboardEvent) {
		if (event.key !== 'Enter' || event.isComposing || event.keyCode === 229) return;
		event.preventDefault();
		dialogState.accept(requiredValue);
	}
</script>

{#if dialogState.open}
	<div
		use:dialogFocus={{ enabled: dialogState.open, onEscape: dialogState.reject }}
		class="confirm-overlay material-scrim motion-fade"
		role="dialog"
		aria-modal="true"
		aria-labelledby="confirm-dialog-message"
		tabindex="-1"
	>
		<div class="confirm-frame motion-pop">
			<Card surface="modal" padding="lg">
				<p id="confirm-dialog-message" class="confirm-message">{dialogState.message}</p>
				{#if dialogState.requiredText !== undefined}
					<div class="confirm-required">
						<Field for="confirm-dialog-required-text" label={dialogState.requiredTextLabel ?? dialogState.requiredText} required>
							<TextInput
								id="confirm-dialog-required-text"
								bind:value={requiredValue}
								autocomplete="off"
								ariaDescribedBy="confirm-dialog-message"
								onkeydown={handleInputKeydown}
							/>
						</Field>
					</div>
				{/if}
				<div class="confirm-actions">
					<Button onclick={dialogState.reject} variant="secondary">{t('actions.cancel')}</Button>
					<Button onclick={() => dialogState.accept(requiredValue)} disabled={!canConfirm} variant={dialogState.confirmVariant}>{dialogState.confirmLabel ?? t('actions.confirm')}</Button>
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
	.confirm-required {
		margin-bottom: 1.5rem;
	}
	.confirm-actions {
		display: flex;
		justify-content: flex-end;
		gap: 0.75rem;
	}
</style>
