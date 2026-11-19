<script lang="ts">
	import { auth, authReady, logoutInProgress, projectSwitching } from '$lib/stores/auth';
	import { personalWorkspace } from '$lib/stores/personalWorkspace';
	import { t } from '$lib/i18n/ns/chat-settings';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import WorkspaceChooserModal from '$lib/components/workspaces/WorkspaceChooserModal.svelte';

	/** `id` names the message so blocked send/run controls can reference it with aria-describedby. */
	let { id }: { id?: string } = $props();
	let open = $state(false);
	let createDomain = $state(false);
	const chooserDisabled = $derived($projectSwitching || !$authReady || $logoutInProgress || !$auth.token);
	function choose(create: boolean) {
		createDomain = create;
		open = true;
	}
</script>

{#if $personalWorkspace}
	<Alert tone="warning">
		<span {id}>{t('dashboardChat.personalUnavailable')}</span>
		{#snippet actions()}
			<Button variant="secondary" size="sm" disabled={chooserDisabled} onclick={() => choose(false)}>{t('dashboardChat.switchWorkspace')}</Button>
			{#if $auth.canCreateDomain}<Button size="sm" disabled={chooserDisabled} onclick={() => choose(true)}>{t('dashboardChat.createOrganization')}</Button>{/if}
		{/snippet}
	</Alert>
{/if}
{#if open}<WorkspaceChooserModal bind:open {createDomain} />{/if}
