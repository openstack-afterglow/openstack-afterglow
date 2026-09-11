<script lang="ts">
  import type { EnvVar, PortMapping } from '$lib/types/zunContainer';

  interface CreatePayload {
    name: string;
    image: string;
    command: string;
    cpu: number;
    memory: string;
    environment: EnvVar[];
    ports: PortMapping[];
  }

  interface Props {
    open: boolean;
    creating: boolean;
    error: string;
    onCreate: (payload: CreatePayload) => Promise<boolean>;
  }
  let { open = $bindable(), creating, error, onCreate }: Props = $props();

  let form = $state({ name: '', image: '', command: '', cpu: 0.5, memory: '512' });
  let envVars = $state<EnvVar[]>([{ key: '', value: '' }]);
  let portMappings = $state<PortMapping[]>([{ container_port: 80, host_port: 0, protocol: 'tcp' }]);

  function addEnvVar() { envVars = [...envVars, { key: '', value: '' }]; }
  function removeEnvVar(i: number) { envVars = envVars.filter((_, idx) => idx !== i); }
  function addPort() { portMappings = [...portMappings, { container_port: 80, host_port: 0, protocol: 'tcp' }]; }
  function removePort(i: number) { portMappings = portMappings.filter((_, idx) => idx !== i); }

  function close() {
    open = false;
  }

  async function handleCreate() {
    const ok = await onCreate({
      name: form.name,
      image: form.image,
      command: form.command,
      cpu: form.cpu,
      memory: form.memory,
      environment: envVars,
      ports: portMappings,
    });
    if (ok) {
      form = { name: '', image: '', command: '', cpu: 0.5, memory: '512' };
      envVars = [{ key: '', value: '' }];
      portMappings = [{ container_port: 80, host_port: 0, protocol: 'tcp' }];
    }
  }
</script>

{#if open}
  <div class="fixed inset-0 bg-surface-scrim/60 flex items-center justify-center z-50" onclick={close} role="dialog" aria-modal="true" tabindex="-1" onkeydown={(e) => e.key === 'Escape' && close()}>
    <div class="bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-2xl mx-4 shadow-[var(--shadow-restraint)] max-h-[90vh] overflow-y-auto" onclick={(e) => e.stopPropagation()} role="none" onkeydown={(e) => e.stopPropagation()}>
      <h2 class="text-lg font-semibold text-ink-0 mb-5">컨테이너 생성</h2>
      <div class="space-y-4">
        <!-- 기본 설정 -->
        <div>
          <label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">이름
            <input bind:value={form.name} type="text" placeholder="my-container" class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1.5" />
          </label>
        </div>
        <div>
          <label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">이미지
            <input bind:value={form.image} type="text" placeholder="nginx:latest" class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm font-mono mt-1.5" />
          </label>
        </div>
        <div>
          <label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">명령 (선택)
            <input bind:value={form.command} type="text" placeholder="/bin/sh -c 'echo hello'" class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm font-mono mt-1.5" />
          </label>
        </div>
        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">CPU
              <input bind:value={form.cpu} type="number" step="0.1" min="0.1" class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1.5" />
            </label>
          </div>
          <div>
            <label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">메모리 (MB)
              <input bind:value={form.memory} type="text" placeholder="512" class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1.5" />
            </label>
          </div>
        </div>

        <!-- 환경 변수 -->
        <div>
          <div class="flex items-center justify-between mb-2">
            <span class="block text-xs text-ink-2 uppercase tracking-wide">환경 변수</span>
            <button type="button" onclick={addEnvVar} class="text-xs text-action-warm hover:text-action-warm-hover transition-colors">+ 추가</button>
          </div>
          <div class="space-y-2">
            {#each envVars as env, i (i)}
              <div class="flex gap-2 items-center">
                <input bind:value={env.key} type="text" placeholder="KEY" class="flex-1 bg-surface-sunken border border-line-2 rounded-lg px-3 py-1.5 text-ink-0 text-xs focus:outline-none focus:border-action-warm font-mono" />
                <span class="text-ink-3 text-xs">=</span>
                <input bind:value={env.value} type="text" placeholder="value" class="flex-1 bg-surface-sunken border border-line-2 rounded-lg px-3 py-1.5 text-ink-0 text-xs focus:outline-none focus:border-action-warm font-mono" />
                <button type="button" onclick={() => removeEnvVar(i)} class="text-ink-3 hover:text-red-400 transition-colors text-xs px-1">✕</button>
              </div>
            {/each}
          </div>
        </div>

        <!-- 포트 매핑 -->
        <div>
          <div class="flex items-center justify-between mb-2">
            <span class="block text-xs text-ink-2 uppercase tracking-wide">포트 매핑</span>
            <button type="button" onclick={addPort} class="text-xs text-action-warm hover:text-action-warm-hover transition-colors">+ 추가</button>
          </div>
          <div class="space-y-2">
            {#each portMappings as port, i (i)}
              <div class="flex gap-2 items-center">
                <div class="flex-1">
                  <input bind:value={port.container_port} type="number" min="1" max="65535" placeholder="컨테이너 포트" class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-1.5 text-ink-0 text-xs focus:outline-none focus:border-action-warm" />
                </div>
                <span class="text-ink-3 text-xs">→</span>
                <div class="flex-1">
                  <input bind:value={port.host_port} type="number" min="0" max="65535" placeholder="호스트 포트 (선택)" class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-1.5 text-ink-0 text-xs focus:outline-none focus:border-action-warm" />
                </div>
                <select bind:value={port.protocol} class="bg-surface-sunken border border-line-2 rounded-lg px-2 py-1.5 text-ink-0 text-xs focus:outline-none focus:border-action-warm">
                  <option value="tcp">TCP</option>
                  <option value="udp">UDP</option>
                </select>
                <button type="button" onclick={() => removePort(i)} class="text-ink-3 hover:text-red-400 transition-colors text-xs px-1">✕</button>
              </div>
            {/each}
          </div>
        </div>
      </div>
      {#if error}<div class="mt-3 text-red-400 text-xs">{error}</div>{/if}
      <div class="flex justify-end gap-3 mt-6">
        <button onclick={close} class="px-4 py-2 text-sm text-ink-2 hover:text-ink-0 transition-colors">취소</button>
        <button onclick={handleCreate} disabled={creating || !form.name || !form.image} class="px-5 py-2 bg-action-warm hover:bg-action-warm-hover disabled:bg-surface-selected disabled:text-ink-3 text-ink-0 text-sm font-medium rounded-lg transition-colors">{creating ? '생성 중...' : '생성'}</button>
      </div>
    </div>
  </div>
{/if}
