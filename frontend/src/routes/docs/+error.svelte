<script lang="ts">
	import { page } from '$app/stores';
	import Button from '$lib/components/ui/Button.svelte';
	import EmptyState from '$lib/components/ui/EmptyState.svelte';
	import { siteConfig } from '$lib/config/site';
	import { docsHref, docsLocaleFromUrl, docsMessages } from '$lib/docs/locales';
	const locale = $derived(docsLocaleFromUrl($page.url));
	const messages = $derived(docsMessages[locale]);
	const title = $derived($page.status === 404 ? messages.notFound : messages.failed);
</script>

<svelte:head><title>{title} | {$siteConfig.site_name}</title></svelte:head>
<EmptyState headline={title} description={messages.errorRecovery}>
	{#snippet cta()}<Button href={docsHref(undefined, locale, $page.url)} class="min-h-11">{messages.goHome}</Button>{/snippet}
</EmptyState>
