<script lang="ts">
	import { toast } from '$lib/stores/toast';
	import { t } from '$lib/i18n/ns/common';
	import { enter, fadeMotion, reflow } from '$lib/utils/motion';
</script>

{#if $toast.length > 0}
<div
	class="fixed top-16 right-4 z-[var(--z-toast)] flex flex-col gap-2 w-80 pointer-events-none"
	role="region"
	aria-label={t('toast.region')}
>
	{#each $toast as item (item.id)}
		<div
			class="toast-item toast-{item.type} flex items-start gap-3 px-4 py-3 rounded-xl border text-sm shadow-[var(--shadow-overlay-compact)] pointer-events-auto"
			in:enter|global={{ x: 24, y: 0 }}
			out:fadeMotion|global
			animate:reflow
			role={item.type === 'error' ? 'alert' : 'status'}
			aria-live={item.type === 'error' ? 'assertive' : 'polite'}
			aria-atomic="true"
			onmouseenter={() => toast.pause(item.id, 'hover')}
			onmouseleave={() => toast.resume(item.id, 'hover')}
			onfocusin={() => toast.pause(item.id, 'focus')}
			onfocusout={() => toast.resume(item.id, 'focus')}
		>
			<span class="toast-icon motion-pop flex-shrink-0 font-bold text-base leading-none mt-0.5" aria-hidden="true">
				{#if item.type === 'success'}✓{:else if item.type === 'error'}✕{:else if item.type === 'warning'}⚠{:else}ℹ{/if}
			</span>
			<div class="flex-1 min-w-0">
				<span class="break-words">{item.message}</span>
				{#if item.action}
					<button
						onclick={() => { item.action!.onClick(); toast.remove(item.id); }}
						class="toast-action block mt-1 text-xs font-medium underline-offset-2 hover:underline"
					>{item.action.label}</button>
				{/if}
			</div>
			<button
				onclick={() => toast.remove(item.id)}
				class="flex-shrink-0 opacity-40 hover:opacity-80 transition-opacity text-lg leading-none mt-0.5"
				aria-label={t('toast.dismiss')}
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
