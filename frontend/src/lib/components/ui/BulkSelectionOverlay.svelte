<script lang="ts" module>
	import { TONE_CSS_VAR, type DesignTone } from '$lib/design/tokens';

	export type BulkActionTone = Extract<DesignTone, 'success' | 'warning' | 'danger' | 'info' | 'neutral'>;
	export type BulkSelectionAction = {
		key: string;
		label: string;
		tone: BulkActionTone;
		onAction: () => void | Promise<void>;
		disabled?: boolean;
	};
</script>

<script lang="ts">
	interface Props {
		count: number;
		ariaLabel: string;
		actions: BulkSelectionAction[];
		busy?: boolean;
		onClear: () => void;
	}

	let { count, ariaLabel, actions, busy = false, onClear }: Props = $props();
</script>

{#if count > 0}
	<div class="bulk-overlay-wrap" role="region" aria-label={ariaLabel} aria-busy={busy}>
		<div class="bulk-overlay-panel">
			<div class="bulk-count" aria-live="polite"><strong>{count}</strong>개 선택됨</div>
			<div class="bulk-actions">
				{#each actions as action (action.key)}
					<button
						type="button"
						class="bulk-btn"
						style:--bulk-action-tone={TONE_CSS_VAR[action.tone]}
						disabled={busy || action.disabled}
						onclick={() => action.onAction()}
					>{action.label}</button>
				{/each}
				<button type="button" class="bulk-btn bulk-clear" disabled={busy} onclick={onClear}>취소</button>
			</div>
		</div>
	</div>
{/if}

<style>
	.bulk-overlay-wrap {
		position: fixed;
		left: 50%;
		bottom: max(1.25rem, env(safe-area-inset-bottom));
		z-index: var(--z-toast);
		width: min(760px, calc(100vw - 2rem));
		transform: translateX(-50%);
		pointer-events: none;
	}

	.bulk-overlay-panel {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		padding: 0.75rem 1rem;
		border: 1px solid var(--color-line-2);
		border-radius: 0.75rem;
		background: color-mix(in oklab, var(--color-surface-raised) 94%, transparent);
		box-shadow: 0 18px 48px color-mix(in oklab, var(--color-surface-canvas) 72%, transparent);
		backdrop-filter: blur(12px);
		pointer-events: auto;
		animation: bulk-rise var(--motion-duration-panel) var(--motion-ease-out);
	}

	.bulk-count {
		color: var(--color-ink-0);
		font-size: 0.875rem;
		font-weight: 600;
		letter-spacing: -0.01em;
		white-space: nowrap;
	}

	.bulk-count strong {
		font-size: 1.2em;
	}

	.bulk-actions {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		flex-wrap: wrap;
		justify-content: flex-end;
	}

	.bulk-btn {
		border: 1px solid color-mix(in oklab, var(--bulk-action-tone) 56%, var(--color-line));
		border-radius: 0.375rem;
		padding: 0.5rem 0.75rem;
		color: var(--color-ink-0);
		font-size: 0.8125rem;
		font-weight: 600;
		letter-spacing: -0.01em;
		cursor: pointer;
		transition:
			transform var(--motion-duration-fast) var(--motion-ease-standard),
			filter var(--motion-duration-fast) var(--motion-ease-standard),
			opacity var(--motion-duration-fast) var(--motion-ease-standard);
	}

	.bulk-btn:hover:not(:disabled) {
		transform: translateY(-1px);
		filter: brightness(1.08);
	}

	.bulk-btn:focus-visible {
		outline: none;
		box-shadow: var(--focus-ring);
	}

	.bulk-btn:disabled {
		cursor: wait;
		opacity: 0.55;
	}

	.bulk-btn {
		background: color-mix(in oklab, var(--bulk-action-tone) 22%, var(--color-surface-raised));
	}

	.bulk-clear {
		--bulk-action-tone: var(--color-state-neutral);
	}

	@keyframes bulk-rise {
		from {
			opacity: 0;
			transform: translateY(10px) scale(0.98);
		}
		to {
			opacity: 1;
			transform: translateY(0) scale(1);
		}
	}

	@media (max-width: 640px) {
		.bulk-overlay-panel {
			align-items: stretch;
			flex-direction: column;
		}

		.bulk-actions {
			justify-content: stretch;
		}

		.bulk-btn {
			flex: 1 1 calc(50% - 0.25rem);
		}
	}

	@media (prefers-reduced-motion: reduce) {
		.bulk-overlay-panel {
			animation: none;
		}
		.bulk-btn {
			transition: none;
		}
	}
</style>
