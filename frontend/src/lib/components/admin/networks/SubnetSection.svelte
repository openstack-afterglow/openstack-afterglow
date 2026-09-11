<script lang="ts">
	import type { SubnetDetail } from '$lib/types/networks';

	let {
		subnets,
		onAdd,
		onSave,
		onDelete,
		deletingSubnetId,
		addError,
		saveError,
		addingSubnet,
		savingSubnet,
	}: {
		subnets: SubnetDetail[];
		onAdd: (form: { name: string; cidr: string; gateway: string; dhcp: boolean }) => Promise<boolean>;
		onSave: (subnetId: string, form: { name: string; gateway: string; dhcp: boolean }) => Promise<boolean>;
		onDelete: (subnetId: string, subnetName: string) => Promise<void>;
		deletingSubnetId: string | null;
		addError: string;
		saveError: string;
		addingSubnet: boolean;
		savingSubnet: boolean;
	} = $props();

	let showSubnetForm = $state(false);
	let subnetForm = $state({ name: '', cidr: '10.0.0.0/24', gateway: '', dhcp: true });
	let editingSubnetId = $state<string | null>(null);
	let editSubnetForm = $state({ name: '', gateway: '', dhcp: true });

	function startEditSubnet(subnet: SubnetDetail) {
		editingSubnetId = subnet.id;
		editSubnetForm = {
			name: subnet.name || '',
			gateway: subnet.gateway_ip ?? '',
			dhcp: subnet.dhcp_enabled,
		};
	}

	async function handleAdd() {
		const ok = await onAdd(subnetForm);
		if (ok) {
			showSubnetForm = false;
			subnetForm = { name: '', cidr: '10.0.0.0/24', gateway: '', dhcp: true };
		}
	}

	async function handleSave() {
		if (!editingSubnetId) return;
		const ok = await onSave(editingSubnetId, editSubnetForm);
		if (ok) editingSubnetId = null;
	}
</script>

