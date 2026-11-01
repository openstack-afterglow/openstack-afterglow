<script lang="ts">
	import { onMount } from 'svelte';
	import { REDUCED_MOTION_QUERY } from '$lib/design/tokens';
	import { afterglowGeometry, createAfterglowScene, type AfterglowGeometry } from './afterglowLoadingScene';

	// `interactive`: a soft light follows the mouse (landing hero only; touch input ignored).
	let { active = true, interactive = false, ongeometry }: { active?: boolean; interactive?: boolean; ongeometry?: (geometry: AfterglowGeometry) => void } = $props();
	let host: HTMLSpanElement;
	let canvas: HTMLCanvasElement;
	let running = $state(false);
	let available = $state(false);
	let synchronize = $state<(() => void) | undefined>();

	$effect(() => { active; synchronize?.(); });

	onMount(() => {
		const scene = createAfterglowScene(canvas, host);
		available = scene !== null;
		const reducedMotion = matchMedia(REDUCED_MOTION_QUERY);
		let inView = true, disposed = false, frame = 0, last = 0, elapsed = 0;
		let width = 0, height = 0;
		const canRun = () => Boolean(scene && active && width && height && inView && !document.hidden && !reducedMotion.matches && !disposed);

		function tick(now: number) {
			frame = 0;
			if (!canRun()) return;
			if (!last) last = now;
			const delta = now - last;
			if (delta >= 1000 / 24) {
				elapsed += Math.min(delta, 80) / 1000;
				last = now;
				scene!.draw(elapsed);
			}
			frame = requestAnimationFrame(tick);
		}
		function sync() {
			cancelAnimationFrame(frame); frame = 0; last = 0;
			const shouldRun = canRun();
			running = shouldRun;
			if (shouldRun) frame = requestAnimationFrame(tick);
		}
		function resize() {
			const box = host.getBoundingClientRect();
			width = box.width; height = box.height;
			if (width > 0 && height > 0) {
				ongeometry?.(afterglowGeometry(width, height));
				scene?.resize(width, height);
				scene?.draw(elapsed);
			}
			sync();
		}
		const motionChange = () => { sync(); scene?.draw(elapsed); };
		const paletteObserver = new MutationObserver(() => {
			if (disposed) return;
			scene?.refreshPalette();
			scene?.draw(elapsed);
		});
		paletteObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['class', 'style'] });
		const resizeObserver = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(resize);
		resizeObserver?.observe(host);
		const intersectionObserver = typeof IntersectionObserver === 'undefined' ? null : new IntersectionObserver(entries => {
			inView = entries.some(entry => entry.isIntersecting);
			sync();
		});
		intersectionObserver?.observe(host);
		reducedMotion.addEventListener('change', motionChange);
		document.addEventListener('visibilitychange', sync);
		synchronize = sync;
		let pointerX = 0, pointerY = 0, strength = 0, target = 0, glowFrame = 0;
		function stepGlow() {
			glowFrame = 0;
			if (disposed || !scene) return;
			strength = reducedMotion.matches ? target : strength + (target - strength) * .3;
			if (Math.abs(target - strength) < .02) strength = target;
			scene.setPointer({ x: pointerX, y: pointerY, strength });
			if (!running) scene.draw(elapsed);
			if (strength !== target) glowFrame = requestAnimationFrame(stepGlow);
		}
		function pointerMove(event: PointerEvent) {
			if (event.pointerType === 'touch' || !inView || document.hidden) return;
			const box = host.getBoundingClientRect();
			pointerX = event.clientX - box.left; pointerY = event.clientY - box.top;
			target = pointerX >= 0 && pointerY >= 0 && pointerX <= box.width && pointerY <= box.height ? 1 : 0;
			// Outside the hero with the light already faded: nothing to repaint.
			if (target === 0 && strength === 0) return;
			if (!glowFrame) glowFrame = requestAnimationFrame(stepGlow);
		}
		function pointerLeave() { target = 0; if (!glowFrame) glowFrame = requestAnimationFrame(stepGlow); }
		if (interactive) {
			window.addEventListener('pointermove', pointerMove, { passive: true });
			document.documentElement.addEventListener('pointerleave', pointerLeave);
			window.addEventListener('blur', pointerLeave);
		}
		resize();
		return () => {
			disposed = true;
			cancelAnimationFrame(frame);
			cancelAnimationFrame(glowFrame);
			if (interactive) {
				window.removeEventListener('pointermove', pointerMove);
				document.documentElement.removeEventListener('pointerleave', pointerLeave);
				window.removeEventListener('blur', pointerLeave);
			}
			resizeObserver?.disconnect();
			intersectionObserver?.disconnect();
			paletteObserver.disconnect();
			reducedMotion.removeEventListener('change', motionChange);
			document.removeEventListener('visibilitychange', sync);
		};
	});
</script>

<span bind:this={host} class="afterglow-orbit" aria-hidden="true" data-running={running} data-renderer={available ? 'canvas' : 'fallback'}>
	<canvas bind:this={canvas} class="afterglow-orbit__scene" aria-hidden="true"></canvas>
</span>

<style>
	.afterglow-orbit {
		display: block;
		position: absolute;
		inset: 0;
		overflow: hidden;
		pointer-events: none;
		contain: paint;
		background: var(--afterglow-artwork-base);
	}
	.afterglow-orbit__scene { display: block; width: 100%; height: 100%; }
	@media (forced-colors: active) {
		.afterglow-orbit { background: Canvas; }
		.afterglow-orbit__scene { visibility: hidden; }
	}
</style>
