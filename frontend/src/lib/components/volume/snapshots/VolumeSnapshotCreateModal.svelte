<script lang="ts">
  import type { Volume } from '$lib/types/volume';
  import { formatStorage } from '$lib/utils/format';

  let {
    open = $bindable(),
    volumes,
    onCreate,
  }: {
    open: boolean;
    volumes: Volume[];
    onCreate: (form: { volume_id: string; name: string; description: string; force: boolean }) => Promise<string | true>;
  } = $props();

  let form = $state({ volume_id: '', name: '', description: '', force: false });
  let creating = $state(false);
  let error = $state('');

  $effect(() => {
    if (!open) {
      form = { volume_id: '', name: '', description: '', force: false };
      error = '';
      creating = false;
    } else if (volumes.length > 0 && !form.volume_id) {
      form.volume_id = volumes[0].id;
    }
  });

  async function submit() {
    if (!form.volume_id || !form.name.trim()) return;
    creating = true;
    error = '';
    const result = await onCreate({ ...form });
    creating = false;
    if (result === true) open = false;
    else error = result;
  }
</script>

{#if open}
  <div class="fixed inset-0 bg-surface-scrim/60 flex items-center justify-center z-50" onclick={() => { open = false; error = ''; }} role="dialog" aria-modal="true" tabindex="-1" onkeydown={(e) => e.key === 'Escape' && (open = false)}>
    <div class="bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-md mx-4 shadow-[var(--shadow-restraint)]" onclick={(e) => e.stopPropagation()} role="none" onkeydown={(e) => e.stopPropagation()}>
      <h2 class="text-lg font-semibold text-ink-0 mb-5">볼륨 스냅샷 생성</h2>
      <div class="space-y-4">
        <div>
          <label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">볼륨 선택
            <select bind:value={form.volume_id} class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1.5">
              <option value="">볼륨을 선택하세요</option>
              {#each volumes as vol}
                <option value={vol.id}>{vol.name || vol.id.slice(0, 8)} ({formatStorage(vol.size)})</option>
              {/each}
            </select>
          </label>
        </div>
        <div>
          <label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">스냅샷 이름
            <input bind:value={form.name} type="text" placeholder="my-snapshot" class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1.5" />
          </label>
        </div>
        <div>
          <label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">설명 (선택)
            <input bind:value={form.description} type="text" class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1.5" />
          </label>
        </div>
        <div class="flex items-center gap-2">
          <input type="checkbox" id="force" bind:checked={form.force} class="rounded border-line-2" />
          <label for="force" class="text-sm text-ink-2">연결된 볼륨 강제 스냅샷 (force)</label>
        </div>
      </div>
      {#if error}<div class="mt-4 text-red-400 text-xs">{error}</div>{/if}
      <div class="flex justify-end gap-3 mt-6">
        <button onclick={() => { open = false; error = ''; }} class="px-4 py-2 text-sm text-ink-2 hover:text-ink-0 transition-colors">취소</button>
        <button onclick={submit} disabled={creating} class="px-5 py-2 bg-action-warm hover:bg-action-warm-hover disabled:bg-surface-selected disabled:text-ink-3 text-ink-0 text-sm font-medium rounded-lg transition-colors">{creating ? '생성 중...' : '생성'}</button>
      </div>
    </div>
  </div>
{/if}
