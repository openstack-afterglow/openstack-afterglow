<script lang="ts">
	import { onMount, type Snippet } from 'svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import { t } from '$lib/i18n/ns/public-entry';
	import { createSceneMotion, type SceneMotionController, type SceneMotionState } from './sceneMotion';

	interface Props {
		kind: 'hero' | 'server' | 'gpu' | 'chat' | 'kubernetes' | 'onprem';
		label: string;
		replay?: boolean;
		class?: string;
		children: Snippet<[SceneMotionState]>;
	}

	let { kind, label, replay = true, class: className = '', children }: Props = $props();
	let element: HTMLDivElement;
	let motionState: SceneMotionState = $state('static');
	let generation = $state(0);
	let motion: SceneMotionController | undefined;
	let motionReady = $state(false);

	onMount(() => {
		motion = createSceneMotion(element, (next) => { motionState = next; });
		motionReady = typeof window.IntersectionObserver === 'function' && typeof window.matchMedia === 'function';
		return () => motion?.destroy();
	});

	function replayScene() {
		generation += 1;
		motion?.replay();
	}
</script>

<div class="landing-scene {className}" bind:this={element} data-scene={kind} data-motion={motionState}>
	<div class="scene-picture">
		{#key generation}{@render children(motionState)}{/key}
	</div>
	{#if replay && motionReady}
		<div class="scene-controls">
			<Button variant="ghost" size="sm" class="scene-replay" onclick={replayScene} ariaLabel={t('landing.story.motion.replayAria', { service: label })}>
				<span aria-hidden="true">↻</span>{t('landing.story.motion.replay')}
			</Button>
		</div>
	{/if}
</div>

<style>
	.landing-scene { min-width: 0; width: 100%; }
	.scene-picture { min-width: 0; }
	.scene-controls { display: flex; justify-content: flex-end; }
	.landing-scene :global(.scene-replay) { min-height: 2.75rem; color: var(--color-ink-2); }
	.landing-scene :global(.scene-replay span) { font-size: 1.25rem; }
	@media (prefers-reduced-motion: reduce) { .scene-controls { display: none; } }
</style>
