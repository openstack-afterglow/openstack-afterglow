<script lang="ts">
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import { toast } from '$lib/stores/toast';

	interface Transfer {
		id: string;
		name: string;
		volume_id: string;
		created_at: string | null;
	}

	interface CreateTransferResult {
		id: string;
		name: string;
		volume_id: string;
		auth_key: string;
		created_at: string | null;
	}

	let { volumeId, volumeName, onClose, onTransferred }: {
		volumeId: string;
		volumeName: string;
		onClose: () => void;
		onTransferred?: () => void;
	} = $props();

	type Mode = 'menu' | 'create' | 'create_done' | 'accept' | 'list';

	let mode = $state<Mode>('menu');
	let loading = $state(false);
	let errorMsg = $state('');

	// 이전 생성
	let transferName = $state('');
	let createdTransfer = $state<CreateTransferResult | null>(null);
	let copied = $state(false);

	// 이전 수락
	let acceptTransferId = $state('');
	let acceptAuthKey = $state('');

	// 이전 목록
	let transfers = $state<Transfer[]>([]);
	let cancellingId = $state<string | null>(null);

	async function createTransfer() {
		loading = true;
		errorMsg = '';
		try {
			const result = await api.post<CreateTransferResult>(
				`/api/v1/volumes/${volumeId}/transfer`,
				{ name: transferName || null },
				$auth.token ?? undefined,
				$auth.projectId ?? undefined,
			);
			createdTransfer = result;
			mode = 'create_done';
		} catch (e) {
			errorMsg = e instanceof ApiError ? e.message : '이전 생성 실패';
		} finally {
			loading = false;
		}
	}

	async function copyAuthKey() {
		if (!createdTransfer) return;
		await navigator.clipboard.writeText(createdTransfer.auth_key ?? '');
		copied = true;
		setTimeout(() => { copied = false; }, 2000);
	}

	async function acceptTransfer() {
		if (!acceptTransferId.trim() || !acceptAuthKey.trim()) return;
		loading = true;
		errorMsg = '';
		try {
			await api.post(
				`/api/v1/volumes/transfer/${acceptTransferId.trim()}/accept`,
				{ auth_key: acceptAuthKey.trim() },
				$auth.token ?? undefined,
				$auth.projectId ?? undefined,
			);
			onTransferred?.();
			onClose();
		} catch (e) {
			errorMsg = e instanceof ApiError ? e.message : '이전 수락 실패';
		} finally {
			loading = false;
		}
	}

	async function loadTransfers() {
		loading = true;
		errorMsg = '';
		try {
			transfers = await api.get<Transfer[]>(
				'/api/v1/volumes/transfers',
				$auth.token ?? undefined,
				$auth.projectId ?? undefined,
			);
		} catch (e) {
			errorMsg = e instanceof ApiError ? e.message : '목록 조회 실패';
		} finally {
			loading = false;
		}
	}

	async function cancelTransfer(id: string) {
		cancellingId = id;
		try {
			await api.delete(
				`/api/v1/volumes/transfer/${id}`,
				$auth.token ?? undefined,
				$auth.projectId ?? undefined,
			);
			await loadTransfers();
		} catch (e) {
			toast.error('취소 실패: ' + (e instanceof ApiError ? e.message : String(e)));
		} finally {
			cancellingId = null;
		}
	}

	function goList() {
		mode = 'list';
		loadTransfers();
	}
</script>

<!-- 배경 오버레이 -->
<div
	class="fixed inset-0 bg-surface-scrim/60 flex items-center justify-center z-50"
	onclick={onClose}
	role="dialog"
	aria-modal="true"
	tabindex="-1"
	onkeydown={(e) => e.key === 'Escape' && onClose()}
