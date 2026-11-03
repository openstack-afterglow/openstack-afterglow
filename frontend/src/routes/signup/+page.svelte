<script lang="ts">
 import AuthStudioShell from '$lib/components/auth/AuthStudioShell.svelte';
 import AccountEmailRequest from '$lib/components/auth/AccountEmailRequest.svelte';
 import Button from '$lib/components/ui/Button.svelte';
 import { t } from '$lib/i18n/ns/domain-auth';
</script>
<svelte:head><meta name="referrer" content="no-referrer" /></svelte:head>
<AuthStudioShell variant="account" localeId="signup-locale" themeId="signup-theme" footerNote={t('login.signup.title')}>
 <div class="auth-flow">
  <header class="auth-flow-heading">
   <h1>{t('login.signup.title')}</h1>
  </header>
  <AccountEmailRequest signup={true} />
  <div class="auth-flow-links">
   <Button variant="link" href="/login">{t('common.backToLogin')}</Button>
  </div>
 </div>
</AuthStudioShell>
