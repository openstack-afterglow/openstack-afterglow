<script lang="ts">
  import type { Snippet } from 'svelte';

  interface Props {
    class?: string;
    children: Snippet;
  }

  let { class: className = '', children }: Props = $props();
</script>

<div class="section-label {className}">
  {@render children()}
</div>

<style>
  .section-label {
    font-size: 0.6875rem;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-weight: 500;
    color: var(--color-ink-2);
  }
</style>
