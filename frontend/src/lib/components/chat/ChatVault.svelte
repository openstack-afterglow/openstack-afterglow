<script lang="ts">
	import { get } from 'svelte/store';
	import { auth, authReady, projectSwitching } from '$lib/stores/auth';
	import { serviceCapabilities } from '$lib/stores/servicePermissions';
	import { chatDomainScope } from '$lib/stores/chatDomainScope';
	import { t } from '$lib/i18n/ns/chat-settings';
	import ChatVaultBrowser from './ChatVaultBrowser.svelte';
	import LumenPermissionNotice from './LumenPermissionNotice.svelte';

	const read = 'lumen-history_reader';
	const edit = 'lumen-history_editor';
	const canRead = $derived($authReady && !$projectSwitching && $serviceCapabilities(read));
	const canWrite = $derived(canRead && $serviceCapabilities(edit));
</script>

<section class="min-w-0 space-y-4">
	<header class="space-y-1">
		<h2 class="text-base font-semibold">{t('settings.sections.memory')}</h2>
		<p class="max-w-prose text-sm text-[var(--color-ink-2)]">{t('settings.vault.description')}</p>
	</header>
	{#if canRead}
		<LumenPermissionNotice leaves={[edit]} />
	{:else}
		<LumenPermissionNotice leaves={[read]} />
	{/if}
	{#if $chatDomainScope.key && $auth.token && $auth.projectId}
		{#key $chatDomainScope.revision}
			{@const owner = $chatDomainScope}
			<ChatVaultBrowser
				token={$auth.token}
				projectId={$auth.projectId}
				{canRead}
				{canWrite}
				isCurrent={() => owner === get(chatDomainScope)}
			/>
		{/key}
	{/if}
</section>
