<script lang="ts">
	import type { Snippet } from 'svelte';
	import AfterglowOrbit from '$lib/components/ui/AfterglowOrbit.svelte';
	import { t } from '$lib/i18n/ns/public-entry';

	/**
	 * The one Afterglow stage: the landing hero, the AuthStudioShell identity side and the console entry
	 * overlay render this same composition (signature and motion control above, wordmark and lead below,
	 * footer line), so a route scene changes only the stage width. Every part keeps its distance to the
	 * stage edge or centre, and route scenes name the parts (layout.css `--stage-vt-*`) so they travel with
	 * the edge instead of being redrawn.
	 */
	interface Props {
		wordmark: string;
		/** The landing wordmark is the page heading; elsewhere the page owns its own `h1`. */
		wordmarkTag?: 'h1' | 'p';
		wordmarkId?: string;
		lead: Snippet;
		/** Live status copy (console entry) announces itself. */
		captionRole?: 'status';
		/** The row under the lead. It keeps its height when empty, so the wordmark never moves between pages. */
		actions?: Snippet;
		motionToggle?: boolean;
		interactive?: boolean;
		[key: `data-${string}`]: string | undefined;
	}

	let { wordmark, wordmarkTag = 'p', wordmarkId, lead, captionRole, actions, motionToggle = true, interactive = true, ...rest }: Props = $props();
	let motion = $state(true);
</script>

<div class="entry-stage" {...rest}>
	<AfterglowOrbit active={motion} {interactive} />
	<div class="entry-stage-bar">
		<span class="entry-stage-signature" aria-hidden="true"><i></i>{t('landing.story.hero.signature')}</span>
		{#if motionToggle}
			<button type="button" class="entry-stage-motion" onclick={() => { motion = !motion; }}>
				{motion ? t('landing.story.hero.pauseMotion') : t('landing.story.hero.playMotion')}
			</button>
		{/if}
	</div>
	<div class="entry-stage-caption" role={captionRole} aria-live={captionRole ? 'polite' : undefined}>
		<svelte:element this={wordmarkTag} id={wordmarkId} class="entry-stage-wordmark">{wordmark.toLowerCase()}<span aria-hidden="true">.</span></svelte:element>
		<div class="entry-stage-lead">{@render lead()}</div>
		<div class="entry-stage-actions">{#if actions}{@render actions()}{/if}</div>
	</div>
	<div class="entry-stage-footer" aria-hidden="true">
		<span class="entry-stage-footer-start">{t('landing.story.hero.footerLabel')}</span>
		<span class="entry-stage-footer-end">{t('landing.story.hero.footerTagline')}</span>
	</div>
</div>

<style>
	/* Sizes come from the host (height or min-height); edges use viewport units so a half-width stage
	   keeps the same margins and type as the full-width one. */
	.entry-stage {
		position: relative;
		isolation: isolate;
		overflow: hidden;
		display: grid;
		height: 100%;
		min-height: inherit;
		box-sizing: border-box;
		background: var(--afterglow-artwork-base);
		color: var(--afterglow-artwork-ink);
		font-family: var(--font-sans);
	}
	.entry-stage-bar, .entry-stage-footer {
		position: absolute;
		left: clamp(1.25rem, 4vw, 4rem);
		right: clamp(1.25rem, 4vw, 4rem);
		display: flex; align-items: center; justify-content: space-between; gap: 1rem;
	}
	/* The bar keeps the motion control's height without it (overlay), so the signature never moves. */
	.entry-stage-bar { top: 1rem; min-height: 2.75rem; }
	.entry-stage-signature, .entry-stage-footer { font-family: var(--font-mono); color: var(--color-ink-2); }
	.entry-stage-signature {
		display: flex; align-items: center; gap: 0.75rem;
		font-size: var(--type-identifier); letter-spacing: 0.15em;
		view-transition-name: var(--stage-vt-signature, none);
	}
	.entry-stage-signature i { width: 0.75rem; height: 0.75rem; border: 1px solid var(--color-warm); border-radius: 50%; }
	.entry-stage-motion {
		min-height: 2.75rem; padding: 0.5rem 0.75rem; border: 1px solid transparent; border-radius: var(--radius-md);
		color: var(--color-ink-2); background: transparent; font: inherit; font-size: var(--type-identifier); cursor: pointer;
		view-transition-name: var(--stage-vt-motion, none);
	}
	.entry-stage-motion:hover { border-color: var(--color-line-2); color: var(--color-ink-0); }
	.entry-stage-motion:focus-visible { outline: none; box-shadow: var(--focus-ring); }
	.entry-stage-caption {
		position: relative;
		align-self: end;
		display: grid; justify-items: center;
		margin-bottom: clamp(5rem, 11svh, 8rem);
		padding: 0 1.25rem;
		text-align: center;
	}
	.entry-stage-wordmark {
		margin: 0;
		font-family: var(--font-mono); font-size: clamp(2.4rem, 4.5vw, 4.5rem); font-weight: 400;
		line-height: 1.1; letter-spacing: -0.04em; color: var(--color-ink-0);
		view-transition-name: var(--stage-vt-wordmark, none);
	}
	.entry-stage-wordmark span { color: var(--color-warm); }
	.entry-stage-lead {
		max-width: 36rem; margin-top: 1rem;
		color: var(--color-ink-1); font-size: 0.9375rem; line-height: 1.65;
		word-break: keep-all; overflow-wrap: anywhere; text-wrap: pretty;
		view-transition-name: var(--stage-vt-lead, none);
	}
	.entry-stage-lead:lang(ja), .entry-stage-lead:lang(zh-CN) { word-break: normal; }
	.entry-stage-lead :global(p) { margin: 0; }
	.entry-stage-actions {
		display: flex; flex-wrap: wrap; justify-content: center; gap: 0.5rem; min-height: 2.75rem; margin-top: 1.25rem;
		view-transition-name: var(--stage-vt-actions, none);
	}
	.entry-stage-actions :global(.btn) { min-height: 2.75rem; }
	.entry-stage-footer { bottom: 1.5rem; flex-wrap: wrap; font-size: 0.6875rem; }
	.entry-stage-footer-start { letter-spacing: 0.1em; view-transition-name: var(--stage-vt-footer-start, none); }
	.entry-stage-footer-end { view-transition-name: var(--stage-vt-footer-end, none); }
	@media (max-width: 767px) {
		.entry-stage-footer { justify-content: center; }
		.entry-stage-footer-start { display: none; }
	}
	@media (forced-colors: active) {
		.entry-stage { background: Canvas; color: CanvasText; }
	}
</style>
