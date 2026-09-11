<script lang="ts">
	import { api, ApiError } from '$lib/api/client';
	import type { Network } from '$lib/types/networks';

	interface Props {
		open: boolean;
		networks: Network[];
		token?: string;
		projectId?: string;
		onAllocated?: () => void;
		onClose?: () => void;
	}

	let { open = $bindable(), networks, token, projectId, onAllocated, onClose }: Props = $props();

	const externalNetworks = $derived(networks.filter((n) => n.is_external));

	let selectedNetworkId = $state('');
	let allocating = $state(false);
	let allocError = $state('');

	$effect(() => {
		if (open) {
			allocError = '';
			allocating = false;
			// 외부 네트워크가 하나뿐이면 자동 선택
			if (externalNetworks.length === 1) {
				selectedNetworkId = externalNetworks[0].id;
			} else {
				selectedNetworkId = '';
			}
		}
	});

	function close() {
		open = false;
		onClose?.();
	}

	async function allocate() {
		if (!selectedNetworkId) {
			allocError = '외부 네트워크를 선택하세요.';
			return;
		}
		allocating = true;
		allocError = '';
		try {
			await api.post(
				'/api/v1/networks/floating-ips',
				{ floating_network_id: selectedNetworkId },
				token,
				projectId
			);
			close();
			onAllocated?.();
		} catch (e) {
			allocError = e instanceof ApiError ? e.message : 'Floating IP 할당 실패';
		} finally {
			allocating = false;
		}
	}
</script>

{#if open}
	<div
		class="fixed inset-0 bg-surface-scrim/60 flex items-center justify-center z-50"
		onclick={close}
		role="dialog"
		aria-modal="true"
		tabindex="-1"
		onkeydown={(e) => e.key === 'Escape' && close()}
	>
		<div
			class="bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-sm mx-4 shadow-[var(--shadow-restraint)]"
			onclick={(e) => e.stopPropagation()}
			role="none"
			onkeydown={(e) => e.stopPropagation()}
		>
			<h2 class="text-lg font-semibold text-ink-0 mb-5">Floating IP 할당</h2>

			{#if externalNetworks.length === 0}
				<p class="text-sm text-ink-2 mb-4">
					사용 가능한 외부 네트워크가 없습니다. 라우터에 외부 게이트웨이가 연결되어 있는지 확인하세요.
				</p>
			{:else if externalNetworks.length === 1}
				<p class="text-sm text-ink-2 mb-4">
					외부 네트워크 <span class="text-ink-0 font-mono">{externalNetworks[0].name || externalNetworks[0].id.slice(0, 8)}</span>에서 Floating IP를 할당합니다.
				</p>
			{:else}
				<div class="mb-4">
					<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide" for="field-floatingipallocatemodal-91">외부 네트워크</label>
					<select id="field-floatingipallocatemodal-91"
						bind:value={selectedNetworkId}
						class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm"
					>
						<option value="">-- 선택 --</option>
						{#each externalNetworks as net}
							<option value={net.id}>{net.name || net.id.slice(0, 8)}</option>
						{/each}
					</select>
				</div>
			{/if}

			{#if allocError}
				<div class="mb-3 text-red-400 text-xs">{allocError}</div>
			{/if}

			<div class="flex justify-end gap-3">
				<button
					onclick={close}
					class="px-4 py-2 text-sm text-ink-2 hover:text-ink-0 transition-colors"
				>취소</button>
				<button
					onclick={allocate}
					disabled={allocating || externalNetworks.length === 0}
					class="px-5 py-2 bg-action-warm hover:bg-action-warm-hover disabled:bg-surface-selected disabled:text-ink-3 text-action-on-warm text-sm font-medium rounded-lg transition-colors"
				>{allocating ? '할당 중...' : 'IP 할당'}</button>
			</div>
		</div>
	</div>
{/if}
