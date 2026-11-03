<script lang="ts">
 import AuthStudioShell from '$lib/components/auth/AuthStudioShell.svelte';
 import AccountEmailRequest from '$lib/components/auth/AccountEmailRequest.svelte';
 import Button from '$lib/components/ui/Button.svelte';
 import { t } from '$lib/i18n/ns/domain-auth';
</script>
<svelte:head><meta name="referrer" content="no-referrer" /></svelte:head>
<AuthStudioShell variant="account" localeId="recover-locale" themeId="recover-theme" footerNote={t('recovery.title')}>
 <div class="auth-flow">
  <header class="auth-flow-heading">
   <h1>{t('recovery.title')}</h1>
  </header>
  <AccountEmailRequest signup={false} />
  <div class="auth-flow-links">
   <Button variant="link" href="/login">{t('common.backToLogin')}</Button>
  </div>
 </div>
</AuthStudioShell>
