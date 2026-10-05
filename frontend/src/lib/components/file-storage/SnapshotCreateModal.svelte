<script lang="ts">
	import { t } from '$lib/i18n/ns/file-storage';
	import type { FileStorage } from '$lib/types/fileStorage';
	import { dialogFocus } from '$lib/utils/dialogFocus';

	let {
		open = $bindable(),
		fileStorages,
		onCreate,
	}: {
		open: boolean;
		fileStorages: FileStorage[];
		onCreate: (form: { share_id: string; name: string; description: string }) => Promise<string | true>;
	} = $props();

	let form = $state({ share_id: '', name: '', description: '' });
	let creating = $state(false);
	let error = $state('');

	$effect(() => {
		if (!open) {
			form = { share_id: '', name: '', description: '' };
			error = '';
			creating = false;
		} else if (fileStorages.length > 0 && !form.share_id) {
			form.share_id = fileStorages[0].id;
		}
	});

	async function submit() {
		if (!form.share_id || !form.name.trim()) return;
		creating = true;
		error = '';
		const result = await onCreate({ ...form });
		creating = false;
		if (result === true) {
			open = false;
		} else {
			error = result;
		}
	}
</script>

{#if open}
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		use:dialogFocus={{ enabled: true, onEscape: () => (open = false) }}
		class="fixed inset-0 bg-surface-scrim/60 flex items-center justify-center z-50"
		onclick={() => (open = false)}
		role="dialog"
		aria-modal="true"
		tabindex="-1"
	>
		<div
			class="bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-lg mx-4 shadow-[var(--shadow-restraint)]"
			onclick={(e) => e.stopPropagation()}
			role="none"
		>
			<h2 class="text-lg font-semibold text-ink-0 mb-5">{t('snapshotCreate.title')}</h2>
			{#if fileStorages.length === 0}
				<p class="text-sm text-ink-2 mb-4">{t('snapshotCreate.noStorage')}</p>
			{:else}
				<div class="space-y-4">
					<div>
						<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">{t('snapshotCreate.storageLabel')}
							<select bind:value={form.share_id} class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1.5">
								<option value="">{t('snapshotCreate.selectStorage')}</option>
								{#each fileStorages as fs}
									<option value={fs.id}>{fs.name || fs.id.slice(0, 12)} ({fs.size} GB)</option>
								{/each}
							</select>
						</label>
					</div>
					<div>
						<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">{t('snapshotCreate.nameLabel')}
							<input bind:value={form.name} type="text" placeholder="snapshot-name" class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1.5" />
						</label>
					</div>
					<div>
						<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">{t('snapshotCreate.descriptionLabel')}
							<input bind:value={form.description} type="text" placeholder={t('snapshotCreate.descriptionPlaceholder')} class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1.5" />
						</label>
					</div>
				</div>
			{/if}
			{#if error}
				<div class="mt-4 text-red-400 text-xs bg-red-900/20 border border-red-800 rounded px-3 py-2">{error}</div>
			{/if}
			<div class="flex justify-end gap-3 mt-6">
				<button onclick={() => (open = false)} class="px-4 py-2 text-sm text-ink-2 hover:text-ink-0 transition-colors">{t('snapshotCreate.cancel')}</button>
				<button
					onclick={submit}
					disabled={creating || !form.share_id || !form.name.trim()}
					class="px-5 py-2 bg-action-warm hover:bg-action-warm-hover disabled:bg-surface-selected disabled:text-ink-3 text-action-on-warm text-sm font-medium rounded-lg transition-colors"
				>{creating ? t('snapshotCreate.creating') : t('snapshotCreate.create')}</button>
			</div>
		</div>
	</div>
{/if}
