<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-system';
	import source from '$lib/i18n/messages/ko/admin-system.json';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import NotionTargetFormFields from './NotionTargetFormFields.svelte';
	import type { NotionTargetForm } from './NotionTargetFormFields.svelte';

	let {
		open = $bindable(false),
		onAdded,
	}: {
		open?: boolean;
		onAdded: () => void;
	} = $props();

	const defaultForm = (): NotionTargetForm => ({
		// Immutable backend data: always retain the Korean default, regardless of UI locale.
		label: source['notion.form.defaultLabel'],
		apiKey: '',
		databaseId: '',
		enabled: true,
		intervalMinutes: 30,
		usersDatabaseId: '',
		hypervisorsDatabaseId: '',
		gpuSpecDatabaseId: '',
	});

	let form = $state<NotionTargetForm>(defaultForm());
	let adding = $state(false);
	let addError = $state('');

	async function addTarget() {
		if (!form.apiKey) { addError = t('notion.validation.apiKeyRequired'); return; }
		if (!form.databaseId) { addError = t('notion.validation.databaseRequired'); return; }
		if (form.intervalMinutes < 1 || form.intervalMinutes > 1440) {
			addError = t('notion.validation.intervalRange'); return;
		}
		adding = true; addError = '';
		try {
			await api.post(
				'/api/v1/admin/notion/targets',
				{
					label: form.label,
					api_key: form.apiKey,
					database_id: form.databaseId,
					enabled: form.enabled,
					interval_minutes: form.intervalMinutes,
					users_database_id: form.usersDatabaseId,
					hypervisors_database_id: form.hypervisorsDatabaseId,
					gpu_spec_database_id: form.gpuSpecDatabaseId,
				},
				$auth.token ?? undefined,
				$auth.projectId ?? undefined
			);
			form = defaultForm();
			open = false;
			onAdded();
		} catch (e) {
			addError = e instanceof ApiError ? e.message : t('notion.add.failed');
		} finally {
			adding = false;
		}
	}
</script>

{#if open}
	<div class="motion-enter bg-surface-base border border-action-warm rounded-lg p-5 mb-6">
		<h2 class="text-sm font-semibold text-warm-text mb-4">{t('notion.add.title')}</h2>
		<NotionTargetFormFields {form} mode="add" />
		{#if addError}
			<div class="mt-3 text-red-400 text-sm">{addError}</div>
		{/if}
		<div class="mt-4">
			<button onclick={addTarget} disabled={adding}
				class="px-5 py-2 bg-action-warm hover:bg-action-warm-hover disabled:bg-surface-selected disabled:text-ink-3 text-action-on-warm text-sm font-medium rounded-lg transition-colors">
				{#if adding}<ActivityIndicator size="xs" tone="ink" class="mr-1.5" />{/if}{adding ? t('notion.add.adding') : t('notion.add.submit')}
			</button>
		</div>
	</div>
{/if}
