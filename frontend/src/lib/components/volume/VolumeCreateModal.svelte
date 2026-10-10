<script lang="ts">
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import { apiMut } from '$lib/api/mutations';
	import { dialogFocus } from '$lib/utils/dialogFocus';
	import { t } from '$lib/i18n/ns/volume';
	import { ActivityIndicator, Alert, Button, ProgressTrack } from '$lib/components/ui';

	let {
		open = $bindable(false),
		onCreated,
	}: {
		open: boolean;
		onCreated: () => void;
	} = $props();

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	let form = $state({ name: '', size_gb: 10 });
	let creating = $state(false);
	let createError = $state('');

	async function createVolume() {
		if (!form.name.trim() || form.size_gb < 1) return;
		creating = true;
		createError = '';
		try {
			await apiMut(t('createModal.mutationLabel'), () => api.post('/api/v1/volumes', form, token, projectId));
			open = false;
			form = { name: '', size_gb: 10 };
			onCreated();
		} catch (e) {
			createError = e instanceof ApiError ? e.message : t('createModal.createFailed');
		} finally {
			creating = false;
		}
	}

	function close() {
		open = false;
		createError = '';
	}
</script>

{#if open}
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		use:dialogFocus={{ enabled: true, onEscape: () => close() }}
		class="motion-fade fixed inset-0 bg-surface-scrim/60 flex items-center justify-center z-50"
		onclick={close}
		role="dialog" aria-modal="true" tabindex="-1"
	>
		<div
			data-tour="volume-create-form"
			class="motion-pop bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-md mx-4 shadow-[var(--shadow-restraint)]"
			onclick={(e) => e.stopPropagation()}
			role="none"
		>
			<h2 class="text-lg font-semibold text-ink-0 mb-5">{t('createModal.title')}</h2>
			<div class="space-y-4">
				<div>
					<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">{t('createModal.nameLabel')}
						<input bind:value={form.name} type="text" placeholder={t('createModal.namePlaceholder')} class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1.5" />
					</label>
				</div>
				<div>
					<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">{t('createModal.sizeLabel')}
						<input bind:value={form.size_gb} type="number" min="1" class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1.5" />
					</label>
				</div>
			</div>
			{#if createError}
				<Alert tone="danger" class="mt-4">{createError}</Alert>
			{/if}
			{#if creating}<ProgressTrack value={null} active label={t('createModal.mutationLabel')} class="mt-4" />{/if}
			<div class="flex justify-end gap-3 mt-6">
				<button onclick={close} class="px-4 py-2 text-sm text-ink-2 hover:text-ink-0 transition-colors">{t('createModal.cancel')}</button>
				<Button
					dataTour="volume-create-submit"
					onclick={createVolume}
					disabled={creating || !form.name.trim() || form.size_gb < 1}
					ariaBusy={creating}
				>{#if creating}<ActivityIndicator size="xs" tone="ink" />{t('createModal.creating')}{:else}{t('createModal.create')}{/if}</Button>
			</div>
		</div>
	</div>
{/if}
