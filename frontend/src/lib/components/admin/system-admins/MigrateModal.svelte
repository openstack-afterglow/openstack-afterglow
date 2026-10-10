<script lang="ts">
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import { dialogFocus } from '$lib/utils/dialogFocus';
	import { t } from '$lib/i18n/ns/admin-identity';
	import RichText from '$lib/i18n/RichText.svelte';

	interface MigrateResult {
		migrated: number;
		skipped: number;
		errors: { user_id: string; reason: string }[];
	}

	let {
		adminProjectMemberCount,
		onClose,
		onMigrated,
	}: {
		adminProjectMemberCount: number;
		onClose: () => void;
		onMigrated: () => void;
	} = $props();

	let migrating = $state(false);
	let result = $state<MigrateResult | null>(null);
	let migrateError = $state('');

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	async function migrate() {
		migrating = true;
		migrateError = '';
		result = null;
		try {
			result = await api.post<MigrateResult>(
				'/api/v1/admin/identity/system-roles/migrate-from-project',
				{},
				token,
				projectId,
			);
			onMigrated();
		} catch (e) {
			migrateError = e instanceof ApiError ? e.message : t('migrate.failed');
		} finally {
			migrating = false;
		}
	}
</script>

{#snippet migratedCount(text: string)}<span class="text-green-400 font-semibold">{text}</span>{/snippet}
{#snippet skippedCount(text: string)}<span class="text-ink-2 font-semibold">{text}</span>{/snippet}

<!-- svelte-ignore a11y_click_events_have_key_events -->
<!-- svelte-ignore a11y_no_static_element_interactions -->
<div
	use:dialogFocus={{ enabled: true, onEscape: () => onClose() }}
	class="fixed inset-0 bg-surface-scrim/60 flex items-center justify-center z-50"
	onclick={(event) => { if (event.target === event.currentTarget) (onClose)(); }}
	role="dialog" aria-modal="true"
	tabindex="-1"
>
	<div
		class="bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-md mx-4 shadow-[var(--shadow-restraint)]"
	>
		<h2 class="text-lg font-semibold text-ink-0 mb-4">{t('migrate.title')}</h2>

		{#if result}
			<div class="mb-4 space-y-2">
				<div class="flex items-center gap-2 text-sm text-ink-2">
					<RichText segments={t.rich('migrate.migrated', { count: result.migrated })} tags={{ count: migratedCount }} />
				</div>
				<div class="flex items-center gap-2 text-sm text-ink-2">
					<RichText segments={t.rich('migrate.skipped', { count: result.skipped })} tags={{ count: skippedCount }} />
				</div>
				{#if result.errors.length > 0}
					<div class="mt-2 bg-red-900/30 border border-red-700 rounded-lg px-3 py-2 text-xs text-red-300">
						{t('migrate.errorCount', { count: result.errors.length })}
						{#each result.errors as e}
							<div class="mt-1">{e.user_id}: {e.reason}</div>
						{/each}
					</div>
				{/if}
			</div>
			<div class="flex justify-end">
				<button onclick={onClose} class="px-4 py-2 bg-surface-selected hover:bg-surface-selected text-ink-0 text-sm font-medium rounded-lg">
					{t('migrate.close')}
				</button>
			</div>
		{:else}
			{#if migrateError}
				<div class="mb-3 bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm">{migrateError}</div>
			{/if}
			<p class="text-sm text-ink-2 mb-5">
				<RichText segments={t.rich('migrate.description', { count: adminProjectMemberCount })} classes={{ strong: 'text-ink-0' }} />
			</p>
			<div class="flex justify-end gap-3">
				<button onclick={onClose} disabled={migrating} class="px-4 py-2 bg-surface-selected hover:bg-surface-selected text-ink-0 text-sm font-medium rounded-lg">
					{t('migrate.cancel')}
				</button>
				<button aria-busy={migrating}
					onclick={migrate}
					disabled={migrating}
					class="px-4 py-2 bg-action-warm hover:bg-action-warm-hover text-action-on-warm text-sm font-medium rounded-lg disabled:opacity-30"
				>
					{#if migrating}<span class="inline-flex items-center gap-2" role="status"><ActivityIndicator size="xs" />{t('migrate.migrating')}</span>{:else}{t('migrate.start')}{/if}
				</button>
			</div>
		{/if}
	</div>
</div>
