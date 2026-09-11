<script lang="ts">
	import { toast } from '$lib/stores/toast';
</script>

{#if $toast.length > 0}
<div class="fixed top-16 right-4 z-[var(--z-toast)] flex flex-col gap-2 w-80 pointer-events-none">
	{#each $toast as t (t.id)}
		<div class="toast-item toast-{t.type} flex items-start gap-3 px-4 py-3 rounded-xl border text-sm shadow-[var(--shadow-restraint)] pointer-events-auto">
			<span class="toast-icon flex-shrink-0 font-bold text-base leading-none mt-0.5">
				{#if t.type === 'success'}✓{:else if t.type === 'error'}✕{:else if t.type === 'warning'}⚠{:else}ℹ{/if}
			</span>
			<div class="flex-1 min-w-0">
				<span class="break-words">{t.message}</span>
				{#if t.action}
					<button
						onclick={() => { t.action!.onClick(); toast.remove(t.id); }}
						class="toast-action block mt-1 text-xs font-medium underline-offset-2 hover:underline"
					>{t.action.label}</button>
				{/if}
			</div>
			<button
				onclick={() => toast.remove(t.id)}
				class="flex-shrink-0 opacity-40 hover:opacity-80 transition-opacity text-lg leading-none mt-0.5"
			>×</button>
		</div>
	{/each}
</div>
{/if}

<style>
	.toast-item {
		backdrop-filter: blur(12px);
	}
	.toast-success {
		background: color-mix(in oklab, var(--color-state-success) 12%, var(--color-surface-raised));
		border-color: color-mix(in oklab, var(--color-state-success) 30%, transparent);
		color: var(--color-ink-0);
	}
	.toast-error {
		background: color-mix(in oklab, var(--color-state-danger) 12%, var(--color-surface-raised));
		border-color: color-mix(in oklab, var(--color-state-danger) 30%, transparent);
		color: var(--color-ink-0);
	}
	.toast-warning {
		background: color-mix(in oklab, var(--color-state-warning) 12%, var(--color-surface-raised));
		border-color: color-mix(in oklab, var(--color-state-warning) 30%, transparent);
		color: var(--color-ink-0);
	}
	.toast-info {
		background: color-mix(in oklab, var(--color-state-info) 12%, var(--color-surface-raised));
		border-color: color-mix(in oklab, var(--color-state-info) 30%, transparent);
		color: var(--color-ink-0);
	}
	.toast-success .toast-icon { color: var(--color-state-success); }
	.toast-error   .toast-icon { color: var(--color-state-danger); }
	.toast-warning .toast-icon { color: var(--color-state-warning); }
	.toast-info    .toast-icon { color: var(--color-state-info); }

	.toast-action { color: var(--color-warm); }
	:root.light .toast-action { color: var(--color-warm-2); }
</style>
