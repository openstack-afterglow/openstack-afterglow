<script lang="ts">
	import { plateGraphics, type PlateName } from './plateGraphics';

	interface Props {
		name: PlateName;
		alt: string;
		/** cover (crop to fill) or contain (letterbox). Mirrors object-fit for the old <img>. */
		fit?: 'cover' | 'contain';
		class?: string;
	}

	let { name, alt, fit = 'cover', class: className = '' }: Props = $props();

	const markup = $derived(plateGraphics[name]);
</script>

<svg
	class={`plate-graphic ${className}`.trim()}
	data-plate={name}
	viewBox="0 0 1200 900"
	preserveAspectRatio={fit === 'contain' ? 'xMidYMid meet' : 'xMidYMid slice'}
	role="img"
	aria-label={alt}
>
	<!-- eslint-disable-next-line svelte/no-at-html-tags -- static, build-time-generated theme SVG markup (no user input) -->
	{@html markup}
</svg>

<style>
	.plate-graphic {
		display: block;
		width: 100%;
		height: 100%;
	}
	.plate-graphic :global(text) {
		font-family: var(--font-sans);
	}
	.plate-graphic :global(text[font-family='monospace']) {
		font-family: var(--font-mono);
	}
</style>
