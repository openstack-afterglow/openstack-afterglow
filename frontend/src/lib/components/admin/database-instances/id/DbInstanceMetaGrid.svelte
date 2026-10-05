<script lang="ts">
	import { t as tr } from '$lib/i18n/ns/database';
  import type { DbInstance } from '$lib/types/database';

  let { instance }: { instance: DbInstance } = $props();
</script>

<div class="bg-surface-base border border-line rounded-xl p-4 mb-4 grid grid-cols-2 gap-3 text-sm">
  <div><div class="text-ink-2 text-xs mb-0.5">ID</div><div class="text-ink-2 font-mono text-xs">{instance.id}</div></div>
  <div><div class="text-ink-2 text-xs mb-0.5">{tr('labels.datastore')}</div><div class="text-ink-0">{instance.datastore?.type ?? '-'} {instance.datastore?.version ?? ''}</div></div>
  <div><div class="text-ink-2 text-xs mb-0.5">{tr('labels.volumeSize')}</div><div class="text-ink-0">{instance.size} GB</div></div>
  <div><div class="text-ink-2 text-xs mb-0.5">{tr('labels.created')}</div><div class="text-ink-0">{instance.created_at ? instance.created_at.slice(0, 10) : '-'}</div></div>
</div>
