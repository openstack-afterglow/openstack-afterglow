<script lang="ts">
  let {
    enabled,
    loading,
    onClick,
  }: {
    enabled: boolean;
    loading: boolean;
    onClick: () => Promise<void>;
  } = $props();
</script>

{#if enabled}
  <div class="relative my-2">
    <div class="absolute inset-0 flex items-center"><div class="w-full border-t border-line-2"></div></div>
    <div class="relative flex justify-center text-xs"><span class="bg-surface-base px-2 text-ink-3">또는</span></div>
  </div>
  <button
    type="button"
    onclick={onClick}
    disabled={loading}
    class="w-full flex items-center justify-center gap-2 bg-[#FC6D26] hover:bg-[#E24329] disabled:bg-surface-selected disabled:text-ink-3 text-ink-0 font-medium rounded-lg py-2.5 text-sm transition-colors"
  >
    <svg class="w-5 h-5" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M22.65 14.39L12 22.13 1.35 14.39a.84.84 0 01-.3-.94l1.22-3.78 2.44-7.51A.42.42 0 014.93 2a.43.43 0 01.41.3l2.44 7.49h8.44l2.44-7.49a.42.42 0 01.41-.3.43.43 0 01.41.16l2.44 7.51L23 13.45a.84.84 0 01-.35.94z"/>
    </svg>
    {loading ? '리다이렉트 중...' : 'GitLab으로 로그인'}
  </button>
{/if}
