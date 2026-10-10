<script lang="ts">
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import { dialogFocus } from '$lib/utils/dialogFocus';
	import { t } from '$lib/i18n/ns/admin-storage';
	import RichText from '$lib/i18n/RichText.svelte';

	interface AdminVolume {
		id: string;
		name: string;
		status: string;
		size: number;
		project_id: string | null;
		created_at: string | null;
		bootable?: boolean;
	}

	let {
		volume,
		onClose,
		onSuccess,
	}: {
		volume: AdminVolume | null;
		onClose: () => void;
		onSuccess: () => void;
	} = $props();

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	let transferSearch = $state('');
	let transferProjectId = $state('');
	let transferProjectName = $state('');
	let showTransferDropdown = $state(false);
	let transferring = $state(false);
	let transferError = $state('');
	let allProjects = $state<{ id: string; name: string }[]>([]);

	let filteredTransferProjects = $derived(
		transferSearch
			? allProjects.filter((p) => p.name.toLowerCase().includes(transferSearch.toLowerCase()))
			: allProjects,
	);

	$effect(() => {
		if (volume) {
			transferSearch = '';
			transferProjectId = '';
			transferProjectName = '';
			transferError = '';
			showTransferDropdown = false;
			if (allProjects.length === 0) {
				api
					.get<{ id: string; name: string }[]>('/api/v1/admin/projects/names', token, projectId)
					.then((r) => (allProjects = r))
					.catch(() => (allProjects = []));
			}
		}
	});

	async function confirmTransfer() {
		if (!volume || !transferProjectId) return;
		transferring = true;
		transferError = '';
		try {
			await api.post(
				`/api/v1/admin/volumes/${volume.id}/transfer`,
				{ target_project_id: transferProjectId },
				token,
				projectId,
			);
			onSuccess();
			onClose();
		} catch (e) {
			transferError = e instanceof ApiError ? e.message : t('volumeTransfer.failed');
		} finally {
			transferring = false;
		}
	}
</script>

{#snippet volumeName(text: string)}<span class="text-ink-0">{text}</span>{/snippet}
{#snippet projectName(text: string)}<span class="text-warm-text">{text}</span>{/snippet}

{#if volume}
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		use:dialogFocus={{ enabled: true, onEscape: () => onClose() }}
		class="fixed inset-0 bg-surface-scrim/60 flex items-center justify-center z-50"
		onclick={onClose}
		role="dialog" aria-modal="true" tabindex="-1"
	>
		<div
			class="bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-md mx-4 shadow-[var(--shadow-restraint)]"
			onclick={(e) => e.stopPropagation()}
			role="none"
		>
			<h2 class="text-lg font-semibold text-ink-0 mb-3">{t('volumeTransfer.title')}</h2>
			<p class="text-xs text-ink-2 mb-4"><RichText segments={t.rich('volumeTransfer.description', { name: volume.name || volume.id.slice(0, 8) })} tags={{ name: volumeName }} /></p>
			{#if transferError}
				<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm mb-4">{transferError}</div>
			{/if}
			<div class="relative">
				<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide" for="field-adminvolumetransfermodal-100">{t('volumeTransfer.targetProject')}</label>
				<input id="field-adminvolumetransfermodal-100"
					type="text"
					bind:value={transferSearch}
					onfocus={() => (showTransferDropdown = true)}
					oninput={() => {
						showTransferDropdown = true;
						if (!transferSearch) { transferProjectId = ''; transferProjectName = ''; }
					}}
					onblur={() => setTimeout(() => { showTransferDropdown = false; }, 150)}
					placeholder={t('volumeTransfer.searchProject')}
					class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm"
				/>
				{#if showTransferDropdown && filteredTransferProjects.length > 0}
					<div class="absolute z-10 w-full mt-1 bg-surface-sunken border border-line-2 rounded-lg shadow-[var(--shadow-restraint)] max-h-40 overflow-y-auto">
						{#each filteredTransferProjects as p (p.id)}
							<button
								type="button"
								onmousedown={() => { transferProjectId = p.id; transferProjectName = p.name; transferSearch = p.name; showTransferDropdown = false; }}
								class="w-full text-left px-3 py-2 text-sm text-ink-2 hover:bg-surface-selected transition-colors {transferProjectId === p.id ? 'bg-surface-selected text-ink-0' : ''}"
							>{p.name}</button>
						{/each}
					</div>
				{/if}
				{#if transferProjectName}
					<div class="mt-1 text-xs text-ink-2"><RichText segments={t.rich('volumeTransfer.selectedProject', { name: transferProjectName })} tags={{ name: projectName }} /></div>
				{/if}
			</div>
			<div class="flex justify-end gap-3 mt-6">
				<button onclick={onClose} class="px-4 py-2 bg-surface-selected hover:bg-surface-selected text-ink-0 text-sm font-medium rounded-lg">{t('volumeTransfer.cancel')}</button>
				<button onclick={confirmTransfer} disabled={transferring || !transferProjectId} class="px-4 py-2 bg-accent hover:bg-accent/90 text-surface-canvas text-sm font-medium rounded-lg disabled:opacity-30">{#if transferring}<span class="inline-flex items-center gap-2" role="status"><ActivityIndicator size="xs" tone="ink" /><span>{t('volumeTransfer.transferring')}</span></span>{:else}{t('volumeTransfer.transfer')}{/if}</button>
			</div>
		</div>
	</div>
{/if}
