<script lang="ts">
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import NotionTargetFormFields from './NotionTargetFormFields.svelte';
	import type { NotionTargetForm } from './NotionTargetFormFields.svelte';
	import type { NotionTarget } from './NotionTargetCard.svelte';

	let {
		target,
		onClose,
		onSaved,
	}: {
		target: NotionTarget | null;
		onClose: () => void;
		onSaved: () => void;
	} = $props();

	let form = $state<NotionTargetForm>({
		label: '',
		apiKey: '',
		databaseId: '',
		enabled: true,
		intervalMinutes: 30,
		usersDatabaseId: '',
		hypervisorsDatabaseId: '',
		gpuSpecDatabaseId: '',
	});
	let saving = $state(false);
	let editError = $state('');

	$effect(() => {
		if (target) {
			form.label = target.label;
			form.apiKey = '';
			form.databaseId = target.database_id;
			form.enabled = target.enabled;
			form.intervalMinutes = target.interval_minutes;
			form.usersDatabaseId = target.users_database_id;
			form.hypervisorsDatabaseId = target.hypervisors_database_id;
			form.gpuSpecDatabaseId = target.gpu_spec_database_id;
			editError = '';
		}
	});

	async function saveEdit() {
		if (!target) return;
		saving = true; editError = '';
		try {
			const data: Record<string, unknown> = {
				label: form.label,
				database_id: form.databaseId,
				enabled: form.enabled,
				interval_minutes: form.intervalMinutes,
				users_database_id: form.usersDatabaseId,
				hypervisors_database_id: form.hypervisorsDatabaseId,
				gpu_spec_database_id: form.gpuSpecDatabaseId,
			};
			if (form.apiKey) data.api_key = form.apiKey;
			await api.patch(
				`/api/v1/admin/notion/targets/${target.id}`,
				data,
				$auth.token ?? undefined,
				$auth.projectId ?? undefined
			);
			onSaved();
			onClose();
		} catch (e) {
			editError = e instanceof ApiError ? e.message : '저장 실패';
		} finally {
			saving = false;
		}
	}
</script>

{#if target}
	<div class="space-y-3">
		<div class="flex items-center justify-between mb-2">
			<h3 class="text-sm font-semibold text-action-warm">수정 중</h3>
			<button onclick={onClose} class="text-xs text-ink-3 hover:text-ink-2">취소</button>
		</div>
		<NotionTargetFormFields {form} mode="edit" />
		{#if editError}
			<div class="text-red-400 text-sm">{editError}</div>
		{/if}
		<button onclick={saveEdit} disabled={saving}
			class="px-4 py-2 bg-action-warm hover:bg-action-warm-hover disabled:bg-surface-selected disabled:text-ink-3 text-action-on-warm text-sm font-medium rounded-lg transition-colors">
			{saving ? '저장 중...' : '저장'}
		</button>
	</div>
{/if}
