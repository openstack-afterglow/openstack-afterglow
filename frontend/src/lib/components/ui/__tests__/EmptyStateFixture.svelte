<script lang="ts">
  import EmptyState from '../EmptyState.svelte';
</script>
<EmptyState headline="No resources" description="Create a resource to begin." icon="M2 2h20v20H2z">
  {#snippet cta()}<button type="button">Create resource</button>{/snippet}
</EmptyState>