>
	<div
		class="bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-lg mx-4 shadow-[var(--shadow-restraint)]"
		onclick={(e) => e.stopPropagation()}
		role="none"
		onkeydown={(e) => e.stopPropagation()}
	>
		{#if mode === 'menu'}
			<h2 class="text-lg font-semibold text-ink-0 mb-2">볼륨 이전</h2>
			<p class="text-sm text-ink-2 mb-5">
				<span class="text-ink-0 font-medium">{volumeName || volumeId.slice(0, 8)}</span> 볼륨을 다른 프로젝트로 이전합니다.
			</p>
			<div class="space-y-3">
				<button
					onclick={() => { mode = 'create'; errorMsg = ''; }}
					class="w-full text-left p-4 rounded-lg border border-line-2 hover:border-action-warm bg-surface-sunken hover:bg-gray-750 transition-colors"
				>
					<div class="font-medium text-ink-0 text-sm mb-1">이전 생성</div>
					<div class="text-xs text-ink-2">이 볼륨의 이전 코드를 생성하여 수락 측에 전달합니다.</div>
				</button>
				<button
					onclick={() => { mode = 'accept'; errorMsg = ''; }}
					class="w-full text-left p-4 rounded-lg border border-line-2 hover:border-green-600 bg-surface-sunken transition-colors"
				>
					<div class="font-medium text-ink-0 text-sm mb-1">이전 수락</div>
					<div class="text-xs text-ink-2">다른 프로젝트에서 받은 이전 ID와 인증 키로 볼륨을 가져옵니다.</div>
				</button>
				<button
					onclick={goList}
					class="w-full text-left p-4 rounded-lg border border-line-2 hover:border-line-2 bg-surface-sunken transition-colors"
				>
					<div class="font-medium text-ink-0 text-sm mb-1">대기 중인 이전 목록</div>
					<div class="text-xs text-ink-2">생성된 이전 요청을 확인하거나 취소합니다.</div>
				</button>
			</div>
			<div class="flex justify-end mt-6">
				<button onclick={onClose} class="px-4 py-2 text-sm text-ink-2 hover:text-ink-0 transition-colors">닫기</button>
			</div>

		{:else if mode === 'create'}
			<h2 class="text-lg font-semibold text-ink-0 mb-4">이전 생성</h2>
			<div class="space-y-3">
				<div>
					<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide" for="field-volumetransfermodal-182">이름 (선택)</label>
					<input id="field-volumetransfermodal-182"
						bind:value={transferName}
						type="text"
						placeholder="transfer-name"
						class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm"
					/>
				</div>
			</div>
			{#if errorMsg}<div class="mt-3 text-red-400 text-xs bg-red-900/20 border border-red-800 rounded px-3 py-2">{errorMsg}</div>{/if}
			<div class="flex justify-end gap-3 mt-6">
				<button onclick={() => mode = 'menu'} class="px-4 py-2 text-sm text-ink-2 hover:text-ink-0 transition-colors">뒤로</button>
				<button
					onclick={createTransfer}
					disabled={loading}
					class="px-5 py-2 bg-action-warm hover:bg-action-warm-hover disabled:bg-surface-selected disabled:text-ink-3 text-action-on-warm text-sm font-medium rounded-lg transition-colors"
				>{loading ? '생성 중...' : '이전 생성'}</button>
			</div>

		{:else if mode === 'create_done' && createdTransfer}
			<h2 class="text-lg font-semibold text-ink-0 mb-2">이전 생성 완료</h2>
			<p class="text-xs text-ink-2 mb-4">아래 정보를 수락 측에 전달하세요. 인증 키는 다시 확인할 수 없습니다.</p>
			<div class="space-y-3">
				<div class="bg-surface-sunken rounded-lg p-3">
					<div class="text-xs text-ink-3 mb-1">이전 ID</div>
					<div class="font-mono text-sm text-ink-0 break-all">{createdTransfer.id}</div>
				</div>
				<div class="bg-surface-sunken rounded-lg p-3">
					<div class="flex items-center justify-between mb-1">
						<div class="text-xs text-ink-3">인증 키</div>
						<button
							onclick={copyAuthKey}
							class="text-xs text-action-warm hover:text-action-warm-hover transition-colors"
						>{copied ? '복사됨!' : '복사'}</button>
					</div>
					<div class="font-mono text-sm text-action-warm break-all">{createdTransfer.auth_key}</div>
				</div>
			</div>
			<div class="flex justify-end mt-6">
				<button onclick={onClose} class="px-5 py-2 bg-surface-selected hover:bg-surface-selected text-ink-0 text-sm font-medium rounded-lg transition-colors">닫기</button>
			</div>

		{:else if mode === 'accept'}
			<h2 class="text-lg font-semibold text-ink-0 mb-4">이전 수락</h2>
			<div class="space-y-3">
				<div>
					<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide" for="field-volumetransfermodal-228">이전 ID</label>
					<input id="field-volumetransfermodal-228"
						bind:value={acceptTransferId}
						type="text"
						placeholder="transfer-id"
						class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm font-mono focus:outline-none focus:border-action-warm"
					/>
				</div>
				<div>
					<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide" for="field-volumetransfermodal-237">인증 키</label>
					<input id="field-volumetransfermodal-237"
						bind:value={acceptAuthKey}
						type="text"
						placeholder="auth-key"
						class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm font-mono focus:outline-none focus:border-action-warm"
					/>
				</div>
			</div>
			{#if errorMsg}<div class="mt-3 text-red-400 text-xs bg-red-900/20 border border-red-800 rounded px-3 py-2">{errorMsg}</div>{/if}
			<div class="flex justify-end gap-3 mt-6">
				<button onclick={() => mode = 'menu'} class="px-4 py-2 text-sm text-ink-2 hover:text-ink-0 transition-colors">뒤로</button>
				<button
					onclick={acceptTransfer}
					disabled={loading || !acceptTransferId.trim() || !acceptAuthKey.trim()}
					class="px-5 py-2 bg-green-600 hover:bg-green-500 disabled:bg-surface-selected disabled:text-ink-3 text-ink-0 text-sm font-medium rounded-lg transition-colors"
				>{loading ? '수락 중...' : '이전 수락'}</button>
			</div>

		{:else if mode === 'list'}
			<h2 class="text-lg font-semibold text-ink-0 mb-4">대기 중인 이전 목록</h2>
			{#if loading}
				<div class="text-center py-6 text-ink-3 text-sm">불러오는 중...</div>
			{:else if errorMsg}
				<div class="text-red-400 text-xs bg-red-900/20 border border-red-800 rounded px-3 py-2">{errorMsg}</div>
			{:else if transfers.length === 0}
				<div class="text-center py-6 text-ink-3 text-sm">대기 중인 이전이 없습니다.</div>
			{:else}
				<div class="space-y-2">
					{#each transfers as t (t.id)}
						<div class="flex items-center justify-between bg-surface-sunken rounded-lg px-3 py-2.5">
							<div class="min-w-0">
								<div class="text-xs text-ink-2 font-mono truncate">{t.id}</div>
								{#if t.name}<div class="text-sm text-ink-0">{t.name}</div>{/if}
								<div class="text-xs text-ink-3">볼륨: {t.volume_id.slice(0, 8)}...</div>
							</div>
							<button
								onclick={() => cancelTransfer(t.id)}
								disabled={cancellingId === t.id}
								class="ml-3 text-xs text-red-400 hover:text-red-300 disabled:text-ink-3 border border-red-900 hover:border-red-700 disabled:border-line-2 px-2 py-1 rounded transition-colors shrink-0"
							>{cancellingId === t.id ? '취소 중...' : '취소'}</button>
						</div>
					{/each}
				</div>
			{/if}
			<div class="flex justify-end gap-3 mt-6">
				<button onclick={() => mode = 'menu'} class="px-4 py-2 text-sm text-ink-2 hover:text-ink-0 transition-colors">뒤로</button>
				<button onclick={loadTransfers} disabled={loading} class="px-4 py-2 text-sm text-ink-2 hover:text-ink-0 border border-line-2 rounded-lg transition-colors">새로고침</button>
			</div>
		{/if}
	</div>
</div>
