<script lang="ts">
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import { toast } from '$lib/stores/toast';
	import { dialogFocus } from '$lib/utils/dialogFocus';
	import { t } from '$lib/i18n/ns/volume';
	import RichText from '$lib/i18n/RichText.svelte';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';

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
			errorMsg = e instanceof ApiError ? e.message : t('transferModal.createFailed');
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
			errorMsg = e instanceof ApiError ? e.message : t('transferModal.acceptFailed');
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
			errorMsg = e instanceof ApiError ? e.message : t('transferModal.listFailed');
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
			toast.error(t('transferModal.cancelFailed', { error: e instanceof ApiError ? e.message : String(e) }));
		} finally {
			cancellingId = null;
		}
	}

	function goList() {
		mode = 'list';
		loadTransfers();
	}
</script>

{#snippet volumeSnippet(text: string)}<span class="text-ink-0 font-medium">{text}</span>{/snippet}

<!-- 배경 오버레이 -->
<!-- svelte-ignore a11y_click_events_have_key_events -->
<!-- svelte-ignore a11y_no_static_element_interactions -->
<div
	use:dialogFocus={{ enabled: true, onEscape: () => onClose() }}
	class="fixed inset-0 bg-surface-scrim/60 flex items-center justify-center z-50"
	onclick={onClose}
	role="dialog"
	aria-modal="true"
	tabindex="-1"
>
	<div
		class="bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-lg mx-4 shadow-[var(--shadow-restraint)]"
		onclick={(e) => e.stopPropagation()}
		role="none"
	>
		{#if mode === 'menu'}
			<h2 class="text-lg font-semibold text-ink-0 mb-2">{t('transferModal.title')}</h2>
			<p class="text-sm text-ink-2 mb-5">
				<RichText segments={t.rich('transferModal.description', { name: volumeName || volumeId.slice(0, 8) })} tags={{ volume: volumeSnippet }} />
			</p>
			<div class="space-y-3">
				<button
					onclick={() => { mode = 'create'; errorMsg = ''; }}
					class="w-full text-left p-4 rounded-lg border border-line-2 hover:border-action-warm bg-surface-sunken hover:bg-gray-750 transition-colors"
				>
					<div class="font-medium text-ink-0 text-sm mb-1">{t('transferModal.createTitle')}</div>
					<div class="text-xs text-ink-2">{t('transferModal.createHelp')}</div>
				</button>
				<button
					onclick={() => { mode = 'accept'; errorMsg = ''; }}
					class="w-full text-left p-4 rounded-lg border border-line-2 hover:border-green-600 bg-surface-sunken transition-colors"
				>
					<div class="font-medium text-ink-0 text-sm mb-1">{t('transferModal.acceptTitle')}</div>
					<div class="text-xs text-ink-2">{t('transferModal.acceptHelp')}</div>
				</button>
				<button
					onclick={goList}
					class="w-full text-left p-4 rounded-lg border border-line-2 hover:border-line-2 bg-surface-sunken transition-colors"
				>
					<div class="font-medium text-ink-0 text-sm mb-1">{t('transferModal.listTitle')}</div>
					<div class="text-xs text-ink-2">{t('transferModal.listHelp')}</div>
				</button>
			</div>
			<div class="flex justify-end mt-6">
				<button onclick={onClose} class="px-4 py-2 text-sm text-ink-2 hover:text-ink-0 transition-colors">{t('transferModal.close')}</button>
			</div>

		{:else if mode === 'create'}
			<h2 class="text-lg font-semibold text-ink-0 mb-4">{t('transferModal.createTitle')}</h2>
			<div class="space-y-3">
				<div>
					<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide" for="field-volumetransfermodal-182">{t('transferModal.nameLabel')}</label>
					<input id="field-volumetransfermodal-182"
						bind:value={transferName}
						type="text"
						placeholder={t('transferModal.namePlaceholder')}
						class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm"
					/>
				</div>
			</div>
			{#if errorMsg}<div class="mt-3 text-red-400 text-xs bg-red-900/20 border border-red-800 rounded px-3 py-2">{errorMsg}</div>{/if}
			<div class="flex justify-end gap-3 mt-6">
				<button onclick={() => mode = 'menu'} class="px-4 py-2 text-sm text-ink-2 hover:text-ink-0 transition-colors">{t('transferModal.back')}</button>
				<button
					onclick={createTransfer}
					disabled={loading}
					class="inline-flex items-center gap-1.5 px-5 py-2 bg-action-warm hover:bg-action-warm-hover disabled:bg-surface-selected disabled:text-ink-3 text-action-on-warm text-sm font-medium rounded-lg transition-colors"
				>{#if loading}<ActivityIndicator size="xs" tone="ink" />{/if}{loading ? t('transferModal.creating') : t('transferModal.createTitle')}</button>
			</div>

		{:else if mode === 'create_done' && createdTransfer}
			<h2 class="text-lg font-semibold text-ink-0 mb-2">{t('transferModal.createdTitle')}</h2>
			<p class="text-xs text-ink-2 mb-4">{t('transferModal.createdHelp')}</p>
			<div class="space-y-3">
				<div class="bg-surface-sunken rounded-lg p-3">
					<div class="text-xs text-ink-2 mb-1">{t('transferModal.idLabel')}</div>
					<div class="font-mono text-sm text-ink-0 break-all">{createdTransfer.id}</div>
				</div>
				<div class="bg-surface-sunken rounded-lg p-3">
					<div class="flex items-center justify-between mb-1">
						<div class="text-xs text-ink-2">{t('transferModal.authKeyLabel')}</div>
						<button
							onclick={copyAuthKey}
							class="text-xs text-warm-text hover:text-warm-text-hover transition-colors"
						>{copied ? t('transferModal.copied') : t('transferModal.copy')}</button>
					</div>
					<div class="font-mono text-sm text-warm-text break-all">{createdTransfer.auth_key}</div>
				</div>
			</div>
			<div class="flex justify-end mt-6">
				<button onclick={onClose} class="px-5 py-2 bg-surface-selected hover:bg-surface-selected text-ink-0 text-sm font-medium rounded-lg transition-colors">{t('transferModal.close')}</button>
			</div>

		{:else if mode === 'accept'}
			<h2 class="text-lg font-semibold text-ink-0 mb-4">{t('transferModal.acceptTitle')}</h2>
			<div class="space-y-3">
				<div>
					<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide" for="field-volumetransfermodal-228">{t('transferModal.idLabel')}</label>
					<input id="field-volumetransfermodal-228"
						bind:value={acceptTransferId}
						type="text"
						placeholder={t('transferModal.idPlaceholder')}
						class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm font-mono focus:outline-none focus:border-action-warm"
					/>
				</div>
				<div>
					<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide" for="field-volumetransfermodal-237">{t('transferModal.authKeyLabel')}</label>
					<input id="field-volumetransfermodal-237"
						bind:value={acceptAuthKey}
						type="text"
						placeholder={t('transferModal.authKeyPlaceholder')}
						class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm font-mono focus:outline-none focus:border-action-warm"
					/>
				</div>
			</div>
			{#if errorMsg}<div class="mt-3 text-red-400 text-xs bg-red-900/20 border border-red-800 rounded px-3 py-2">{errorMsg}</div>{/if}
			<div class="flex justify-end gap-3 mt-6">
				<button onclick={() => mode = 'menu'} class="px-4 py-2 text-sm text-ink-2 hover:text-ink-0 transition-colors">{t('transferModal.back')}</button>
				<button
					onclick={acceptTransfer}
					disabled={loading || !acceptTransferId.trim() || !acceptAuthKey.trim()}
					class="inline-flex items-center gap-1.5 px-5 py-2 bg-green-600 hover:bg-green-500 disabled:bg-surface-selected disabled:text-ink-3 text-ink-0 text-sm font-medium rounded-lg transition-colors"
				>{#if loading}<ActivityIndicator size="xs" tone="ink" />{/if}{loading ? t('transferModal.accepting') : t('transferModal.acceptTitle')}</button>
			</div>

		{:else if mode === 'list'}
			<h2 class="text-lg font-semibold text-ink-0 mb-4">{t('transferModal.listTitle')}</h2>
			{#if loading}
				<div class="flex justify-center py-6"><ActivityIndicator size="sm" label={t('transferModal.loading')} /></div>
			{:else if errorMsg}
				<div class="text-red-400 text-xs bg-red-900/20 border border-red-800 rounded px-3 py-2">{errorMsg}</div>
			{:else if transfers.length === 0}
				<div class="text-center py-6 text-ink-2 text-sm">{t('transferModal.empty')}</div>
			{:else}
				<div class="space-y-2">
					{#each transfers as transfer (transfer.id)}
						<div class="flex items-center justify-between bg-surface-sunken rounded-lg px-3 py-2.5">
							<div class="min-w-0">
								<div class="text-xs text-ink-2 font-mono truncate">{transfer.id}</div>
								{#if transfer.name}<div class="text-sm text-ink-0">{transfer.name}</div>{/if}
								<div class="text-xs text-ink-2">{t('transferModal.volumeSummary', { id: transfer.volume_id.slice(0, 8) })}</div>
							</div>
							<button
								onclick={() => cancelTransfer(transfer.id)}
								disabled={cancellingId === transfer.id}
								class="ml-3 inline-flex items-center gap-1.5 text-xs text-red-400 hover:text-red-300 disabled:text-ink-3 border border-red-900 hover:border-red-700 disabled:border-line-2 px-2 py-1 rounded transition-colors shrink-0"
							>{#if cancellingId === transfer.id}<ActivityIndicator size="xs" tone="danger" />{/if}{cancellingId === transfer.id ? t('transferModal.cancelling') : t('transferModal.cancel')}</button>
						</div>
					{/each}
				</div>
			{/if}
			<div class="flex justify-end gap-3 mt-6">
				<button onclick={() => mode = 'menu'} class="px-4 py-2 text-sm text-ink-2 hover:text-ink-0 transition-colors">{t('transferModal.back')}</button>
				<button onclick={loadTransfers} disabled={loading} class="px-4 py-2 text-sm text-ink-2 hover:text-ink-0 border border-line-2 rounded-lg transition-colors">{t('transferModal.refresh')}</button>
			</div>
		{/if}
	</div>
</div>
