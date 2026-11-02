<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-ops';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import type { Overview } from '$lib/types/adminOverview';
	let { overview }: { overview: Overview } = $props();
	const services = $derived([
		{ label: t('overview.services.containers'), href: '/admin/containers', value: overview.containers_count, disabled: overview.disabled_sections?.includes('containers') },
		{ label: t('overview.services.fileStorage'), href: '/admin/file-storage', value: overview.file_storage_count, disabled: overview.disabled_sections?.includes('file_storage') },
		{ label: t('overview.services.database'), href: '/admin/database-instances', value: overview.database_instances_count, disabled: overview.disabled_sections?.includes('database') },
		{ label: t('overview.services.objectStorage'), href: '/admin/object-storage', value: overview.object_storage_containers_count, disabled: overview.disabled_sections?.includes('object_storage'), unreadable: overview.object_storage_unreadable_accounts },
	]);
</script>

<div class="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-line bg-line lg:grid-cols-4">
	{#each services as service}
		<a href={service.href} class="flex min-w-0 flex-wrap items-baseline justify-between gap-2 bg-surface-base px-4 py-3 text-sm transition-colors hover:bg-surface-selected">
			<span class="text-ink-2">{service.label}</span>
			<span class="font-semibold tabular-nums text-ink-0">{service.disabled ? t('overview.availability.disabled') : service.value == null ? t('overview.availability.unknown') : service.value.toLocaleString(intlLocale())}</span>
			{#if !service.disabled && service.value != null && (service.unreadable ?? 0) > 0}
				<span class="w-full text-xs text-ink-2">{t('overview.services.unreadableAccounts', { count: service.unreadable!.toLocaleString(intlLocale()) })}</span>
			{/if}
		</a>
	{/each}
</div>
