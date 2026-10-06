<script lang="ts">
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import { projectNames } from '$lib/stores/projectNames';
	import { dialogFocus } from '$lib/utils/dialogFocus';
	import RichText from '$lib/i18n/RichText.svelte';
	import { t } from '$lib/i18n/ns/admin-identity';
	import { t as tc } from '$lib/i18n/ns/common';

	interface Project {
		id: string;
		name: string;
		description: string;
		enabled: boolean;
		domain_id: string | null;
		created_at: string | null;
	}

	let {
		project,
		onClose,
		onSuccess,
	}: {
		project: Project | null;
		onClose: () => void;
		onSuccess: () => void;
	} = $props();

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	let deleting = $state(false);
	let deleteError = $state('');

	$effect(() => {
		if (project) deleteError = '';
	});

	async function confirmDelete() {
		if (!project) return;
		deleting = true;
		deleteError = '';
		const namesScope = projectNames.scope(token, projectId);
		projectNames.invalidate(namesScope);
		try {
			await api.delete(`/api/v1/admin/projects/${project.id}`, token, projectId);
			projectNames.invalidate(namesScope);
			onSuccess();
			onClose();
		} catch (e) {
			deleteError = e instanceof ApiError ? e.message : t('projectDelete.failed');
		} finally {
			deleting = false;
		}
	}
</script>

{#snippet nameTag(text: string)}<span class="text-ink-0 font-medium">{text}</span>{/snippet}

{#if project}
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		use:dialogFocus={{ enabled: true, onEscape: () => onClose() }}
		class="fixed inset-0 bg-surface-scrim/60 flex items-center justify-center z-50"
		onclick={onClose}
		role="dialog" aria-modal="true" tabindex="-1"
	>
		<div
			class="bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-sm mx-4 shadow-[var(--shadow-restraint)]"
			onclick={(e) => e.stopPropagation()}
			role="none"
		>
			<h2 class="text-lg font-semibold text-ink-0 mb-3">{t('projectDelete.title')}</h2>
			<p class="text-sm text-ink-2 mb-2"><RichText segments={t.rich('projectDelete.body', { name: project.name })} tags={{ name: nameTag }} /></p>
			<p class="text-xs text-red-400 mb-4">{t('projectDelete.irreversible')}</p>
			{#if deleteError}
				<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm mb-4">{deleteError}</div>
			{/if}
			<div class="flex justify-end gap-3">
				<button onclick={onClose} class="px-4 py-2 bg-surface-selected hover:bg-surface-selected text-ink-0 text-sm font-medium rounded-lg">{tc('actions.cancel')}</button>
				<button aria-busy={deleting} onclick={confirmDelete} disabled={deleting} class="px-4 py-2 bg-[var(--color-state-danger)]/10 hover:bg-[var(--color-state-danger)]/20 text-[var(--color-state-danger-text)] text-sm font-medium rounded-lg disabled:opacity-30">{#if deleting}<span class="inline-flex items-center gap-2" role="status"><ActivityIndicator size="xs" />{t('state.deleting')}</span>{:else}{t('actions.delete')}{/if}</button>
			</div>
		</div>
	</div>
{/if}