<div class="bg-surface-base border border-line rounded-lg p-6 mb-4">
	<div class="flex items-center justify-between mb-4">
		<h2 class="text-sm font-semibold text-ink-2 uppercase tracking-wide">서브넷</h2>
		<button
			onclick={() => { showSubnetForm = !showSubnetForm; }}
			class="text-xs text-action-warm hover:text-action-warm-hover transition-colors"
		>
			{showSubnetForm ? '닫기' : '+ 서브넷 추가'}
		</button>
	</div>

	{#if showSubnetForm}
		<div class="mb-4 bg-surface-sunken rounded-lg p-4 space-y-3">
			<div class="grid grid-cols-2 gap-3">
				<div>
					<label class="block text-xs text-ink-2 mb-1">이름 (선택)
						<input
							bind:value={subnetForm.name}
							type="text"
							placeholder="my-subnet"
							class="w-full bg-surface-selected border border-line-2 rounded px-2.5 py-1.5 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1"
						/>
					</label>
				</div>
				<div>
					<label class="block text-xs text-ink-2 mb-1">CIDR
						<input
							bind:value={subnetForm.cidr}
							type="text"
							placeholder="10.0.0.0/24"
							class="w-full bg-surface-selected border border-line-2 rounded px-2.5 py-1.5 text-ink-0 text-sm font-mono focus:outline-none focus:border-action-warm mt-1"
						/>
					</label>
				</div>
				<div>
					<label class="block text-xs text-ink-2 mb-1">게이트웨이 (선택)
						<input
							bind:value={subnetForm.gateway}
							type="text"
							placeholder="10.0.0.1"
							class="w-full bg-surface-selected border border-line-2 rounded px-2.5 py-1.5 text-ink-0 text-sm font-mono focus:outline-none focus:border-action-warm mt-1"
						/>
					</label>
				</div>
				<div class="flex items-end pb-1.5">
					<label class="flex items-center gap-2 text-sm text-ink-2">
						<input type="checkbox" bind:checked={subnetForm.dhcp} class="rounded border-line-2" />
						DHCP 활성화
					</label>
				</div>
			</div>
			{#if addError}
				<p class="text-red-400 text-xs">{addError}</p>
			{/if}
			<div class="flex justify-end">
				<button
					onclick={handleAdd}
					disabled={addingSubnet}
					class="text-sm px-4 py-1.5 bg-action-warm hover:bg-action-warm-hover disabled:bg-surface-selected text-action-on-warm rounded transition-colors"
				>
					{addingSubnet ? '추가 중...' : '서브넷 추가'}
				</button>
			</div>
		</div>
	{/if}

	{#if subnets.length > 0}
		<div class="space-y-3">
			{#each subnets as subnet}
				{#if editingSubnetId === subnet.id}
					<div class="bg-surface-sunken rounded-lg p-4 space-y-3">
						<div class="grid grid-cols-2 gap-3">
							<div>
								<label class="block text-xs text-ink-2 mb-1">이름
									<input
										bind:value={editSubnetForm.name}
										type="text"
										class="w-full bg-surface-selected border border-line-2 rounded px-2.5 py-1.5 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1"
									/>
								</label>
							</div>
							<div>
								<label class="block text-xs text-ink-2 mb-1">게이트웨이
									<input
										bind:value={editSubnetForm.gateway}
										type="text"
										placeholder={subnet.gateway_ip ?? '없음'}
										class="w-full bg-surface-selected border border-line-2 rounded px-2.5 py-1.5 text-ink-0 text-sm font-mono focus:outline-none focus:border-action-warm mt-1"
									/>
								</label>
							</div>
							<div class="flex items-center">
								<label class="flex items-center gap-2 text-sm text-ink-2">
									<input type="checkbox" bind:checked={editSubnetForm.dhcp} class="rounded border-line-2" />
									DHCP 활성화
								</label>
							</div>
						</div>
						{#if saveError}
							<p class="text-red-400 text-xs">{saveError}</p>
						{/if}
						<div class="flex justify-end gap-2">
							<button
								onclick={() => { editingSubnetId = null; }}
								class="text-xs text-ink-2 hover:text-ink-1 px-3 py-1.5 transition-colors"
							>취소</button>
							<button
								onclick={handleSave}
								disabled={savingSubnet}
								class="text-xs px-4 py-1.5 bg-action-warm hover:bg-action-warm-hover disabled:bg-surface-selected text-action-on-warm rounded transition-colors"
							>{savingSubnet ? '저장 중...' : '저장'}</button>
						</div>
					</div>
				{:else}
					<div class="bg-surface-sunken/50 rounded-lg p-4">
						<div class="flex items-start justify-between mb-3">
							<div>
								<h3 class="text-sm font-medium text-ink-0">
									<a
										href="/admin/subnets/{subnet.id}"
										class="hover:text-accent hover:underline transition-colors"
									>
										{subnet.name || '(이름 없음)'}
									</a>
								</h3>
								<span class="text-xs text-ink-3 font-mono">{subnet.id}</span>
							</div>
							<div class="flex items-center gap-1">
								<button
									onclick={() => startEditSubnet(subnet)}
									class="text-xs text-action-warm hover:text-action-warm-hover px-2 py-1 border border-action-warm hover:border-action-warm rounded transition-colors"
								>편집</button>
								<button
									onclick={() => onDelete(subnet.id, subnet.name)}
									disabled={deletingSubnetId === subnet.id}
									class="text-xs text-red-400 hover:text-red-300 disabled:text-ink-3 px-2 py-1 border border-red-900 hover:border-red-700 disabled:border-line-2 rounded transition-colors"
								>{deletingSubnetId === subnet.id ? '삭제 중...' : '삭제'}</button>
							</div>
						</div>
						<dl class="grid grid-cols-2 md:grid-cols-4 gap-x-6 gap-y-2">
							<div>
								<dt class="text-xs text-ink-3 mb-0.5">CIDR</dt>
								<dd class="text-sm text-ink-2 font-mono">{subnet.cidr}</dd>
							</div>
							<div>
								<dt class="text-xs text-ink-3 mb-0.5">게이트웨이</dt>
								<dd class="text-sm text-ink-2 font-mono">{subnet.gateway_ip ?? '-'}</dd>
							</div>
							<div>
								<dt class="text-xs text-ink-3 mb-0.5">DHCP</dt>
								<dd>
									{#if subnet.dhcp_enabled}
										<span class="px-1.5 py-0.5 bg-green-900/30 text-green-400 rounded text-xs">활성</span>
									{:else}
										<span class="px-1.5 py-0.5 bg-surface-sunken text-ink-3 rounded text-xs">비활성</span>
									{/if}
								</dd>
							</div>
							<div>
								<dt class="text-xs text-ink-3 mb-0.5">IP 버전</dt>
								<dd class="text-sm text-ink-2">IPv4</dd>
							</div>
						</dl>
					</div>
				{/if}
			{/each}
		</div>
	{:else}
		<p class="text-sm text-ink-3">서브넷 없음</p>
	{/if}
</div>
