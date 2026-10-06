<script lang="ts">
	import { uploadQueue } from '$lib/stores/uploadQueue';
	import { parseImageReference, sanitizeImageFilename } from '$lib/utils/imageReference';
	import Button from '$lib/components/ui/Button.svelte';
	import { ActivityIndicator } from '$lib/components/ui';
	import { dialogFocus } from '$lib/utils/dialogFocus';
	import { t } from '$lib/i18n/ns/images-keys';
	import RichText from '$lib/i18n/RichText.svelte';

	interface Props {
		open: boolean;
		token?: string;
		projectId?: string;
		initialFile?: File | null;
		onUploaded?: () => void;
		onClose?: () => void;
	}

	let { open = $bindable(), token, projectId, initialFile = null, onUploaded, onClose }: Props = $props();

	const DISK_FORMATS = ['raw', 'qcow2', 'vmdk', 'vdi', 'vhd', 'vhdx', 'iso', 'ami'] as const;

	let name = $state('');
	let diskFormat = $state<string>('raw');
	let visibility = $state('private');
	let osDistro = $state('');
	let file = $state<File | null>(null);
	let dropActive = $state(false);
	let formError = $state('');

	$effect(() => {
		if (initialFile) {
			file = initialFile;
			if (!name) name = sanitizeImageFilename(initialFile.name);
		}
	});

	$effect(() => {
		if (!open) {
			name = '';
			diskFormat = 'raw';
			visibility = 'private';
			osDistro = '';
			file = null;
			dropActive = false;
			formError = '';
		}
	});

	function close() {
		open = false;
		onClose?.();
	}

	function onFileInput(e: Event) {
		const input = e.currentTarget as HTMLInputElement;
		const f = input.files?.[0];
		if (f) {
			file = f;
			if (!name) name = sanitizeImageFilename(f.name);
		}
	}

	function onDropzoneEnter(e: DragEvent) {
		if (!hasFiles(e)) return;
		e.preventDefault();
		dropActive = true;
	}
	function onDropzoneOver(e: DragEvent) {
		if (!hasFiles(e)) return;
		e.preventDefault();
		dropActive = true;
	}
	function onDropzoneLeave() {
		dropActive = false;
	}
	function onDropzoneDrop(e: DragEvent) {
		e.preventDefault();
		dropActive = false;
		const f = e.dataTransfer?.files?.[0];
		if (f) {
			file = f;
			if (!name) name = sanitizeImageFilename(f.name);
		}
	}

	function hasFiles(e: DragEvent): boolean {
		const types = e.dataTransfer?.types;
		if (!types) return false;
		for (let i = 0; i < types.length; i++) if (types[i] === 'Files') return true;
		return false;
	}

	function submit() {
		formError = '';
		if (!name.trim()) { formError = t('uploadModal.nameRequired'); return; }
		if (!file) { formError = t('uploadModal.fileRequired'); return; }
		let normalizedName: string;
		try {
			normalizedName = parseImageReference(name).name;
		} catch (error) {
			formError = error instanceof Error ? error.message : t('uploadModal.invalidName');
			return;
		}

		const extraFields: Record<string, string> = {
			name: normalizedName,
			disk_format: diskFormat,
			visibility,
		};
		if (osDistro.trim()) extraFields.os_distro = osDistro.trim();

		uploadQueue.enqueue(file, {
			endpoint: '/api/v1/images',
			extraFields,
			kind: 'image',
			token,
			projectId,
			onComplete: (job) => {
				if (job.status === 'success') onUploaded?.();
			},
		});
		close();
	}

	function formatBytes(n: number): string {
		if (n >= 1073741824) return `${(n / 1073741824).toFixed(1)} GB`;
		if (n >= 1048576) return `${(n / 1048576).toFixed(1)} MB`;
		if (n >= 1024) return `${(n / 1024).toFixed(0)} KB`;
		return `${n} B`;
	}
</script>

