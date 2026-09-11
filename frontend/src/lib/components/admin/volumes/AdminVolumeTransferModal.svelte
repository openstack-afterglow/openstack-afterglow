<script lang="ts">
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';

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
			transferError = e instanceof ApiError ? e.message : '이전 실패';
		} finally {
			transferring = false;
		}
	}
</script>

{#if volume}
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		class="fixed inset-0 bg-surface-scrim/60 flex items-center justify-center z-50"
		onclick={onClose}
		role="dialog" aria-modal="true" tabindex="-1"
		onkeydown={(e) => e.key === 'Escape' && onClose()}
	>
		<div
			class="bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-md mx-4 shadow-[var(--shadow-restraint)]"
			onclick={(e) => e.stopPropagation()}
			role="none"
			onkeydown={(e) => e.stopPropagation()}
		>
			<h2 class="text-lg font-semibold text-ink-0 mb-3">볼륨 프로젝트 이전</h2>
			<p class="text-xs text-ink-3 mb-4">볼륨 <span class="text-ink-0">{volume.name || volume.id.slice(0, 8)}</span>을 다른 프로젝트로 이전합니다.</p>
			{#if transferError}
				<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm mb-4">{transferError}</div>
			{/if}
			<div class="relative">
				<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide" for="field-adminvolumetransfermodal-100">대상 프로젝트 *</label>
				<input id="field-adminvolumetransfermodal-100"
					type="text"
					bind:value={transferSearch}
					onfocus={() => (showTransferDropdown = true)}
					oninput={() => {
						showTransferDropdown = true;
						if (!transferSearch) { transferProjectId = ''; transferProjectName = ''; }
					}}
					onblur={() => setTimeout(() => { showTransferDropdown = false; }, 150)}
					placeholder="프로젝트 검색..."
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
					<div class="mt-1 text-xs text-ink-3">선택됨: <span class="text-action-warm">{transferProjectName}</span></div>
				{/if}
			</div>
			<div class="flex justify-end gap-3 mt-6">
				<button onclick={onClose} class="px-4 py-2 bg-surface-selected hover:bg-surface-selected text-ink-0 text-sm font-medium rounded-lg">취소</button>
				<button onclick={confirmTransfer} disabled={transferring || !transferProjectId} class="px-4 py-2 bg-purple-600 hover:bg-purple-500 text-ink-0 text-sm font-medium rounded-lg disabled:opacity-30">{transferring ? '이전 중...' : '이전'}</button>
			</div>
		</div>
	</div>
{/if}
