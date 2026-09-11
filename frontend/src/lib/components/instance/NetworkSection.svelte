<script lang="ts">
	import { useInstanceDetailController } from '$lib/stores/instanceDetailController.svelte';
	import type { PortInfo } from '$lib/types/networks';

	const s = useInstanceDetailController();

	let showAddInterface = $state(false);
	let selectedNetId = $state('');
	let sgEditPortId = $state<string | null>(null);
	let sgEditSelected = $state<string[]>([]);
	let expandedSgRules = $state<Set<string>>(new Set());

	function toggleSgRules(sgId: string) {
		const next = new Set(expandedSgRules);
		next.has(sgId) ? next.delete(sgId) : next.add(sgId);
		expandedSgRules = next;
	}

	function toggleSg(sgId: string) {
		if (sgEditSelected.includes(sgId)) {
			sgEditSelected = sgEditSelected.filter(id => id !== sgId);
		} else {
			sgEditSelected = [...sgEditSelected, sgId];
		}
	}

	function openSgEdit(port: PortInfo) {
		sgEditPortId = port.id;
		sgEditSelected = [...(port.security_group_ids ?? [])];
	}

	async function handleSaveSgEdit() {
		if (!sgEditPortId) return;
		await s.saveSgEdit(sgEditPortId, sgEditSelected);
		sgEditPortId = null;
	}

	async function handleAttachInterface() {
		await s.attachInterface(selectedNetId);
		showAddInterface = false;
		selectedNetId = '';
	}
</script>

