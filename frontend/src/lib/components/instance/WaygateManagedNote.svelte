<script lang="ts">
	import { Alert } from '$lib/components/ui';
	import { t } from '$lib/i18n/ns/instance';

	let { class: className = '' }: { class?: string } = $props();
</script>

<Alert tone="info" class={className}>
	<span data-testid="waygate-managed-note">{t('waygate.managedNote')}</span>
	<a href="/dashboard/network/waygate" class="ml-1 font-medium underline underline-offset-4">{t('waygate.openLink')}</a>
</Alert>
