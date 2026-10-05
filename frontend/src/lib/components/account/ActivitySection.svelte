<script lang="ts">
	import { t } from '$lib/i18n/ns/account';
	import ActivityLogTable from '$lib/components/admin/ActivityLogTable.svelte';
</script>

<div class="bg-surface-base border border-line rounded-lg p-5">
	<div class="text-ink-0 text-[15px] font-semibold mb-3">{t('activity.title')}</div>
	<ActivityLogTable endpoint="/api/v1/profile/activity" storageKey="account-activity" />
</div>
