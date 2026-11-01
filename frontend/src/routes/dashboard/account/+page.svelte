<script lang="ts">
  import ProfileSection from '$lib/components/account/ProfileSection.svelte';
  import LoginPreferenceSection from '$lib/components/account/LoginPreferenceSection.svelte';
  import PasswordSection from '$lib/components/account/PasswordSection.svelte';
</script>

<div class="grid grid-cols-1 items-start gap-4 lg:grid-cols-2">
  <ProfileSection />
  <div class="space-y-4">
    <PasswordSection />
    <LoginPreferenceSection />
  </div>
</div>
