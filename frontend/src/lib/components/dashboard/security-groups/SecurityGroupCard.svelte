<script lang="ts">
	import SecurityGroupRuleForm from './SecurityGroupRuleForm.svelte';
	import SecurityGroupRuleTable from './SecurityGroupRuleTable.svelte';

	interface SecurityGroupRule {
		id: string;
		direction: string;
		protocol: string | null;
		port_range_min: number | null;
		port_range_max: number | null;
		remote_ip_prefix: string | null;
		ethertype: string;
	}

	interface SecurityGroup {
		id: string;
		name: string;
		description: string;
		rules: SecurityGroupRule[];
	}

	let {
		sg,
		onDelete,
		onAddRule,
		onDeleteRule,
	}: {
		sg: SecurityGroup;
		onDelete: (id: string, name: string) => Promise<void>;
		onAddRule: (
			sgId: string,
			form: {
				direction: string;
				protocol: string;
				port_range_min: string;
				port_range_max: string;
				remote_ip_prefix: string;
				ethertype: string;
			}
		) => Promise<string | true>;
		onDeleteRule: (sgId: string, ruleId: string) => Promise<void>;
	} = $props();

	let expanded = $state(false);
	let showAddRule = $state(false);
	let submitting = $state(false);

	async function handleAddRule(form: {
		direction: string;
		protocol: string;
		port_range_min: string;
		port_range_max: string;
		remote_ip_prefix: string;
		ethertype: string;
	}): Promise<string | true> {
		submitting = true;
		const result = await onAddRule(sg.id, form);
		submitting = false;
		if (result === true) showAddRule = false;
		return result;
	}

	function handleCancelRule() {
		showAddRule = false;
	}
</script>

<div class="bg-surface-sunken/50 border border-line-2 rounded-lg overflow-hidden">
	<!-- SG 헤더 -->
	<div class="flex items-center gap-3 px-4 py-3">
		<button
			onclick={() => (expanded = !expanded)}
			class="flex items-center gap-2 flex-1 text-left min-w-0"
		>
			<span class="text-sm font-medium text-ink-0 truncate">{sg.name}</span>
			{#if sg.description}
				<span class="text-xs text-ink-3 truncate">{sg.description}</span>
			{/if}
			<span class="text-xs text-ink-3 ml-auto shrink-0"
				>{sg.rules.length}개 규칙 {expanded ? '▾' : '▸'}</span
			>
		</button>
		<button
			onclick={() => { showAddRule = !showAddRule; }}
			class="text-xs text-action-warm hover:text-action-warm-hover px-2 py-1 border border-action-warm hover:border-action-warm rounded transition-colors shrink-0"
		>+ 규칙</button>
		<button
			onclick={() => onDelete(sg.id, sg.name)}
			class="text-xs text-red-400 hover:text-red-300 px-2 py-1 border border-red-900 hover:border-red-700 rounded transition-colors shrink-0"
		>삭제</button>
	</div>

	<!-- 규칙 추가 폼 -->
	{#if showAddRule}
		<SecurityGroupRuleForm
			{submitting}
			onSubmit={handleAddRule}
			onCancel={handleCancelRule}
		/>
	{/if}

	<!-- 규칙 목록 -->
	{#if expanded}
		<SecurityGroupRuleTable
			rules={sg.rules}
			onDelete={(ruleId) => onDeleteRule(sg.id, ruleId)}
		/>
	{/if}
</div>
