<script lang="ts">
	import type { AccessRule } from '$lib/types/fileStorage';

	let {
		shareProto, accessRules, accessLoading,
		onAdd, onRevoke,
		addingRule, addError,
		revokingId,
	}: {
		shareProto: string;
		accessRules: AccessRule[];
		accessLoading: boolean;
		onAdd: (form: { access_to: string; access_level: string }) => Promise<boolean>;
		onRevoke: (id: string) => Promise<void>;
		addingRule: boolean;
		addError: string;
		revokingId: string | null;
	} = $props();

	let showAddRule = $state(false);
	let ruleForm = $state({ access_to: '', access_level: 'ro' });
	let copiedKey = $state<string | null>(null);

	async function handleAdd() {
		const success = await onAdd(ruleForm);
		if (success) {
			ruleForm = { access_to: '', access_level: 'ro' };
			showAddRule = false;
		}
	}

	async function copyKey(key: string, id: string) {
		await navigator.clipboard.writeText(key);
		copiedKey = id;
		setTimeout(() => (copiedKey = null), 2000);
	}
</script>

<div class="bg-surface-base border border-line rounded-lg p-6 mb-4">
	<div class="flex items-center justify-between mb-4">
		<h2 class="text-sm font-semibold text-ink-2 uppercase tracking-wide">접근 규칙 {shareProto === 'NFS' ? '(IP)' : '(CephX)'}</h2>
		<button
			onclick={() => { showAddRule = !showAddRule; }}
			class="text-xs text-action-warm hover:text-action-warm-hover transition-colors"
		>
			{showAddRule ? '취소' : '+ 추가'}
		</button>
	</div>

	{#if showAddRule}
		<div class="bg-surface-sunken border border-line-2 rounded-lg p-4 mb-4">
			<div class="flex gap-3 items-end">
				<div class="flex-1">
					<label class="block text-xs text-ink-2 mb-1">{shareProto === 'NFS' ? 'IP / CIDR' : 'CephX ID'}
					<input
						bind:value={ruleForm.access_to}
						type="text"
						placeholder={shareProto === 'NFS' ? '예: 10.0.0.0/24' : '예: my-instance'}
						class="w-full bg-surface-base border border-line-2 rounded px-3 py-1.5 text-ink-0 text-sm focus:outline-none focus:border-action-warm font-mono mt-1"
					/>
				</label>
				</div>
				<div>
					<label class="block text-xs text-ink-2 mb-1">권한
					<select
						bind:value={ruleForm.access_level}
						class="bg-surface-base border border-line-2 rounded px-3 py-1.5 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1"
					>
						<option value="ro">읽기 전용 (ro)</option>
						<option value="rw">읽기/쓰기 (rw)</option>
					</select>
					</label>
				</div>
				<button
					onclick={handleAdd}
					disabled={addingRule || !ruleForm.access_to.trim()}
					class="px-4 py-1.5 bg-action-warm hover:bg-action-warm-hover disabled:bg-surface-selected disabled:text-ink-3 text-action-on-warm text-sm rounded transition-colors"
				>
					{addingRule ? '추가 중...' : '추가'}
				</button>
			</div>
			{#if addError}<p class="text-red-400 text-xs mt-2">{addError}</p>{/if}
		</div>
	{/if}

	{#if accessLoading}
		<p class="text-ink-3 text-sm text-center py-4">로딩 중...</p>
	{:else if accessRules.length === 0}
		<p class="text-ink-3 text-sm text-center py-4">접근 규칙이 없습니다</p>
	{:else}
		<div class="overflow-x-auto">
			<table class="w-full text-sm">
				<thead>
					<tr class="border-b border-line text-ink-3 text-xs uppercase tracking-wide">
						<th class="text-left py-2 pr-4">접근 대상</th>
						<th class="text-left py-2 pr-4">권한</th>
						<th class="text-left py-2 pr-4">상태</th>
						<th class="text-left py-2 pr-4">Access Key</th>
						<th class="text-right py-2"></th>
					</tr>
				</thead>
				<tbody>
					{#each accessRules as rule (rule.id)}
						<tr class="border-b border-line/50">
							<td class="py-2 pr-4 font-mono text-xs text-ink-2">{rule.access_to ?? '-'}</td>
							<td class="py-2 pr-4">
								<span class="text-xs px-1.5 py-0.5 rounded {rule.access_level === 'rw' ? 'bg-orange-900/30 text-orange-400' : 'bg-surface-sunken text-ink-2'}">
									{rule.access_level}
								</span>
							</td>
							<td class="py-2 pr-4 text-xs text-ink-2">{rule.state || '-'}</td>
							<td class="py-2 pr-4 text-xs font-mono">
								{#if rule.access_key}
									<div class="flex items-center gap-2">
										<span class="text-ink-3 truncate max-w-[120px]">{rule.access_key.slice(0, 16)}...</span>
										<button
											onclick={() => copyKey(rule.access_key!, rule.id)}
											class="text-xs px-1.5 py-0.5 rounded border transition-colors {copiedKey === rule.id ? 'border-green-700 text-green-400' : 'border-line-2 text-ink-2 hover:text-ink-1'}"
										>
											{copiedKey === rule.id ? '복사됨' : '복사'}
										</button>
									</div>
								{:else}
									<span class="text-ink-3">-</span>
								{/if}
							</td>
							<td class="py-2 text-right">
								<button
									onclick={() => onRevoke(rule.id)}
									disabled={revokingId === rule.id}
									class="text-xs text-red-400 hover:text-red-300 disabled:opacity-40 transition-colors"
								>
									{revokingId === rule.id ? '삭제 중...' : '삭제'}
								</button>
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{/if}
</div>
