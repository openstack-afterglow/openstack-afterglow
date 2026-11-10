<script lang="ts">
	import { t } from '$lib/i18n/ns/vm-wizard';
	import { AfterglowOrbit, Alert, Button } from '$lib/components/ui';
	import type { AfterglowGeometry } from '$lib/components/ui/afterglowLoadingScene';

	type Task = { id: string; label: string; status: 'pending' | 'complete' | 'failed' };
	let { tasks, error, onRetry, retrying }: { tasks: Task[]; error: boolean; onRetry: () => void; retrying: boolean } = $props();
	const pending = $derived(tasks.filter(task => task.status === 'pending'));
	const failed = $derived(tasks.filter(task => task.status === 'failed'));
	// Advance only when the real dependency settles, not on a decorative animation timer.
	const active = $derived(pending[0] ?? null);
	let geometry = $state<AfterglowGeometry | null>(null);
</script>

<section data-testid="vm-resource-preparation" aria-labelledby="vm-preparation-title" aria-describedby="vm-preparation-help" class="preparation">
	<h2 id="vm-preparation-title" class="sr-only">{t('preparation.title')}</h2>
	<AfterglowOrbit active={pending.length > 0} interactive ongeometry={value => { geometry = value; }} />
	<div
		class="preparation-task" role="status" aria-live="polite" aria-atomic="true"
		style:--orbit-center-x={geometry ? `${geometry.centerX}px` : undefined}
		style:--orbit-center-y={geometry ? `${geometry.centerY}px` : undefined}
		style:--orbit-radius={geometry ? `${geometry.radius}px` : undefined}
	>
		{#if active}
			<span class="task-state">{t('preparation.waiting')}</span>
			<span class="task-label">{active.label}</span>
		{:else}
			<span class="task-label">{t(error ? 'preparation.failed' : 'preparation.complete')}</span>
		{/if}
	</div>
	<p id="vm-preparation-help" class="sr-only">{t('preparation.help')}</p>
	<ul class="sr-only" data-preparation-lanes aria-busy={pending.length > 0}>
		{#each tasks as task (task.id)}
			<li data-preparation-task={task.id} data-state={task.status}>
				{task.label}: {t(task.status === 'complete' ? 'preparation.complete' : task.status === 'failed' ? 'preparation.failed' : 'preparation.waiting')}
			</li>
		{/each}
	</ul>
	{#if error}
		<div class="preparation-error" role="region" aria-label={t('preparation.failed')} tabindex="0">
			<Alert tone="danger">
				{t('preparation.error')}
				<ul class="mt-2 space-y-1">
					{#each failed as task (task.id)}<li>{task.label} — {t('preparation.failed')}</li>{/each}
				</ul>
				{#snippet actions()}<Button variant="secondary" disabled={retrying} ariaBusy={retrying} onclick={onRetry}>{t('preparation.retry')}</Button>{/snippet}
			</Alert>
		</div>
	{/if}
</section>

<style>
	.preparation {
		position: relative;
		isolation: isolate;
		container-type: size;
		width: 100%;
		height: 100%;
		overflow: hidden;
		background: var(--afterglow-artwork-base);
		text-align: center;
	}
	.preparation-task {
		--orbit-radius: min(25cqw, 21.8cqh, 235px);
		position: absolute;
		top: var(--orbit-center-y, calc(53.9% - var(--orbit-radius)));
		left: var(--orbit-center-x, 50%);
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		width: calc(var(--orbit-radius) * 1.45);
		transform: translate(-50%, -50%);
	}
	.task-state {
		color: var(--afterglow-artwork-muted);
		font-size: var(--type-identifier);
	}
	.task-label {
		color: var(--afterglow-artwork-ink);
		font-size: var(--type-support);
		font-weight: 500;
		line-height: 1.5;
		text-wrap: balance;
		word-break: keep-all;
		overflow-wrap: anywhere;
	}
	:global(html:lang(ja)) .task-label,
	:global(html:lang(zh-CN)) .task-label { word-break: normal; }
	.preparation-error {
		position: absolute;
		inset-inline: 1rem;
		bottom: 1rem;
		max-height: 42%;
		overflow-y: auto;
		text-align: start;
		background: var(--afterglow-artwork-base);
	}
	.preparation-error:focus-visible {
		outline: 2px solid var(--color-line-2);
		outline-offset: 2px;
	}
	@media (forced-colors: active) {
		.preparation { background: Canvas; }
		.task-state, .task-label { color: CanvasText; }
	}
</style>
