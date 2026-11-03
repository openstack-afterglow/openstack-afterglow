<script lang="ts">
	import type { DeliveryStatus, MailOperation } from '$lib/api/email';
	import { t } from '$lib/i18n/ns/admin-email';
	import { Alert } from '$lib/components/ui';
	let { operation }: { operation: MailOperation } = $props();
	const statuses: DeliveryStatus[] = ['pending', 'dispatching', 'accepted', 'failed', 'unknown', 'cancelled'];
</script>
<div class="space-y-2" data-email-operation={operation.operation_id} role="status">
	<p class="text-sm font-mono text-ink-1 [overflow-wrap:anywhere]">{t('operation', { id: operation.operation_id })}</p>
	<p class="text-sm text-ink-1">{t(`status.${operation.status}`)}</p>
	<p class="text-sm text-ink-1">{t('queued')}</p>
	{#if operation.audience_pending}
		<p class="text-sm text-ink-2" data-email-audience-pending>{t('audiencePending')}</p>
	{:else}
		<dl class="flex flex-wrap gap-x-4 gap-y-2 text-sm">
			{#each statuses as status}
				<div><dt class="text-ink-2">{t(`status.${status}`)}</dt><dd class="tabular-nums">{operation.counts[status]}</dd></div>
			{/each}
		</dl>
	{/if}
	<Alert tone="info">{t('proof')}</Alert>
	<a class="text-sm text-ink-1 underline" href="/admin/settings?tab=email">{t('history')}</a>
</div>
