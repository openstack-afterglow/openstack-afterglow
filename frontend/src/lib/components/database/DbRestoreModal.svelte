<script lang="ts">
	import { t as tr } from '$lib/i18n/ns/database';
	import RichText from '$lib/i18n/RichText.svelte';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import type { DbFlavor, DbBackup } from '$lib/types/database';
	import { dialogFocus } from '$lib/utils/dialogFocus';

	interface Props {
		open: boolean;
		backup: DbBackup | null;
		flavors?: DbFlavor[];
		onRestore: (backupId: string, name: string, flavorId: string, volumeSize: number) => Promise<void>;
		onClose: () => void;
	}

	let { open = $bindable(), backup, flavors: externalFlavors, onRestore, onClose }: Props = $props();

	let name = $state('');
	let flavorId = $state('');
	let volumeSize = $state(5);
	let loadedFlavors = $state<DbFlavor[]>([]);
	let submitting = $state(false);
	let error = $state('');

	const flavors = $derived(externalFlavors && externalFlavors.length > 0 ? externalFlavors : loadedFlavors);
	const minVolume = $derived(backup?.size ? Math.max(5, Math.ceil(backup.size)) : 5);

	$effect(() => {
		if (!open || !backup) return;
		name = backup.name ? `${backup.name}-restored` : 'restored-db';
		volumeSize = minVolume;
		error = '';
		if (!externalFlavors || externalFlavors.length === 0) {
			api.get<DbFlavor[]>('/api/v1/database-instances/flavors', $auth.token ?? undefined, $auth.projectId ?? undefined)
				.then(f => {
					loadedFlavors = f;
					if (f.length > 0 && !flavorId) flavorId = String(f[0].id);
				})
				.catch(() => {});
		} else if (externalFlavors.length > 0 && !flavorId) {
			flavorId = String(externalFlavors[0].id);
		}
	});

	async function handleSubmit() {
		if (!backup || !name.trim() || !flavorId) { error = tr('validation.allFields'); return; }
		if (volumeSize < minVolume) { error = tr('validation.minVolume', { size: minVolume }); return; }
		submitting = true; error = '';
		try {
			await onRestore(backup.id, name.trim(), flavorId, volumeSize);
			open = false;
		} catch (e) {
			error = e instanceof ApiError ? e.message : tr('restore.failed');
		} finally {
			submitting = false;
		}
	}

	function handleClose() {
		open = false;
		onClose();
	}
</script>

{#snippet backupName(text: string)}<span class="text-ink-2 font-medium">{text}</span>{/snippet}

{#if open && backup}
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		use:dialogFocus={{ enabled: true, onEscape: () => handleClose() }}
		class="fixed inset-0 bg-surface-scrim/60 flex items-center justify-center z-50"
		onclick={handleClose}
		role="dialog"
		aria-modal="true"
		tabindex="-1"
	>
		<div
			class="bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-md mx-4 shadow-[var(--shadow-restraint)]"
			onclick={(e) => e.stopPropagation()}
			role="none"
		>
			<h2 class="text-lg font-semibold text-ink-0 mb-1">{tr('restore.title')}</h2>
			<p class="text-xs text-ink-2 mb-4"><RichText segments={tr.rich('restore.description', { name: backup.name || backup.id.slice(0, 8) })} tags={{ name: backupName }} /></p>

			<div class="space-y-3">
				<label class="flex flex-col gap-1">
					<span class="text-xs text-ink-2">{tr('restore.instanceName')} <span class="text-red-400">*</span></span>
					<input
						type="text"
						bind:value={name}
						placeholder={tr('restore.namePlaceholder')}
						class="bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0 placeholder-ink-3 focus:outline-none focus:border-action-warm"
					/>
				</label>

				<label class="flex flex-col gap-1">
					<span class="text-xs text-ink-2">{tr('labels.flavorEnglish')} <span class="text-red-400">*</span></span>
					<select
						bind:value={flavorId}
						class="bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0 focus:outline-none focus:border-action-warm"
					>
						{#if flavors.length === 0}
							<option value="">{tr('state.loading')}</option>
						{:else}
							{#each flavors as f}
								<option value={String(f.id)}>{f.name} ({f.vcpus}vCPU / {f.ram}MB)</option>
							{/each}
						{/if}
					</select>
				</label>

				<label class="flex flex-col gap-1">
					<span class="text-xs text-ink-2">{tr('labels.volumeSizeGb')} <span class="text-xs text-ink-2">{tr('restore.minimum', { size: minVolume })}</span></span>
					<input
						type="number"
						bind:value={volumeSize}
						min={minVolume}
						step="1"
						class="bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0 focus:outline-none focus:border-action-warm"
					/>
				</label>
			</div>

			{#if error}
				<p class="text-red-400 text-xs mt-3">{error}</p>
			{/if}

			<div class="flex justify-end gap-3 mt-5">
				<button
					onclick={handleClose}
					class="px-4 py-2 text-sm text-ink-2 hover:text-ink-0 transition-colors"
				>
					{tr('actions.cancel')}
				</button>
				<button
					onclick={handleSubmit}
					disabled={submitting}
					class="px-5 py-2 bg-action-warm hover:bg-action-warm-hover disabled:bg-surface-selected disabled:text-ink-3 text-action-on-warm text-sm font-medium rounded-lg transition-colors"
				>
					{submitting ? tr('state.restoring') : tr('actions.startRestore')}
				</button>
			</div>
		</div>
	</div>
{/if}
