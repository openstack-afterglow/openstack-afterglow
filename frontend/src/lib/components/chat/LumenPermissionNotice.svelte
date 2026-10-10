<script lang="ts">
	import { projectPermissions, serviceCapabilities } from '$lib/stores/servicePermissions';
	import { permissionReason } from '$lib/api/lumenPermissions';
	import { t } from '$lib/i18n/ns/chat-settings';
	let { leaf }: { leaf: string } = $props();
</script>

{#if $projectPermissions.loading}
	<p class="text-sm text-[var(--color-ink-2)]" role="status">{t('permissions.loading')}</p>
{:else if $projectPermissions.error}
	<p class="text-sm text-[var(--color-state-danger)]" role="alert">{$projectPermissions.error}</p>
{:else if !$serviceCapabilities(leaf)}
	<p class="text-sm text-[var(--color-ink-2)]" role="status">{permissionReason(leaf)}</p>
{/if}
