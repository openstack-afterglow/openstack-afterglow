<script module lang="ts">
	import assets from '$lib/design/characterAssets.json';
	export type AssetGlyphVariant = keyof typeof assets;
</script>

<script lang="ts">
	/** Decorative only. The owner supplies actual localized status and recovery controls. */
	let { variant = 'empty' }: { variant?: AssetGlyphVariant } = $props();
</script>

<pre class="asset-glyph" aria-hidden="true">{(assets[variant] ?? assets.empty).art}</pre>

<style>
	.asset-glyph {
		margin: 0;
		max-width: 100%;
		overflow: hidden;
		font-family: var(--font-mono);
		font-size: var(--type-support);
		font-weight: 400;
		line-height: 1.2;
		white-space: pre;
		color: var(--afterglow-artwork-warm);
		user-select: none;
	}
	@media (forced-colors: active) { .asset-glyph { color: CanvasText; } }
</style>
