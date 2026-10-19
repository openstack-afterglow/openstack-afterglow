<script lang="ts">
 import LoginBrandHeader from '$lib/components/auth/LoginBrandHeader.svelte';
 import AccountEmailRequest from '$lib/components/auth/AccountEmailRequest.svelte';
 import PageShell from '$lib/components/ui/PageShell.svelte';
 import Card from '$lib/components/ui/Card.svelte';
 import Button from '$lib/components/ui/Button.svelte';
 import LocaleSelect from '$lib/i18n/LocaleSelect.svelte';
 import { t } from '$lib/i18n/ns/domain-auth';
</script>
<svelte:head><meta name="referrer" content="no-referrer" /></svelte:head>
<main id="main-content" tabindex="-1" class="min-h-screen bg-surface-canvas py-8 flex items-center justify-center">
 <PageShell class="flex justify-center"><div class="w-full max-w-md space-y-6">
  <LocaleSelect id="recover-locale" variant="labelled" />
  <LoginBrandHeader />
  <Card class="p-5 sm:p-6 space-y-4">
   <h1 class="text-xl font-semibold text-ink-0">{t('recovery.title')}</h1>
   <AccountEmailRequest signup={false} />
   <Button variant="link" href="/login">{t('common.backToLogin')}</Button>
  </Card>
 </div></PageShell>
</main>
