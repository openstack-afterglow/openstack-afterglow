<script lang="ts">
	import { get } from 'svelte/store';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import { toast } from '$lib/stores/toast';
	import type { Volume } from '$lib/types/volume';
	import { Field, FormModal, TextInput } from '$lib/components/ui';

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
			error = '볼륨 이름을 입력하세요.';
			return;
		}
		if (trimmed.length > MAX_NAME_LENGTH) {
			error = `볼륨 이름은 ${MAX_NAME_LENGTH}자 이하여야 합니다.`;
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
			toast.success('볼륨 이름을 변경했습니다.');
			onrenamed({ ...target, ...updated, name: updated?.name ?? trimmed });
		} catch (e) {
			saving = false;
			error = e instanceof ApiError ? e.message : '볼륨 이름 변경에 실패했습니다.';
		}
	}
</script>

{#if volume}
	<FormModal
		open={true}
		title="볼륨 이름 변경"
		submitLabel="저장"
		submitting={saving}
		onClose={close}
		onSubmit={submit}
	>
		<form onsubmit={(event) => { event.preventDefault(); void submit(); }}>
			<Field label="볼륨 이름" for={inputId} error={error} required help={volume.attachments.length > 0 ? '연결된 볼륨도 이름을 변경할 수 있습니다.' : undefined}>
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
