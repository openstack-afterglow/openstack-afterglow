<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-identity';
	import Pill from '$lib/components/ui/Pill.svelte';
	import type { ManagedRole } from './types';
	import { isRetiredRole } from '$lib/utils/roleCatalog';
	let { role }: { role: ManagedRole } = $props();
</script>

<span class="inline-flex flex-wrap gap-1">
	{#if isRetiredRole(role)}<Pill tone="neutral" class="!text-xs">{t('roleBadges.retired')}</Pill>{/if}
	{#if role.protected}<Pill tone="neutral" class="!text-xs">{t('roleBadges.protected')}</Pill>{/if}
	{#if role.system_only}<Pill tone="admin-tone" class="!text-xs">{t('roleBadges.systemOnly')}</Pill>{/if}
</span>
