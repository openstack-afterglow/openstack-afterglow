<script lang="ts">
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import ProjectResourceMonitor from '$lib/components/admin/projects/ProjectResourceMonitor.svelte';
	import { t } from '$lib/i18n/ns/admin-identity';

	function chooseKind(kind: string) {
		const url = new URL(page.url);
		url.searchParams.set('kind', kind);
		void goto(url, { keepFocus: true, noScroll: true });
	}
</script>

<svelte:head><title>{t('resourceMonitor.title')}</title></svelte:head>
<ProjectResourceMonitor projectId={page.params.id ?? ''} domainId={page.url.searchParams.get('domain_id') ?? ''}
	kind={page.url.searchParams.get('kind') ?? 'instances'} onKindChange={chooseKind} />
