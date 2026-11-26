<script lang="ts">
	import AfterglowOrbit from '$lib/components/ui/AfterglowOrbit.svelte';
	import type { AfterglowGeometry } from '$lib/components/ui/afterglowLoadingScene';
	import { consoleEntry, finishConsoleEntry, markConsoleEntryEntered } from '$lib/stores/consoleEntry';
	import { t } from '$lib/i18n/ns/public-entry';

	let geometry = $state<AfterglowGeometry | null>(null);
	let art = $state<HTMLDivElement | null>(null);
	const entry = $derived($consoleEntry);

	// The auth panel's own exit is page CSS keyed on this root attribute (layout.css).
	$effect(() => {
		if (typeof document === 'undefined') return;
		const root = document.documentElement;
		if (entry.phase === 'idle') delete root.dataset.consoleEntry;
		else root.dataset.consoleEntry = entry.phase;
		return () => { delete root.dataset.consoleEntry; };
	});

	function animationEnded(event: AnimationEvent) {
		if (entry.phase === 'entering' && event.target === art) markConsoleEntryEntered(entry.id);
		else if (entry.phase === 'revealing' && event.target === event.currentTarget) finishConsoleEntry(entry.id);
	}
</script>

{#if entry.phase !== 'idle'}
	{#key entry.id}
		<div
			class="console-entry"
			data-phase={entry.phase}
			data-scene={entry.scene ? '' : undefined}
			data-testid="console-entry"
			style:--entry-origin-x={`${entry.origin.x}px`}
			style:--entry-origin-y={`${entry.origin.y}px`}
			onanimationend={animationEnded}
		>
			<div class="console-entry__art" bind:this={art} aria-hidden="true" data-console-entry-part="art">
				<AfterglowOrbit ongeometry={(value) => { geometry = value; }} />
			</div>
			<div
				class="console-entry__copy"
				data-console-entry-part="copy"
				role="status"
				aria-live="polite"
				style:--orbit-center-x={geometry ? `${geometry.centerX}px` : undefined}
				style:--orbit-center-y={geometry ? `${geometry.centerY}px` : undefined}
				style:--orbit-radius={geometry ? `${geometry.radius}px` : undefined}
			>
				<p class="console-entry__title">{entry.opened ? t('consoleEntry.ready') : t('consoleEntry.opening')}</p>
				<ol class="console-entry__steps">
					<li data-state="done">
						<span class="console-entry__mark" aria-hidden="true">[✓]</span>
						<span>{entry.method === 'sso' ? t('consoleEntry.step.sso') : t('consoleEntry.step.password')}</span>
					</li>
					<li data-state={entry.opened ? 'done' : 'active'}>
						<span class="console-entry__mark" aria-hidden="true">{entry.opened ? '[✓]' : '[ ~ ]'}</span>
						<span>{t('consoleEntry.step.workspace')}</span>
					</li>
				</ol>
			</div>
		</div>
	{/key}
{/if}

<style>
	/* Decoration over real work: the art grows from the auth identity side, the copy states the actual
	   handoff, and the whole layer fades away once the destination route is shown. Transform/opacity only. */
	.console-entry {
		position: fixed;
		inset: 0;
		z-index: calc(var(--z-command) + 1);
		overflow: hidden;
		pointer-events: auto;
		color: var(--afterglow-artwork-ink);
	}
	.console-entry__art {
		position: absolute;
		inset: 0;
		background: var(--afterglow-artwork-base);
		animation: console-entry-art-in var(--motion-duration-scene) var(--motion-ease-emphasized) both;
	}
	/* A View Transition already grows the login artwork into this layer. */
	.console-entry[data-scene][data-phase='entering'] .console-entry__art { animation: none; }
	.console-entry__copy {
		position: absolute;
		top: var(--orbit-center-y, 38%);
		left: var(--orbit-center-x, 50%);
		width: min(max(calc(var(--orbit-radius, 7rem) * 1.6), 15rem), calc(100vw - 2rem));
		transform: translate(-50%, -50%);
		text-align: center;
		animation: console-entry-copy-in var(--motion-duration-panel) var(--motion-ease-emphasized) both;
		animation-delay: calc(var(--motion-duration-scene) * 0.55);
		overflow-wrap: anywhere;
	}
	.console-entry__title {
		margin: 0 0 1rem;
		font-size: clamp(1.15rem, 2vw, 1.5rem);
		font-weight: 500;
		line-height: 1.35;
		letter-spacing: -0.04em;
		word-break: keep-all;
		text-wrap: balance;
	}
	.console-entry__steps {
		display: inline-grid;
		gap: 0.35rem;
		margin: 0;
		padding: 0;
		list-style: none;
		text-align: start;
		font-size: var(--type-support);
		color: var(--afterglow-artwork-muted);
	}
	.console-entry__steps li { display: flex; align-items: baseline; gap: 0.6rem; }
	.console-entry__steps li[data-state='done'] { color: var(--afterglow-artwork-ink); }
	.console-entry__mark { flex: none; min-width: 2.5rem; font-family: var(--font-mono); color: var(--afterglow-artwork-warm); white-space: pre; }

	/* Reveal: the status leaves first, then the picture opens onto the console. */
	.console-entry[data-phase='revealing'] {
		pointer-events: none;
		animation: console-entry-reveal var(--motion-duration-scene) var(--motion-ease-emphasized) var(--motion-duration-panel) forwards;
	}
	.console-entry[data-phase='revealing'] .console-entry__copy {
		animation: console-entry-copy-out var(--motion-duration-panel) var(--motion-ease-out) forwards;
	}
	.console-entry[data-phase='revealing'] .console-entry__art {
		animation: console-entry-art-out var(--motion-duration-scene) var(--motion-ease-emphasized) var(--motion-duration-panel) forwards;
	}

	@keyframes console-entry-art-in {
		from { opacity: 0; transform: translate(var(--entry-origin-x, 0), var(--entry-origin-y, 0)); }
		45% { opacity: 1; }
		to { opacity: 1; transform: none; }
	}
	@keyframes console-entry-copy-in {
		from { opacity: 0; transform: translate(-50%, calc(-50% + 0.5rem)); }
		to { opacity: 1; transform: translate(-50%, -50%); }
	}
	@keyframes console-entry-copy-out {
		from { opacity: 1; }
		to { opacity: 0; }
	}
	@keyframes console-entry-reveal {
		from { opacity: 1; }
		to { opacity: 0; }
	}
	@keyframes console-entry-art-out {
		from { transform: none; }
		to { transform: scale(1.08); }
	}
	@media (forced-colors: active) {
		.console-entry__art { background: Canvas; }
		.console-entry { color: CanvasText; }
	}
</style>
