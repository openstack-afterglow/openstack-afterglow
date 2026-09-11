<script lang="ts">
	import type { SecurityGroup } from '$lib/types/securityGroup';
	import AddRuleForm from './AddRuleForm.svelte';

	let {
		group,
		addRuleOpen = $bindable(),
		addingRule,
		addError,
		ruleForm = $bindable(),
		onAddRule,
		onDeleteRule,
		onDeleteGroup,
		onCloseMobile,
	}: {
		group: SecurityGroup;
		addRuleOpen: boolean;
		addingRule: boolean;
		addError: string;
		ruleForm: { direction: string; protocol: string; port_range_min: string; port_range_max: string; remote_ip_prefix: string; ethertype: string };
		onAddRule: () => Promise<void>;
		onDeleteRule: (ruleId: string) => Promise<void>;
		onDeleteGroup: () => Promise<void>;
		onCloseMobile: () => void;
	} = $props();
</script>

<!-- 모바일: 전체화면 오버레이 / 데스크톱: 인라인 -->
<div class="security-group-rules fixed inset-0 z-50 bg-surface-canvas overflow-y-auto p-4 sm:static sm:inset-auto sm:z-auto sm:bg-surface-base sm:border sm:border-line sm:rounded-lg sm:p-5 sm:overflow-visible">
	<div class="flex items-center mb-3.5">
		<button type="button" aria-label="보안 그룹 목록으로 돌아가기" onclick={onCloseMobile} class="sm:hidden mr-2 text-ink-2 hover:text-ink-0 p-1">
			<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7"/></svg>
		</button>
		<div>
			<div class="text-ink-0 text-[15px] font-semibold font-mono">{group.name}</div>
			{#if group.description}
				<div class="text-[11px] text-ink-3 mt-0.5">{group.description}</div>
			{/if}
		</div>
		<div class="ml-auto flex gap-2">
			<button
				onclick={onDeleteGroup}
				class="px-3 py-1.5 text-[13px] text-red-400 hover:text-red-300 border border-red-900 hover:border-red-700 rounded-lg transition-colors"
			>삭제</button>
			<button
				onclick={() => { addRuleOpen = !addRuleOpen; }}
				class="px-3 py-1.5 text-[13px] bg-action-warm hover:bg-action-warm-hover text-action-on-warm font-medium rounded-lg transition-colors"
			>+ 규칙 추가</button>
		</div>
	</div>

	<!-- Add rule form -->
	{#if addRuleOpen}
		<AddRuleForm
			bind:ruleForm
			adding={addingRule}
			error={addError}
			onAdd={onAddRule}
			onCancel={() => { addRuleOpen = false; }}
		/>
	{/if}

	<!-- Rules table -->
	{#if group.rules.length === 0}
		<div class="text-center py-10 text-ink-3 text-sm">규칙이 없습니다</div>
	{:else}
		<div class="bg-[#0B1220] border border-line rounded-lg overflow-hidden">
			<div class="grid grid-cols-[120px_120px_1fr_1.4fr_80px] px-4 py-2.5 border-b border-line text-[11px] uppercase tracking-wider text-ink-3 font-medium">
				<div>방향</div>
				<div>프로토콜</div>
				<div>포트</div>
				<div>출발지/대상</div>
				<div></div>
			</div>
			{#each group.rules as rule, i (rule.id)}
				<div class="grid grid-cols-[120px_120px_1fr_1.4fr_80px] px-4 py-3 text-[13px] items-center {i < group.rules.length - 1 ? 'border-b border-line' : ''}">
					<div>
						<span class="text-[11px] px-2 py-0.5 rounded-md border font-medium
							{rule.direction === 'ingress' ? 'bg-emerald-900/25 border-emerald-800 text-emerald-400' : 'bg-surface-selected/25 border-action-warm text-action-warm'}">
							{rule.direction === 'ingress' ? '↓ ingress' : '↑ egress'}
						</span>
					</div>
					<div class="text-ink-1 font-mono text-xs uppercase">{rule.protocol ?? 'any'}</div>
					<div class="text-ink-1 font-mono text-xs">
						{rule.port_range_min
							? rule.port_range_min + (rule.port_range_max !== rule.port_range_min ? '-' + rule.port_range_max : '')
							: '—'}
					</div>
					<div class="text-ink-2 font-mono text-xs">{rule.remote_ip_prefix ?? '0.0.0.0/0'}</div>
					<div class="text-right">
						<button
							onclick={() => onDeleteRule(rule.id)}
							class="text-xs text-red-400 hover:text-red-300 px-2 py-1 rounded border border-red-900 hover:border-red-700 transition-colors"
						>제거</button>
					</div>
				</div>
			{/each}
		</div>
	{/if}
</div>

<style>
	@media (min-width: 640px) {
		.security-group-rules {
			position: static;
			inset: auto;
			z-index: auto;
			overflow: visible;
			min-width: 0;
		}
	}
</style>
