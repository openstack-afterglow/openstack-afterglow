<script lang="ts">
	import ChatBubble from '$lib/components/ui/ChatBubble.svelte';
	import { t } from '$lib/i18n/ns/public-entry';
	import LandingSolid from './LandingSolid.svelte';
	import type { SceneMotionState } from './sceneMotion';

	interface Props {
		state?: SceneMotionState;
	}

	let { state = 'static' }: Props = $props();
</script>

<section class="chat-demo" data-motion={state} aria-label={t('landing.story.chat.example')}>
	<header class="demo-header">
		<div class="demo-identity">
			<svg class="response-sculpture" viewBox="0 0 128 112" aria-hidden="true" focusable="false">
				{#each [3, 2, 1, 0] as layer}
					<LandingSolid x={25} y={52 + layer * 13} width={42} depth={34} height={9} tone="accent" {state} dx={layer % 2 ? 13 : -13} dy={-layer * 3} angle={(layer - 1.5) * 5} step={layer} />
				{/each}
			</svg>
			<div class="demo-title"><strong>Lumen</strong><span>{t('landing.story.chat.example')}</span></div>
		</div>
		<p>{t('landing.story.chat.exampleNote')}</p>
	</header>
	<ol class="conversation">
		<li class="message" style="--chat-step: 0">
			<ChatBubble align="end" label={t('landing.story.chat.researcher')} ariaLabel={t('landing.story.chat.researcher')}>
				<p>{t('landing.story.chat.question1')}</p>
			</ChatBubble>
		</li>
		<li class="message" style="--chat-step: 2">
			<ChatBubble align="start" label={t('landing.story.chat.assistant')} ariaLabel={t('landing.story.chat.assistant')}>
				<p class="chunk" style="--chat-step: 2">{t('landing.story.chat.answer1Lead')}</p>
				<p class="chunk" style="--chat-step: 3; --motion-index: 1">{t('landing.story.chat.answer1Detail')}</p>
			</ChatBubble>
		</li>
		<li class="message" style="--chat-step: 5">
			<ChatBubble align="end" label={t('landing.story.chat.researcher')} ariaLabel={t('landing.story.chat.researcher')}>
				<p>{t('landing.story.chat.question2')}</p>
			</ChatBubble>
		</li>
		<li class="message" style="--chat-step: 7">
			<ChatBubble align="start" label={t('landing.story.chat.assistant')} ariaLabel={t('landing.story.chat.assistant')}>
				<p class="chunk" style="--chat-step: 7">{t('landing.story.chat.answer2Lead')}</p>
				<p class="chunk" style="--chat-step: 8; --motion-index: 1">{t('landing.story.chat.answer2Detail')}</p>
			</ChatBubble>
		</li>
	</ol>
</section>

<style>
	.chat-demo {
		min-width: 0;
		border: 1px solid var(--color-line-2);
		border-radius: var(--radius-xl);
		background: var(--color-surface-canvas);
		color: var(--color-ink-0);
		font-size: 0.9375rem;
		line-height: 1.6;
		word-break: normal;
		overflow-wrap: anywhere;
	}

	.demo-header {
		padding: 1rem;
		border-bottom: 1px solid var(--color-line);
	}

	.demo-identity { display: flex; align-items: center; gap: 0.75rem; }
	.response-sculpture { flex: 0 0 3rem; width: 3rem; height: 2.625rem; }

	.demo-title {
		display: flex;
		flex-wrap: wrap;
		align-items: baseline;
		gap: 0.5rem 1rem;
	}

	.demo-title strong { font-family: var(--font-display); font-size: 1.125rem; font-weight: 500; }
	.demo-title span { color: var(--color-warm-text); font-size: 0.8125rem; }
	.demo-header p { margin-top: 0.25rem; color: var(--color-ink-2); font-size: 0.75rem; }
	p { margin: 0; }
	.chunk + .chunk { margin-top: 0.5rem; }

	.conversation {
		display: grid;
		gap: 0.75rem;
		margin: 0;
		padding: 1rem;
		list-style: none;
	}

	.message { min-width: 0; }
	.chat-demo :global(.chat-header) { font-size: 0.75rem; }
	.chat-demo :global(.chat-bubble) { box-sizing: border-box; max-width: 100%; }

	/* The complete transcript is the base frame. Both active states use the
	   same finite timeline; LandingScene owns pausing and keyed replay. */
	.chat-demo:is([data-motion='playing'], [data-motion='paused']) :is(.message, .chunk) {
		animation-duration: var(--motion-duration-data);
		animation-delay: calc(var(--motion-duration-data) * var(--chat-step) + var(--motion-duration-stagger) * var(--motion-index, 0));
		animation-timing-function: var(--motion-ease-emphasized);
		animation-iteration-count: 1;
		animation-fill-mode: backwards;
	}

	.chat-demo:is([data-motion='playing'], [data-motion='paused']) .message {
		animation-name: motion-enter;
		--motion-enter-offset: 0.75rem;
		--motion-enter-x: -0.75rem;
	}
	.chat-demo:is([data-motion='playing'], [data-motion='paused']) .message:nth-child(odd) { --motion-enter-x: 0.75rem; }

	.chat-demo:is([data-motion='playing'], [data-motion='paused']) .chunk { animation-name: motion-fade; }
	.chat-demo[data-motion='paused'] :is(.message, .chunk) { animation-play-state: paused; }

	@media (min-width: 768px) {
		.demo-header { padding: 1rem 1.5rem; }
		.conversation { padding: 1rem 1.5rem; }
		.chat-demo :global(.chat-bubble) { max-width: 86%; }
		.chat-demo :global(.chat-end .chat-bubble) { max-width: 78%; }
	}

	@media (prefers-reduced-motion: reduce) {
		.chat-demo:is([data-motion='playing'], [data-motion='paused']) :is(.message, .chunk) {
			animation: none;
			opacity: 1;
			transform: none;
		}
	}
</style>
