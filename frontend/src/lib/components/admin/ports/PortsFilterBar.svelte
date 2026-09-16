<script lang="ts">
  let {
    search = $bindable(),
    projectFilter = $bindable(),
    projectOptions,
    onProjectChange,
  }: {
    search: string;
    projectFilter: string;
    projectOptions: { id: string; name: string }[];
    onProjectChange: () => void;
  } = $props();
</script>

<div class="flex flex-wrap gap-3 mb-4">
  <input
    type="text"
    bind:value={search}
    placeholder="필터 (이름, device_owner, IP)"
    class="text-xs bg-surface-sunken border border-line-2 rounded px-3 py-1.5 text-ink-2 placeholder-ink-3 w-56"
  />
  <select
    bind:value={projectFilter}
    onchange={onProjectChange}
    class="text-xs bg-surface-sunken border border-line-2 rounded px-3 py-1.5 text-ink-2 focus:outline-none focus:border-action-warm"
  >
    <option value="">전체 프로젝트</option>
    {#each projectOptions as p (p.id)}
      <option value={p.id}>{p.name}</option>
    {/each}
  </select>
</div>
