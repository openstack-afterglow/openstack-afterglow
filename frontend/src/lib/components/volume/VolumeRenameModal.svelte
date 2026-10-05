<script lang="ts">
	import { get } from 'svelte/store';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import { toast } from '$lib/stores/toast';
	import type { Volume } from '$lib/types/volume';
	import { Field, FormModal, TextInput } from '$lib/components/ui';
	import { t } from '$lib/i18n/ns/volume';

	const MAX_NAME_LENGTH = 255;

	let { volume, onclose, onrenamed }: {
		volume: Volume | null;
		onclose: () => void;
		onrenamed: (updated: Volume) => void;
	} = $props();

	const inputId = $props.id();
	let name = $state('');
	let error = $state('');
	let saving = $state(false);
	let targetId = '';

	$effect.pre(() => {
		const id = volume?.id ?? '';
		if (id === targetId) return;
		targetId = id;
		name = volume?.name ?? '';
		error = '';
		saving = false;
	});

	function close() {
		if (saving) return;
		onclose();
	}

	async function submit() {
		const target = volume;
		if (!target || saving) return;
		const trimmed = name.trim();
		if (!trimmed) {
			error = t('renameModal.nameRequired');
			return;
		}
		if (trimmed.length > MAX_NAME_LENGTH) {
			error = t('renameModal.nameTooLong', { maxLength: MAX_NAME_LENGTH });
			return;
		}
		if (trimmed === target.name) {
			onclose();
			return;
		}
		const { token, projectId } = get(auth);
		saving = true;
		error = '';
		try {
			const updated = await api.patch<Volume>(
				`/api/v1/volumes/${encodeURIComponent(target.id)}`,
				{ name: trimmed },
				token ?? undefined,
				projectId ?? undefined,
			);
			saving = false;
			// The project changed while the request was in flight; the new scope
			// reloads its own data, so never apply this response to it.
			if (get(auth).projectId !== projectId) {
				onclose();
				return;
			}
			toast.success(t('renameModal.renamed'));
			onrenamed({ ...target, ...updated, name: updated?.name ?? trimmed });
		} catch (e) {
			saving = false;
			error = e instanceof ApiError ? e.message : t('renameModal.renameFailed');
		}
	}
</script>

{#if volume}
	<FormModal
		open={true}
		title={t('renameModal.title')}
		submitLabel={t('renameModal.save')}
		submitting={saving}
		onClose={close}
		onSubmit={submit}
	>
		<form onsubmit={(event) => { event.preventDefault(); void submit(); }}>
			<Field label={t('renameModal.nameLabel')} for={inputId} error={error} required help={volume.attachments.length > 0 ? t('renameModal.attachedHelp') : undefined}>
				<TextInput
					id={inputId}
					bind:value={name}
					maxlength={MAX_NAME_LENGTH}
					disabled={saving}
					required
					ariaInvalid={!!error}
					oninput={() => { error = ''; }}
				/>
			</Field>
			<p class="mt-2 text-xs text-ink-2 font-mono break-all">{volume.id}</p>
		</form>
	</FormModal>
{/if}
