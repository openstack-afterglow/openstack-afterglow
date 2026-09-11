<script lang="ts">
	import Button from '$lib/components/ui/Button.svelte';
	import StatusChip from '$lib/components/ui/StatusChip.svelte';
	import { useFileStorageDetailController } from '$lib/stores/fileStorageDetailController.svelte';

	const s = useFileStorageDetailController();
</script>

<div class="bg-surface-base border border-line rounded-lg p-5 mb-4">
	<div class="flex items-center justify-between mb-3">
		<div class="flex items-center gap-2">
			<h3 class="text-xs font-semibold text-ink-2 uppercase tracking-wide">
				접근 규칙 {s.fileStorage!.share_proto === 'NFS' ? '(IP)' : '(CephX)'}
			</h3>
			{#if s.fileStorage!.access_rules_status}
				<StatusChip status={s.fileStorage!.access_rules_status} class="text-[10px]" />
			{/if}
		</div>
		<button
			onclick={() => { s.showAddRule = !s.showAddRule; }}
			class="text-xs text-action-warm hover:text-action-warm-hover transition-colors"
		>
			{s.showAddRule ? '취소' : '+ 추가'}
		</button>
	</div>

	{#if s.showAddRule}
		<div class="bg-surface-sunken border border-line-2 rounded-lg p-4 mb-4">
			<div class="flex gap-3 items-end">
				<div class="flex-1">
					<label class="block text-xs text-ink-2 mb-1">
						{s.fileStorage!.share_proto === 'NFS' ? 'IP / CIDR' : 'CephX ID'}
						<input
							bind:value={s.ruleForm.access_to}
							type="text"
							placeholder={s.fileStorage!.share_proto === 'NFS' ? '예: 10.0.0.0/24' : '예: my-instance'}
							class="w-full bg-surface-base border border-line-2 rounded px-3 py-1.5 text-ink-0 text-sm focus:outline-none focus:border-action-warm font-mono mt-1"
						/>
					</label>
				</div>
				<div>
					<label class="block text-xs text-ink-2 mb-1">
						권한
						<select
							bind:value={s.ruleForm.access_level}
							class="bg-surface-base border border-line-2 rounded px-3 py-1.5 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1"
						>
							<option value="ro">읽기 전용 (ro)</option>
							<option value="rw">읽기/쓰기 (rw)</option>
						</select>
					</label>
				</div>
				<Button onclick={() => s.addAccessRule()} disabled={s.addingRule || !s.ruleForm.access_to.trim()} size="sm">
					{s.addingRule ? '추가 중...' : '추가'}
				</Button>
			</div>
			{#if s.ruleError}<p class="text-red-400 text-xs mt-2">{s.ruleError}</p>{/if}
		</div>
	{/if}

	{#if s.accessLoading}
		<p class="text-ink-3 text-sm text-center py-4">로딩 중...</p>
	{:else if s.accessError}
		<div class="flex items-center gap-2 py-3 px-3 bg-red-900/20 border border-red-800/50 rounded-md">
			<span class="text-red-400 text-xs">{s.accessError}</span>
		</div>
	{:else if s.accessRules.length === 0}
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
					{#each s.accessRules as rule (rule.id)}
						<tr class="border-b border-line/50">
							<td class="py-2 pr-4 font-mono text-xs text-ink-2">{rule.access_to ?? '-'}</td>
							<td class="py-2 pr-4">
								<span class="text-xs px-1.5 py-0.5 rounded {rule.access_level === 'rw' ? 'bg-orange-900/30 text-orange-400' : 'bg-surface-sunken text-ink-2'}">{rule.access_level}</span>
							</td>
							<td class="py-2 pr-4">
								<StatusChip status={rule.state || 'unknown'} class="text-[10px]" />
							</td>
							<td class="py-2 pr-4 text-xs font-mono">
								{#if rule.access_key}
									<div class="flex items-center gap-2">
										<span class="text-ink-3 truncate max-w-[120px]">{rule.access_key.slice(0, 16)}...</span>
										<button
											onclick={() => s.copyKey(rule.access_key!, rule.id)}
											class="text-xs px-1.5 py-0.5 rounded border transition-colors {s.copiedKey === rule.id ? 'border-green-700 text-green-400' : 'border-line-2 text-ink-2 hover:text-ink-1'}"
										>
											{s.copiedKey === rule.id ? '복사됨' : '복사'}
										</button>
									</div>
								{:else}
									<span class="text-ink-3">-</span>
								{/if}
							</td>
							<td class="py-2 text-right">
								<button
									onclick={() => s.revokeAccessRule(rule.id)}
									disabled={s.revokingId === rule.id}
									class="text-xs text-red-400 hover:text-red-300 disabled:opacity-40 transition-colors"
								>
									{s.revokingId === rule.id ? '삭제 중...' : '삭제'}
								</button>
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{/if}
</div>
