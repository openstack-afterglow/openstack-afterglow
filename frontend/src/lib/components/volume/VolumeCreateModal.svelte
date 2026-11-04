<script lang="ts">
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import { apiMut } from '$lib/api/mutations';
	import { dialogFocus } from '$lib/utils/dialogFocus';
	import { t } from '$lib/i18n/ns/volume';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import { Alert, Button } from '$lib/components/ui';
	import { onDestroy } from 'svelte';
	import { resolveExperienceMessage } from '$lib/i18n/runtime.svelte';
	import { unavailableExperienceMessage } from '$lib/i18n/experienceMessages';
	import {
		beginExperienceAction, experienceApplied, experienceDiscarded, experienceMessage,
		experienceState, recordExperience, type ExperienceContext,
	} from '$lib/utils/experience';

	let {
		open = $bindable(false),
		onCreated,
	}: {
		open: boolean;
		onCreated: (context?: ExperienceContext, createdVolumeId?: string) => void | Promise<void>;
	} = $props();

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	let form = $state({ name: '', size_gb: 10 });
	let creating = $state(false);
	let createError = $state('');

	let activeContext: ExperienceContext | undefined;
	let modalRevision = 0;
	let destroyed = false;
	let wasOpen = false;
	$effect(() => {
		if (wasOpen && !open && activeContext) {
			modalRevision += 1;
			recordExperience(activeContext, 'view.exposure_changed', { visibility: 'hidden' });
		}
		wasOpen = open;
	});

	async function createVolume() {
		const context = beginExperienceAction('block_storage', 'create', 'block_storage.create');
		if (!form.name.trim() || form.size_gb < 1) {
			recordExperience(context, 'validation.rejected', { reason: !form.name.trim() ? 'required' : 'format' });
			return;
		}
		const revision = modalRevision;
		const actor = $auth.userId;
		const project = projectId;
		const owns = () => !destroyed && actor === $auth.userId && project === projectId;
		const visible = () => owns() && open && revision === modalRevision;
		activeContext = context;
		creating = true;
		createError = '';
		experienceState(context, 'loading', 1);
		try {
			const created = await apiMut(t('createModal.mutationLabel'), () =>
				api.post<{ id?: string }>('/api/v1/volumes', form, token, project, context ? { experience: context } : undefined), { experience: context });
			const appliedContext = owns() ? context : undefined;
			if (!owns()) experienceDiscarded(context, destroyed ? 'unmounted' : 'scope_changed');
			if (!created?.id) experienceDiscarded(appliedContext, 'unknown');
			experienceState(appliedContext, 'loading', 2);
			const appliedRevision = modalRevision;
			if (activeContext === context) activeContext = undefined;
			open = false;
			form = { name: '', size_gb: 10 };
			// A 201 and closing the modal are not native availability or list application.
			void onCreated(owns() ? appliedContext : undefined, created?.id);
			void experienceApplied(appliedContext, undefined, () => owns() && !open && appliedRevision === modalRevision).then(() => {
				if (owns() && !open && appliedRevision === modalRevision) recordExperience(appliedContext, 'view.exposure_changed', { visibility: 'hidden' });
			});
		} catch (e) {
			if (!owns()) experienceDiscarded(context, destroyed ? 'unmounted' : 'scope_changed');
			createError = e instanceof ApiError ? e.message : t('createModal.createFailed');
			if (owns()) {
				// UI errors still render normally; ambiguous transport outcomes never become native failure.
				if (e instanceof ApiError && e.status >= 400 && e.status < 500 && e.status !== 408 && e.status !== 499) experienceState(context, 'error', 1);
				else experienceDiscarded(context, 'unknown');
			}
			if (visible()) {
				experienceMessage(context, e instanceof ApiError
					? unavailableExperienceMessage('danger')
					: { ...resolveExperienceMessage('volume', 'createModal.createFailed'), tone: 'danger' });
				void experienceApplied(context, undefined, visible);
			}
		} finally {
			creating = false;
			if (activeContext === context) activeContext = undefined;
		}
	}

	function close() {
		modalRevision += 1;
		const context = activeContext ?? beginExperienceAction('block_storage', 'close', 'block_storage.create');
		recordExperience(context, 'view.exposure_changed', { visibility: 'hidden' });
		open = false;
		createError = '';
	}

	onDestroy(() => {
		destroyed = true;
		experienceDiscarded(activeContext, 'unmounted');
		activeContext = undefined;
	});
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
			{#if creating}<LoadingState variant="inline" label={t('createModal.mutationLabel')} class="mt-4" />{/if}
			<div class="flex justify-end gap-3 mt-6">
				<button onclick={close} class="px-4 py-2 text-sm text-ink-2 hover:text-ink-0 transition-colors">{t('createModal.cancel')}</button>
				<Button
					dataTour="volume-create-submit"
					onclick={createVolume}
					disabled={creating || !form.name.trim() || form.size_gb < 1}
					ariaBusy={creating}
				>{#if creating}<LoadingState variant="control" label="" />{t('createModal.creating')}{:else}{t('createModal.create')}{/if}</Button>
			</div>
		</div>
	</div>
{/if}
