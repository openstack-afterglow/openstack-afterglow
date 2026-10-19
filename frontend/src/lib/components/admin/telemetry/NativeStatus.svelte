<script lang="ts">
	import { Alert, StatusChip } from '$lib/components/ui';
	import type { TelemetryStatus } from '$lib/api/adminTelemetry';
	import { t } from '$lib/i18n/ns/admin-telemetry';
	let { status, error = null }: { status: TelemetryStatus; error?: string | null } = $props();
	const message = $derived(status === 'available' ? t('status.available') : status === 'partial' ? t('status.partial')
		: status === 'not_configured' ? t('status.notConfigured') : status === 'forbidden' ? t('status.forbidden')
		: status === 'not_found' ? t('status.notFound') : t('status.unavailable'));
</script>

{#if status === 'available'}
	<StatusChip status={message} />
{:else}
	<Alert tone={status === 'partial' ? 'warning' : status === 'unavailable' ? 'danger' : 'neutral'}>
		{message}
		{#if error}<span class="sr-only">{t('status.diagnosticAvailable')}</span>{/if}
	</Alert>
{/if}
