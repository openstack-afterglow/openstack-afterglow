<script lang="ts">
	import { t } from '$lib/i18n/ns/object-storage';
	import { t as tc } from '$lib/i18n/ns/common';
</script>

<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3.5" role="status" aria-busy="true" aria-label={tc('state.loadingNamed', { name: t('buckets.dashboardPage.title') })}>
	{#each Array(6) as _}
		<div class="motion-skeleton h-32 border border-line rounded-lg"></div>
	{/each}
</div>
