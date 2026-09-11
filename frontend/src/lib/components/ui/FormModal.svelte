<script lang="ts">
	import type { Snippet } from 'svelte';
	import Button from './Button.svelte';
	import Card from './Card.svelte';
	import Modal from './Modal.svelte';

	interface Props {
		open: boolean;
		title: string;
		onClose?: () => void;
		onSubmit?: () => void;
		submitLabel?: string;
		cancelLabel?: string;
		submitting?: boolean;
		children: Snippet;
		actions?: Snippet;
	}

	let {
		open = $bindable(false),
		title,
		onClose,
		onSubmit,
		submitLabel = '확인',
		cancelLabel = '취소',
		submitting = false,
		children,
		actions,
	}: Props = $props();
	const componentId = $props.id();
	const titleId = `${componentId}-title`;

	function close() {
		open = false;
		onClose?.();
	}
</script>

<Modal bind:open {onClose} dismissible={!submitting} labelledBy={titleId}>
	<div class="form-modal-frame">
		<Card surface="modal" padding="lg">
			<h2 id={titleId} class="form-modal-title">{title}</h2>
			{@render children()}
			<div class="form-modal-actions">
				{#if actions}
					{@render actions()}
				{:else}
					<Button onclick={close} variant="secondary" disabled={submitting}>{cancelLabel}</Button>
					{#if onSubmit}
						<Button onclick={onSubmit} disabled={submitting} variant="primary">{submitting ? '처리 중...' : submitLabel}</Button>
					{/if}
				{/if}
			</div>
		</Card>
	</div>
</Modal>

<style>
	.form-modal-frame {
		width: min(calc(100vw - 2rem), 28rem);
		max-height: calc(100dvh - 2rem);
		overflow-y: auto;
	}
	.form-modal-title {
		margin: 0 0 1.25rem;
		font-size: 1.125rem;
		font-weight: 600;
		color: var(--color-ink-0);
	}
	.form-modal-actions {
		display: flex;
		justify-content: flex-end;
		gap: 0.75rem;
		margin-top: 1.5rem;
	}
</style>
