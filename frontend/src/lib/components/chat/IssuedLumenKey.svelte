<script lang="ts">
	import Button from '$lib/components/ui/Button.svelte';
	import FormModal from '$lib/components/ui/FormModal.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import { toast } from '$lib/stores/toast';
	import { t } from '$lib/i18n/ns/chat-settings';

	let { secret, close, canCopy }: { secret: string; close: () => void; canCopy: () => boolean } = $props();

	async function copy() {
		if (!canCopy()) return;
		try {
			await navigator.clipboard.writeText(secret);
			toast.success(t('apiKeys.toast.copied'));
		} catch {
			toast.error(t('apiKeys.toast.copyFailed'));
		}
	}
</script>

<FormModal open={true} title={t('apiKeys.issued.title')} onClose={close}>
	<Alert flat tone="warning">{t('apiKeys.issued.warning')}</Alert>
	<code class="mt-3 block break-all rounded bg-surface-sunken p-3 font-mono text-sm text-ink-1">{secret}</code>
	{#snippet actions()}
		<Button variant="secondary" onclick={copy}>{t('apiKeys.copy')}</Button>
		<Button onclick={close}>{t('apiKeys.done')}</Button>
	{/snippet}
</FormModal>
