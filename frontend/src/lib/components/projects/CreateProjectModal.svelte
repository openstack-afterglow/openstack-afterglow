<script lang="ts">
	import { t } from '$lib/i18n/ns/dashboard-home';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import { dialogFocus } from '$lib/utils/dialogFocus';
  import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';

	let { onClose, onSuccess }: {
		onClose: () => void;
		onSuccess: (project: { id: string; name: string }) => void;
	} = $props();

	let name = $state('');
	let description = $state('');
	let submitting = $state(false);
	let error = $state('');

	async function submit() {
		if (!name.trim() || submitting) return;
		submitting = true;
		error = '';
		try {
			const result = await api.post<{ id: string; name: string; description: string }>(
				'/api/v1/projects',
				{ name: name.trim(), description: description.trim() },
				$auth.token ?? undefined
			);
			onSuccess(result);
		} catch (e) {
			error = e instanceof ApiError ? e.message : t('createProject.failed');
		} finally {
			submitting = false;
		}
	}

	function handleKeydown(e: KeyboardEvent) {
		// Escape 는 dialogFocus 가 처리한다. 여기 남기면 두 번 닫힌다.
		if (e.key === 'Enter' && name.trim()) submit();
	}
</script>

<svelte:window onkeydown={handleKeydown} />

<!-- svelte-ignore a11y_click_events_have_key_events -->
<!-- svelte-ignore a11y_no_static_element_interactions -->
<div
	use:dialogFocus={{ enabled: true, onEscape: onClose }}
	class="fixed inset-0 z-50 flex items-center justify-center bg-surface-scrim/60"
	onclick={(event) => {
		if (event.target === event.currentTarget) onClose();
	}}
	tabindex="-1"
	role="dialog"
	aria-modal="true"
	aria-label={t('createProject.title')}
>
	<div
    class="motion-pop bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-md shadow-[var(--shadow-restraint)]"
		role="none"
	>
		<h2 class="text-base font-semibold text-ink-0 mb-4">{t('createProject.title')}</h2>

		<div class="space-y-3">
			<div>
				<label class="block text-xs text-ink-2 mb-1.5" for="proj-name">
					{t('createProject.name')} <span class="text-red-400">*</span>
				</label>
				<input
					id="proj-name"
					bind:value={name}
					placeholder="my-project"
					class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0 placeholder-ink-3 focus:outline-none focus:border-action-warm transition-colors"
				/>
			</div>
			<div>
				<label class="block text-xs text-ink-2 mb-1.5" for="proj-desc">{t('createProject.description')}</label>
				<input
					id="proj-desc"
					bind:value={description}
					placeholder={t('createProject.descriptionPlaceholder')}
					class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0 placeholder-ink-3 focus:outline-none focus:border-action-warm transition-colors"
				/>
			</div>
		</div>

		{#if error}
			<div class="mt-3 text-xs text-red-400">{error}</div>
		{/if}

		<div class="flex justify-end gap-2 mt-5">
			<button
				onclick={onClose}
				class="px-3 py-2 text-sm text-ink-2 hover:text-ink-0 transition-colors"
			>
				{t('createProject.cancel')}
			</button>
			<button
				onclick={submit}
				disabled={!name.trim() || submitting}
				class="px-4 py-2 bg-action-warm hover:bg-action-warm-hover disabled:bg-action-warm/40 disabled:cursor-not-allowed text-action-on-warm text-sm font-medium rounded-lg transition-colors"
			>
				{#if submitting}<ActivityIndicator size="xs" label={t('createProject.creating')} />{:else}{t('createProject.create')}{/if}
			</button>
		</div>
	</div>
</div>
