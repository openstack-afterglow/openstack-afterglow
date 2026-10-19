<script lang="ts">
	import DomainScope from '$lib/components/admin/domains/DomainScope.svelte';
	import AdminChatQuotasPage from '$lib/components/admin/chat/AdminChatQuotasPage.svelte';
</script>

<DomainScope>
	{#snippet children(domainId: string)}
		<AdminChatQuotasPage {domainId} />
	{/snippet}
</DomainScope>
