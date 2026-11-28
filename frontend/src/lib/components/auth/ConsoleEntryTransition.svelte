<script lang="ts">
	import EntryTopbar from '$lib/components/entry/EntryTopbar.svelte';
	import EntryStage from '$lib/components/entry/EntryStage.svelte';
	import { entryNavLinks } from '$lib/components/entry/entryNav';
	import { siteConfig } from '$lib/config/site';
	import { resolveLandingLogoPath } from '$lib/config/brandAssets';
	import { resolvedTheme } from '$lib/stores/theme';
	import { consoleEntry, finishConsoleEntry, markConsoleEntryEntered } from '$lib/stores/consoleEntry';
	import { t } from '$lib/i18n/ns/public-entry';

	let art = $state<HTMLDivElement | null>(null);
	const entry = $derived($consoleEntry);
	const site = $derived($siteConfig.site_name);
	const logo = $derived(resolveLandingLogoPath($siteConfig, $resolvedTheme));

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
			<!-- The login bar and stage, unchanged: the stage only widens to the full screen. -->
			<EntryTopbar siteName={site} logoPath={logo} links={entryNavLinks('/')} decorative scenePart="console" />
			<div class="console-entry__art" bind:this={art}>
				<EntryStage wordmark={site} captionRole="status" motionToggle={false} interactive={false} data-console-entry-part="art">
					{#snippet lead()}
						<p class="console-entry__copy console-entry__title">{entry.opened ? t('consoleEntry.ready') : t('consoleEntry.opening')}</p>
					{/snippet}
					{#snippet actions()}
						<ol class="console-entry__copy console-entry__steps">
							<li data-state="done">
								<span class="console-entry__mark" aria-hidden="true">[✓]</span>
								<span>{entry.method === 'sso' ? t('consoleEntry.step.sso') : t('consoleEntry.step.password')}</span>
							</li>
							<li data-state={entry.opened ? 'done' : 'active'}>
								<span class="console-entry__mark" aria-hidden="true">{entry.opened ? '[✓]' : '[ ~ ]'}</span>
								<span>{t('consoleEntry.step.workspace')}</span>
							</li>
						</ol>
					{/snippet}
				</EntryStage>
			</div>
		</div>
	{/key}
{/if}

<style>
	/* Decoration over real work: the login stage widens to the full screen under the same bar, the lead
	   states the actual handoff, and the whole layer fades away once the destination route is shown.
	   Transform/opacity only. */
	.console-entry {
		position: fixed;
		inset: 0;
		z-index: calc(var(--z-command) + 1);
		overflow: hidden;
		pointer-events: auto;
		background: var(--color-surface-canvas);
	}
	.console-entry :global(.entry-topbar) { position: absolute; }
	.console-entry__art {
		position: absolute;
		inset: var(--entry-nav-height) 0 0;
		animation: console-entry-art-in var(--motion-duration-scene) var(--motion-ease-emphasized) both;
	}
	/* A View Transition already widens the login stage into this layer. */
	.console-entry[data-scene][data-phase='entering'] .console-entry__art { animation: none; }
	.console-entry__copy {
		animation: console-entry-copy-in var(--motion-duration-panel) var(--motion-ease-emphasized) both;
		animation-delay: calc(var(--motion-duration-scene) * 0.55);
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
		from { opacity: 0; transform: translateY(0.5rem); }
		to { opacity: 1; transform: none; }
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
		.console-entry { background: Canvas; color: CanvasText; }
	}
</style>
