<script lang="ts">
  import PageHeader from '$lib/components/ui/PageHeader.svelte';
  import ProfileSection from '$lib/components/account/ProfileSection.svelte';
  import PasswordSection from '$lib/components/account/PasswordSection.svelte';
  import KeypairsSection from '$lib/components/account/KeypairsSection.svelte';
  import ActivitySection from '$lib/components/account/ActivitySection.svelte';
  import SecuritySection from '$lib/components/account/SecuritySection.svelte';
  import BetaFeaturesSection from '$lib/components/account/BetaFeaturesSection.svelte';
  import McpAccessSection from '$lib/components/account/McpAccessSection.svelte';
</script>

<div class="p-4 md:p-6 max-w-5xl">
  <div class="flex items-center gap-3 mb-4">
    <a
      href="/dashboard"
      class="inline-flex items-center gap-1.5 text-xs text-ink-2 hover:text-ink-0 transition-colors px-2.5 py-1.5 rounded-md hover:bg-surface-sunken"
    >
      <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7"></path></svg>
      대시보드로 돌아가기
    </a>
    <span class="text-ink-3">·</span>
    <a
      href="/dashboard/my-resources"
      class="inline-flex items-center gap-1.5 text-xs text-action-warm hover:text-action-warm-hover transition-colors px-2.5 py-1.5 rounded-md hover:bg-action-warm-hover/10"
    >
      내 리소스
      <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"></path></svg>
    </a>
  </div>

  <PageHeader breadcrumb="" title="계정 설정" />
  <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
    <ProfileSection />
    <PasswordSection />
    <SecuritySection />
    <div class="lg:col-span-2">
      <BetaFeaturesSection />
    </div>
    <div class="lg:col-span-2">
      <KeypairsSection />
    </div>
    <div class="lg:col-span-2">
      <McpAccessSection />
    </div>
    <div class="lg:col-span-2">
      <ActivitySection />
    </div>
  </div>
</div>
