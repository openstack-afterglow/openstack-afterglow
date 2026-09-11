<script lang="ts">
  let {
    open = $bindable(),
    creating,
    error,
    onSubmit,
  }: {
    open: boolean;
    creating: boolean;
    error: string;
    onSubmit: (form: { type: string; name: string; description: string; dns_ip: string; server: string; domain: string; user: string; password: string }) => Promise<boolean>;
  } = $props();

  let form = $state({
    type: 'ldap' as 'ldap' | 'kerberos' | 'active_directory',
    name: '',
    description: '',
    dns_ip: '',
    server: '',
    domain: '',
    user: '',
    password: '',
  });

  $effect(() => {
    if (open) {
      form = { type: 'ldap', name: '', description: '', dns_ip: '', server: '', domain: '', user: '', password: '' };
    }
  });

  async function handleSubmit() {
    const ok = await onSubmit({ ...form });
    if (ok) open = false;
  }
</script>

{#if open}
  <div class="fixed inset-0 bg-surface-scrim/60 flex items-center justify-center z-50"
    onclick={() => { open = false; }}
    role="dialog" aria-modal="true" tabindex="-1"
    onkeydown={(e) => e.key === 'Escape' && (open = false)}>
    <div class="bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-lg mx-4 shadow-[var(--shadow-restraint)] max-h-[90vh] overflow-y-auto"
      onclick={(e) => e.stopPropagation()} role="none" onkeydown={(e) => e.stopPropagation()}>
      <h2 class="text-lg font-semibold text-ink-0 mb-5">Security Service 생성</h2>
      <div class="space-y-4">
        <div>
          <label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">유형 *
            <select bind:value={form.type}
              class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1.5">
              <option value="ldap">LDAP</option>
              <option value="kerberos">Kerberos</option>
              <option value="active_directory">Active Directory</option>
            </select>
          </label>
        </div>
        <div>
          <label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">이름 *
            <input bind:value={form.name} type="text" placeholder="my-security-service"
              class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1.5" />
          </label>
        </div>
        <div>
          <label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">설명 (선택)
            <input bind:value={form.description} type="text" placeholder="설명"
              class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1.5" />
          </label>
        </div>
        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">DNS IP
              <input bind:value={form.dns_ip} type="text" placeholder="192.168.1.10"
                class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1.5" />
            </label>
          </div>
          <div>
            <label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">서버 주소
              <input bind:value={form.server} type="text" placeholder="ldap.example.com"
                class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1.5" />
            </label>
          </div>
        </div>
        <div>
          <label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">도메인 (선택)
            <input bind:value={form.domain} type="text" placeholder="example.com"
              class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1.5" />
          </label>
        </div>
        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">사용자 (선택)
              <input bind:value={form.user} type="text" placeholder="bind user"
                class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1.5" />
            </label>
          </div>
          <div>
            <label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">비밀번호 (선택)
              <input bind:value={form.password} type="password" placeholder="••••••"
                class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1.5" />
            </label>
          </div>
        </div>
      </div>
      {#if error}
        <div class="mt-4 text-red-400 text-xs bg-red-900/20 border border-red-800 rounded px-3 py-2">{error}</div>
      {/if}
      <div class="flex justify-end gap-3 mt-6">
        <button onclick={() => { open = false; }}
          class="px-4 py-2 text-sm text-ink-2 hover:text-ink-0 transition-colors">취소</button>
        <button onclick={handleSubmit} disabled={creating || !form.name.trim()}
          class="px-5 py-2 bg-action-warm hover:bg-action-warm-hover disabled:bg-surface-selected disabled:text-ink-3 text-action-on-warm text-sm font-medium rounded-lg transition-colors">
          {creating ? '생성 중...' : '생성'}
        </button>
      </div>
    </div>
  </div>
{/if}
