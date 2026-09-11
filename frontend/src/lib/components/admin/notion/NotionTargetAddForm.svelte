<script lang="ts">
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import NotionTargetFormFields from './NotionTargetFormFields.svelte';
	import type { NotionTargetForm } from './NotionTargetFormFields.svelte';

	let {
		open = $bindable(false),
		onAdded,
	}: {
		open?: boolean;
		onAdded: () => void;
	} = $props();

	const defaultForm = (): NotionTargetForm => ({
		label: '기본',
		apiKey: '',
		databaseId: '',
		enabled: true,
		intervalMinutes: 30,
		usersDatabaseId: '',
		hypervisorsDatabaseId: '',
		gpuSpecDatabaseId: '',
	});

	let form = $state<NotionTargetForm>(defaultForm());
	let adding = $state(false);
	let addError = $state('');

	async function addTarget() {
		if (!form.apiKey) { addError = 'API Key를 입력하세요'; return; }
		if (!form.databaseId) { addError = '인스턴스 Database ID를 입력하세요'; return; }
		if (form.intervalMinutes < 1 || form.intervalMinutes > 1440) {
			addError = '동기화 간격은 1~1440분 사이여야 합니다'; return;
		}
		adding = true; addError = '';
		try {
			await api.post(
				'/api/v1/admin/notion/targets',
				{
					label: form.label,
					api_key: form.apiKey,
					database_id: form.databaseId,
					enabled: form.enabled,
					interval_minutes: form.intervalMinutes,
					users_database_id: form.usersDatabaseId,
					hypervisors_database_id: form.hypervisorsDatabaseId,
					gpu_spec_database_id: form.gpuSpecDatabaseId,
				},
				$auth.token ?? undefined,
				$auth.projectId ?? undefined
			);
			form = defaultForm();
			open = false;
			onAdded();
		} catch (e) {
			addError = e instanceof ApiError ? e.message : '추가 실패';
		} finally {
			adding = false;
		}
	}
</script>

{#if open}
	<div class="bg-surface-base border border-action-warm rounded-lg p-5 mb-6">
		<h2 class="text-sm font-semibold text-action-warm mb-4">새 연동 대상 추가</h2>
		<NotionTargetFormFields {form} mode="add" />
		{#if addError}
			<div class="mt-3 text-red-400 text-sm">{addError}</div>
		{/if}
		<div class="mt-4">
			<button onclick={addTarget} disabled={adding}
				class="px-5 py-2 bg-action-warm hover:bg-action-warm-hover disabled:bg-surface-selected disabled:text-ink-3 text-action-on-warm text-sm font-medium rounded-lg transition-colors">
				{adding ? '추가 중...' : '연결 검증 및 추가'}
			</button>
		</div>
	</div>
{/if}
