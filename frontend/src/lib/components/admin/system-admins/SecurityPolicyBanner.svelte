<script lang="ts">
	import Alert from '$lib/components/ui/Alert.svelte';
	import { t } from '$lib/i18n/ns/admin-identity';
	import { t as domainT } from '$lib/i18n/ns/domain-admin';
	import RichText from '$lib/i18n/RichText.svelte';
	import type { AdminSecurityPolicy } from '$lib/types/adminSecurityPolicy';

	let { policy }: { policy: AdminSecurityPolicy } = $props();
</script>

{#snippet recoveryCommand(text: string)}<code class="break-words rounded bg-surface-sunken px-1">{text}</code>{/snippet}

{#if policy.system_admin_count === 0}
	<Alert tone="danger" class="mb-4" title={t('securityPolicy.lockoutTitle')}>
		<p>{domainT('securityPolicy.noAdmins')}</p>
		<p class="mt-1 text-xs"><RichText segments={t.rich('securityPolicy.recovery', { command: 'python3 scripts/manage_system_admins.py --os-system-scope grant <user-id>' })} tags={{ command: recoveryCommand }} /></p>
	</Alert>
{:else}
	<Alert tone="success" class="mb-4">
		{domainT('securityPolicy.authority', { count: policy.system_admin_count })}
	</Alert>
{/if}