<div class="bg-surface-base border border-line rounded-lg p-6 mb-4">
	<div class="flex items-center justify-between mb-4">
		<h2 class="text-sm font-semibold text-ink-2 uppercase tracking-wide">인터페이스</h2>
		<button
			onclick={() => { showAddInterface = !showAddInterface; selectedNetId = ''; }}
			class="text-xs text-action-warm hover:text-action-warm-hover transition-colors"
		>
			{showAddInterface ? '닫기' : '+ 인터페이스 추가'}
		</button>
	</div>

	{#if showAddInterface}
		<div class="mb-4 bg-surface-sunken rounded-lg p-4">
			<p class="text-xs text-ink-2 mb-2">연결할 네트워크 선택</p>
			<div class="flex gap-2">
				<select
					bind:value={selectedNetId}
					class="flex-1 bg-surface-selected border border-line-2 text-ink-1 text-sm rounded px-2 py-1.5 focus:outline-none focus:border-action-warm"
				>
					<option value="">네트워크 선택...</option>
					{#each s.availableNetworks as net}
						<option value={net.id}>{net.name || net.id.slice(0, 12)}</option>
					{/each}
				</select>
				<button
					onclick={handleAttachInterface}
					disabled={!selectedNetId || s.actioning === 'attach-iface'}
					class="text-xs text-action-warm hover:text-action-warm-hover px-3 py-1.5 border border-action-warm hover:border-action-warm rounded transition-colors disabled:text-ink-3 disabled:border-line-2"
				>
					{s.actioning === 'attach-iface' ? '추가 중...' : '추가'}
				</button>
			</div>
		</div>
	{/if}

	{#if s.interfaces.length === 0}
		<p class="text-sm text-ink-3">인터페이스 정보 없음</p>
	{:else}
		<div class="space-y-4">
			{#each s.interfaces as iface}
				{@const ifaceFip = s.floatingIps.find(f => f.port_id === iface.id)}
				<div class="bg-surface-sunken/50 rounded-lg p-4">
					<div class="flex items-start justify-between mb-3">
						<div class="grid grid-cols-1 @3xl/panel:grid-cols-2 gap-x-6 gap-y-2 flex-1">
							<div>
								<dt class="text-xs text-ink-3 mb-0.5">포트 ID</dt>
								<dd class="text-xs text-ink-2 font-mono">{iface.id}</dd>
							</div>
							<div>
								<dt class="text-xs text-ink-3 mb-0.5">MAC 주소</dt>
								<dd class="text-xs text-ink-2 font-mono">{iface.mac_address}</dd>
							</div>
							<div>
								<dt class="text-xs text-ink-3 mb-0.5">네트워크</dt>
								<dd class="text-xs text-ink-2">{iface.network_id ? s.networkNameById(iface.network_id) : '-'}</dd>
							</div>
							<div>
								<dt class="text-xs text-ink-3 mb-0.5">상태</dt>
								<dd class="text-xs {iface.status === 'ACTIVE' ? 'text-green-400' : 'text-ink-2'}">{iface.status}</dd>
							</div>
							<div class="col-span-2">
								<dt class="text-xs text-ink-3 mb-1">IP 주소</dt>
								<dd class="flex flex-wrap gap-1.5 items-center">
									{#each iface.fixed_ips as fip}
										<span class="text-xs font-mono text-ink-2 bg-surface-selected px-1.5 py-0.5 rounded">{fip.ip_address}</span>
									{/each}
									{#if ifaceFip}
										<span class="text-xs font-mono text-green-300 bg-green-900/20 px-1.5 py-0.5 rounded">{ifaceFip.floating_ip_address}</span>
									{/if}
								</dd>
							</div>
						</div>
						<div class="ml-4 flex flex-col gap-1.5 shrink-0">
							{#if ifaceFip}
								<button
									onclick={() => s.releaseFloatingIp(ifaceFip.id)}
									disabled={!!s.actioning}
									class="text-xs text-orange-400 hover:text-orange-300 px-2 py-1 border border-orange-900 hover:border-orange-700 rounded transition-colors disabled:text-ink-3"
								>
									{s.actioning === 'fip-release-' + ifaceFip.id ? '해제 중...' : 'FIP 해제'}
								</button>
							{:else}
								<button
									onclick={() => s.assignFloatingIp(iface.id)}
									disabled={!!s.actioning}
									class="text-xs text-action-warm hover:text-action-warm-hover px-2 py-1 border border-action-warm hover:border-action-warm rounded transition-colors disabled:text-ink-3"
								>
									{s.actioning === 'fip-assign-' + iface.id ? '할당 중...' : '+ FIP'}
								</button>
							{/if}
							<button
								onclick={() => s.detachInterface(iface.id)}
								disabled={!!s.actioning}
								class="text-xs text-orange-400 hover:text-orange-300 px-2 py-1 border border-orange-900 hover:border-orange-700 rounded transition-colors disabled:text-ink-3"
							>
								{s.actioning === 'detach-iface-' + iface.id ? '제거 중...' : '제거'}
							</button>
						</div>
					</div>
					<!-- 보안 그룹 -->
					<div>
						<div class="flex items-center justify-between mb-1.5">
							<dt class="text-xs text-ink-3">보안 그룹</dt>
							<button
								onclick={() => openSgEdit(iface)}
								class="text-xs text-action-warm hover:text-action-warm-hover transition-colors"
							>
								편집
							</button>
						</div>
						{#if sgEditPortId === iface.id}
							<div class="bg-surface-selected rounded p-3 mt-2">
								<p class="text-xs text-ink-3 mb-2">이 프로젝트의 보안 그룹</p>
								<div class="space-y-1.5 mb-3 max-h-56 overflow-y-auto">
									{#each s.allSecurityGroups as sg}
										<div>
											<label class="flex items-center gap-2 cursor-pointer">
												<input
													type="checkbox"
													checked={sgEditSelected.includes(sg.id)}
													onchange={() => toggleSg(sg.id)}
													class="accent-blue-500"
												/>
												<span class="text-xs text-ink-2">{sg.name}</span>
												{#if sg.description}
													<span class="text-xs text-ink-3 truncate max-w-[100px]">— {sg.description}</span>
												{/if}
												<button
													type="button"
													onclick={() => toggleSgRules(sg.id)}
													class="text-xs text-ink-3 hover:text-ink-2 ml-auto shrink-0 transition-colors"
												>
													{expandedSgRules.has(sg.id) ? '▾' : '▸'} {sg.rules.length}개 규칙
												</button>
											</label>
											{#if expandedSgRules.has(sg.id)}
												<div class="ml-5 mt-1 mb-1 space-y-0.5 pl-2 border-l border-line-2">
													{#each sg.rules as rule}
														<div class="text-xs text-ink-3 font-mono">{s.formatRule(rule)}</div>
													{/each}
													{#if sg.rules.length === 0}
														<div class="text-xs text-ink-3 italic">규칙 없음</div>
													{/if}
												</div>
											{/if}
										</div>
									{/each}
								</div>
								<div class="flex gap-2">
									<button
										onclick={handleSaveSgEdit}
										disabled={s.actioning === 'sg-' + iface.id}
										class="text-xs text-action-warm hover:text-action-warm-hover px-2 py-1 border border-action-warm hover:border-action-warm rounded transition-colors disabled:text-ink-3"
									>
										{s.actioning === 'sg-' + iface.id ? '저장 중...' : '저장'}
									</button>
									<button
										onclick={() => { sgEditPortId = null; }}
										class="text-xs text-ink-2 hover:text-ink-1 px-2 py-1 border border-line-2 hover:border-line-2 rounded transition-colors"
									>
										취소
									</button>
								</div>
							</div>
						{:else}
							<dd class="flex flex-wrap gap-1.5">
								{#if !(iface.security_group_ids?.length)}
									<span class="text-xs text-ink-3">없음</span>
								{:else}
									{#each (iface.security_group_ids ?? []) as sgId}
										<span class="text-xs text-purple-300 bg-purple-900/30 px-1.5 py-0.5 rounded">{s.sgNameById(sgId)}</span>
									{/each}
								{/if}
							</dd>
						{/if}
					</div>
				</div>
			{/each}
		</div>
	{/if}
</div>
