<script lang="ts">
	import type { DomainAccountResult } from '$lib/types/auth';
	import { t } from '$lib/i18n/ns/domain-auth';
	let { result, admission }: { result: DomainAccountResult; admission?: { id: string; name: string } } = $props();
</script>

<dl class="space-y-3 text-sm [overflow-wrap:anywhere]">
	<div><dt class="text-ink-2">{t('select.identityDomain')}</dt><dd>{result.identity_domain_name}<code class="block text-xs">{result.identity_domain_id}</code><code class="block text-xs">{result.user_id}</code></dd></div>
	{#if result.personal_project_id}
		<div><dt class="text-ink-2">{t('onboarding.personalProject')}</dt><dd>{result.personal_project_name}<code class="block text-xs">{result.personal_project_id}</code></dd></div>
	{:else if result.personal_project_deferred}
		<div><dt class="text-ink-2">{t('onboarding.personalProject')}</dt><dd>{t('onboarding.personalDeferred')}</dd></div>
	{/if}
	{#if result.personal_domain_id}
		<div><dt class="text-ink-2">{t('onboarding.personalDomain')}</dt><dd><code class="text-xs">{result.personal_domain_id}</code></dd></div>
	{/if}
	{#if admission}
		<div><dt class="text-ink-2">{t('onboarding.joinedDomain')}</dt><dd>{admission.name}<code class="block text-xs">{admission.id}</code></dd></div>
	{/if}
</dl>
