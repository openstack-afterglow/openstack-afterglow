<script lang="ts">
	import type { DocRoleHierarchy } from '$lib/docs/types';

	let { hierarchy, id }: { hierarchy: DocRoleHierarchy; id: string } = $props();
	const branched = $derived(hierarchy.levels.some((level) => level.alsoIncludes?.length));
</script>

{#snippet arrow()}
	<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M4 12h15m-5-5 5 5-5 5" /></svg>
{/snippet}

<figure class="role-hierarchy" {id} aria-labelledby={`${id}-title`} aria-describedby={`${id}-description`}>
	<figcaption>
		<h3 id={`${id}-title`}>{hierarchy.title}</h3>
		<p id={`${id}-description`}>{hierarchy.description}</p>
	</figcaption>
	<div class="relation-legend" aria-hidden="true">{@render arrow()}<span>{hierarchy.relation}</span></div>
	<div class="hierarchy-plot" aria-hidden="true">
		{#if branched}
			<div class="branched-chain">
				{#each hierarchy.levels as level, index (level.role)}
					<code class="role-node">{level.role}</code>
					<div class="branches">
						{#each level.alsoIncludes ?? [] as role (role)}
							<div class="branch"><span class="branch-connector">{@render arrow()}</span><code class="role-node">{role}</code></div>
						{/each}
					</div>
					{#if index < hierarchy.levels.length - 1}
						<span class="vertical-connector">{@render arrow()}</span><span></span>
					{/if}
				{/each}
			</div>
		{:else}
			<div class="grade-chain">
				{#each hierarchy.levels as level, index (level.role)}
					<code class="role-node">{level.role}</code>
					{#if index < hierarchy.levels.length - 1}<span class="chain-connector">{@render arrow()}</span>{/if}
				{/each}
			</div>
		{/if}
	</div>
	<ul class="sr-only">
		{#each hierarchy.levels as level, index (level.role)}
			{#if hierarchy.levels[index + 1]}
				<li>{level.role} {hierarchy.relation} {hierarchy.levels[index + 1].role}</li>
			{/if}
			{#each level.alsoIncludes ?? [] as role (role)}<li>{level.role} {hierarchy.relation} {role}</li>{/each}
		{/each}
	</ul>
</figure>

<style>
	.role-hierarchy { position: relative; min-width: 0; margin: 1.25rem 0; padding: 1rem; border: 1px solid var(--color-line); border-radius: var(--radius-lg); background: var(--color-surface-base); }
	h3 { margin: 0; color: var(--color-ink-0); font-size: var(--type-body); font-weight: 600; line-height: 1.5; }
	p { margin: 0.5rem 0 0; color: var(--color-ink-2); font-size: var(--type-support); line-height: 1.7; overflow-wrap: anywhere; }
	svg { display: block; width: 1.5rem; height: 1.5rem; flex: none; stroke: currentColor; stroke-width: 1.5; stroke-linecap: round; stroke-linejoin: round; }
	.relation-legend { display: flex; align-items: center; gap: 0.375rem; margin-top: 0.75rem; color: var(--color-ink-2); font-size: var(--type-support); }
	.hierarchy-plot { margin-block: 0.75rem 0.25rem; }
	.role-node { display: flex; justify-content: center; align-items: center; min-width: 0; padding: 0.625rem 0.5rem; border: 1px solid var(--color-line-2); border-radius: var(--radius-md); background: var(--color-surface-sunken); color: var(--color-ink-0); font-family: var(--font-mono); font-size: var(--type-support); font-weight: 500; line-height: 1.6; overflow-wrap: anywhere; text-align: center; }
	.grade-chain { display: flex; flex-direction: column; align-items: center; }
	.grade-chain .role-node { width: 100%; max-width: 18rem; }
	.chain-connector, .vertical-connector { display: flex; justify-content: center; align-items: center; flex: none; color: var(--color-ink-2); min-height: 1.75rem; }
	.chain-connector svg, .vertical-connector svg { transform: rotate(90deg); }
	.branched-chain { display: grid; grid-template-columns: minmax(0, 1.4fr) minmax(0, 1fr); max-width: 30rem; margin-inline: auto; align-items: center; }
	.branches { display: grid; gap: 0.5rem; min-width: 0; }
	.branch { display: flex; align-items: center; min-width: 0; }
	.branch .role-node { flex: 1; }
	.branch-connector { flex: none; color: var(--color-ink-2); }
	@media (min-width: 48rem) {
		.grade-chain { flex-direction: row; align-items: stretch; }
		.grade-chain .role-node { flex: 1; width: auto; max-width: none; }
		.chain-connector { width: 1.5rem; }
		.chain-connector svg { transform: none; }
	}
</style>
