<script lang="ts" module>
	export type RichTagClasses = Partial<Record<'strong' | 'em' | 'code' | 'kbd', string>>;
</script>

<script lang="ts">
	import type { Snippet } from 'svelte';
	import RichText from './RichText.svelte';
	import { richPlainText, type RichSegment } from './rich';

	interface Props {
		/** Output of `t.rich(key, values)`. */
		segments: RichSegment[];
		/** Classes for built-in tags, e.g. `{ strong: 'text-ink-0' }`. */
		classes?: RichTagClasses;
		/** Custom tags such as `<docs>…</docs>`; each snippet receives the tag's inner text. */
		tags?: Record<string, Snippet<[string]>>;
	}

	let { segments, classes = {}, tags = {} }: Props = $props();
</script>

{#each segments as segment, index (index)}
	{#if segment.type === 'text'}{segment.value}{:else if segment.tag === 'br'}<br />{:else if tags[segment.tag]}{@render tags[segment.tag](richPlainText(segment.children))}{:else if segment.tag === 'strong' || segment.tag === 'b'}<strong class={classes.strong}><RichText segments={segment.children} {classes} {tags} /></strong>{:else if segment.tag === 'em' || segment.tag === 'i'}<em class={classes.em}><RichText segments={segment.children} {classes} {tags} /></em>{:else if segment.tag === 'code'}<code class={classes.code}><RichText segments={segment.children} {classes} {tags} /></code>{:else if segment.tag === 'kbd'}<kbd class={classes.kbd}><RichText segments={segment.children} {classes} {tags} /></kbd>{:else}<RichText segments={segment.children} {classes} {tags} />{/if}
{/each}
