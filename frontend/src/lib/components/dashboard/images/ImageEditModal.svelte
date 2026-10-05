<script lang="ts">
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import type { ImageInfo } from '$lib/types/compute';
	import Button from '$lib/components/ui/Button.svelte';
	import { dialogFocus } from '$lib/utils/dialogFocus';
	import { t } from '$lib/i18n/ns/images-keys';

	let {
		target,
		onClose,
		onSaved,
	}: {
		target: ImageInfo | null;
		onClose: () => void;
		onSaved: (updated: ImageInfo) => void;
	} = $props();

	let form = $state({ name: '', os_distro: '', os_type: '', min_disk: 0, min_ram: 0 });
	let saving = $state(false);
	let saveError = $state('');

	$effect(() => {
		if (target) {
			form = {
				name: target.name,
				os_distro: target.os_distro ?? '',
				os_type: '',
				min_disk: target.min_disk ?? 0,
				min_ram: target.min_ram ?? 0,
			};
			saveError = '';
		}
	});

	async function save() {
		if (!target) return;
		saving = true;
		saveError = '';
		try {
			const body: Record<string, unknown> = {};
			if (form.name !== target.name) body.name = form.name;
			if (form.os_distro !== (target.os_distro ?? '')) body.os_distro = form.os_distro || null;
			if (form.os_type) body.os_type = form.os_type;
			if (form.min_disk !== target.min_disk) body.min_disk = form.min_disk;
			if (form.min_ram !== target.min_ram) body.min_ram = form.min_ram;
			if (Object.keys(body).length === 0) { onClose(); return; }
			const updated = await api.patch<ImageInfo>(
				`/api/v1/images/${target.id}`, body,
				$auth.token ?? undefined, $auth.projectId ?? undefined,
			);
			onSaved(updated);
			onClose();
		} catch (e) {
			saveError = e instanceof ApiError ? e.message : t('imageEdit.saveFailed');
		} finally {
			saving = false;
		}
	}
</script>

{#if target}
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		use:dialogFocus={{ enabled: true, onEscape: () => onClose() }} class="fixed inset-0 bg-surface-scrim/60 flex items-center justify-center z-50"
	     onclick={() => { onClose(); }}
	     role="dialog" aria-modal="true" tabindex="-1"
>
		<div class="bg-[var(--color-surface-raised)] border border-[var(--color-line)] rounded-xl p-6 w-full max-w-md mx-4 shadow-[var(--shadow-restraint)]"
		     onclick={(e) => e.stopPropagation()}
		     role="none">
			<h2 class="text-lg font-semibold text-[var(--color-ink-0)] mb-5">{t('imageEdit.title')}</h2>
			<div class="space-y-4">
				<div>
					<label class="block text-xs text-[var(--color-ink-2)] mb-1.5 uppercase tracking-wide">{t('imageEdit.name')}
						<input bind:value={form.name} type="text" class="w-full bg-[var(--color-surface-sunken)] border border-[var(--color-line-2)] rounded-lg px-3 py-2 text-[var(--color-ink-0)] text-sm focus:outline-none focus:border-[var(--color-accent)] mt-1.5" />
						<span class="block text-xs text-[var(--color-ink-3)] mt-1">{t('imageEdit.nameHelp')}</span>
					</label>
				</div>
				<div>
					<label class="block text-xs text-[var(--color-ink-2)] mb-1.5 uppercase tracking-wide">{t('imageEdit.osDistro')}
						<input bind:value={form.os_distro} type="text" placeholder={t('imageEdit.osDistroPlaceholder')} class="w-full bg-[var(--color-surface-sunken)] border border-[var(--color-line-2)] rounded-lg px-3 py-2 text-[var(--color-ink-0)] text-sm focus:outline-none focus:border-[var(--color-accent)] mt-1.5" />
					</label>
				</div>
				<div class="grid grid-cols-2 gap-3">
					<div>
						<label class="block text-xs text-[var(--color-ink-2)] mb-1.5 uppercase tracking-wide">{t('imageEdit.minDisk')}
							<input bind:value={form.min_disk} type="number" min="0" class="w-full bg-[var(--color-surface-sunken)] border border-[var(--color-line-2)] rounded-lg px-3 py-2 text-[var(--color-ink-0)] text-sm focus:outline-none focus:border-[var(--color-accent)] mt-1.5" />
						</label>
					</div>
					<div>
						<label class="block text-xs text-[var(--color-ink-2)] mb-1.5 uppercase tracking-wide">{t('imageEdit.minRam')}
							<input bind:value={form.min_ram} type="number" min="0" class="w-full bg-[var(--color-surface-sunken)] border border-[var(--color-line-2)] rounded-lg px-3 py-2 text-[var(--color-ink-0)] text-sm focus:outline-none focus:border-[var(--color-accent)] mt-1.5" />
						</label>
					</div>
				</div>
			</div>
			{#if saveError}<div class="mt-3 text-[var(--color-state-danger)] text-xs">{saveError}</div>{/if}
			<div class="flex justify-end gap-3 mt-6">
				<Button variant="ghost" size="md" onclick={onClose}>{t('imageEdit.cancel')}</Button>
				<Button variant="accent" size="md" onclick={save} disabled={saving}>{saving ? t('imageEdit.saving') : t('imageEdit.save')}</Button>
			</div>
		</div>
	</div>
{/if}