{#snippet requiredMarker(text: string)}<span class="text-[var(--color-state-danger)]">{text}</span>{/snippet}

{#if open}
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		use:dialogFocus={{ enabled: true, onEscape: () => close() }}
		class="motion-fade fixed inset-0 bg-surface-scrim/60 flex items-center justify-center z-50"
		onclick={close}
		role="dialog"
		aria-modal="true"
		tabindex="-1"
	>
		<div
			class="motion-pop bg-[var(--color-surface-raised)] border border-[var(--color-line)] rounded-xl p-6 w-full max-w-lg mx-4 shadow-[var(--shadow-restraint)]"
			onclick={(e) => e.stopPropagation()}
			role="none"
		>
			<h2 class="text-lg font-semibold text-[var(--color-ink-0)] mb-5">{t('uploadModal.title')}</h2>

			<!-- 드롭존 -->
			<div
				class="border-2 border-dashed rounded-xl p-6 mb-5 text-center transition-colors cursor-pointer
					{dropActive ? 'border-[var(--color-accent)] bg-[var(--color-accent)]/10' : 'border-[var(--color-line)] hover:border-[var(--color-line-2)]'}"
				role="button"
				tabindex="0"
				ondragenter={onDropzoneEnter}
				ondragover={onDropzoneOver}
				ondragleave={onDropzoneLeave}
				ondrop={onDropzoneDrop}
				onclick={() => (document.getElementById('image-file-input') as HTMLInputElement)?.click()}
				onkeydown={(e) => e.key === 'Enter' && (document.getElementById('image-file-input') as HTMLInputElement)?.click()}
			>
				{#if dropActive}
					<div class="motion-pop mb-3"><ActivityIndicator variant="upload" label={t('uploadModal.dropFiles')} /></div>
				{/if}
				{#if file}
					<div class="text-sm text-[var(--color-ink-0)] font-medium">{file.name}</div>
					<div class="text-xs text-[var(--color-ink-3)] mt-1">{formatBytes(file.size)}</div>
					<button
						class="text-xs text-[var(--color-ink-3)] hover:text-[var(--color-state-danger)] mt-2 transition-colors"
						onclick={(e) => { e.stopPropagation(); file = null; }}
					>{t('uploadModal.removeFile')}</button>
				{:else}
					<div class="text-[var(--color-ink-3)] text-sm">{t('uploadModal.chooseFile')}</div>
					<div class="text-[var(--color-ink-3)] text-xs mt-1">{t('uploadModal.fileFormats')}</div>
				{/if}
			</div>
			<input id="image-file-input" type="file" class="hidden" onchange={onFileInput} />

			<div class="space-y-4">
				<!-- 이름 -->
				<div>
					<label for="img-name" class="block text-xs text-[var(--color-ink-2)] mb-1.5 uppercase tracking-wide">
						<RichText segments={t.rich('uploadModal.nameLabel')} tags={{ required: requiredMarker }} />
					</label>
					<input
						id="img-name"
						bind:value={name}
						type="text"
						placeholder={t('uploadModal.namePlaceholder')}
						class="w-full bg-[var(--color-surface-sunken)] border border-[var(--color-line-2)] rounded-lg px-3 py-2 text-[var(--color-ink-0)] text-sm focus:outline-none focus:border-[var(--color-accent)]"
					/>
					<div class="text-xs text-[var(--color-ink-3)] mt-1">{t('uploadModal.nameHelp')}</div>
				</div>

				<div class="grid grid-cols-2 gap-3">
					<!-- Disk Format -->
					<div>
						<label for="img-disk-format" class="block text-xs text-[var(--color-ink-2)] mb-1.5 uppercase tracking-wide">{t('uploadModal.diskFormat')}</label>
						<select
							id="img-disk-format"
							bind:value={diskFormat}
							class="w-full bg-[var(--color-surface-sunken)] border border-[var(--color-line-2)] rounded-lg px-3 py-2 text-[var(--color-ink-0)] text-sm focus:outline-none focus:border-[var(--color-accent)]"
						>
							{#each DISK_FORMATS as fmt}
								<option value={fmt}>{fmt}</option>
							{/each}
						</select>
					</div>

					<!-- Visibility -->
					<div>
						<label for="img-visibility" class="block text-xs text-[var(--color-ink-2)] mb-1.5 uppercase tracking-wide">{t('uploadModal.visibility')}</label>
						<select
							id="img-visibility"
							bind:value={visibility}
							class="w-full bg-[var(--color-surface-sunken)] border border-[var(--color-line-2)] rounded-lg px-3 py-2 text-[var(--color-ink-0)] text-sm focus:outline-none focus:border-[var(--color-accent)]"
						>
							<option value="private">{t('uploadModal.private')}</option>
							<option value="shared">{t('uploadModal.shared')}</option>
						</select>
					</div>
				</div>

				<!-- OS Distro -->
				<div>
					<label for="img-os-distro" class="block text-xs text-[var(--color-ink-2)] mb-1.5 uppercase tracking-wide">{t('uploadModal.osDistro')}</label>
					<input
						id="img-os-distro"
						bind:value={osDistro}
						type="text"
						placeholder={t('uploadModal.osDistroPlaceholder')}
						class="w-full bg-[var(--color-surface-sunken)] border border-[var(--color-line-2)] rounded-lg px-3 py-2 text-[var(--color-ink-0)] text-sm focus:outline-none focus:border-[var(--color-accent)]"
					/>
				</div>
			</div>

			{#if formError}
				<div class="mt-3 text-[var(--color-state-danger)] text-xs">{formError}</div>
			{/if}

			<div class="flex justify-end gap-3 mt-6">
				<Button variant="ghost" size="md" onclick={close}>{t('uploadModal.cancel')}</Button>
				<Button variant="accent" size="md" onclick={submit}>{t('uploadModal.startUpload')}</Button>
			</div>
		</div>
	</div>
{/if}
