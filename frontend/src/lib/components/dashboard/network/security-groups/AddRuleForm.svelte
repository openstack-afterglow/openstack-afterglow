<script lang="ts">
	let {
		ruleForm = $bindable(),
		adding,
		error,
		onAdd,
		onCancel,
	}: {
		ruleForm: { direction: string; protocol: string; port_range_min: string; port_range_max: string; remote_ip_prefix: string; ethertype: string };
		adding: boolean;
		error: string;
		onAdd: () => Promise<void>;
		onCancel: () => void;
	} = $props();
</script>

<div class="mb-4 p-3.5 bg-[#0B1220] border border-line rounded-lg">
	<p class="text-xs text-ink-3 mb-2.5">규칙 추가</p>
	<div class="grid grid-cols-2 gap-2 mb-2 md:grid-cols-4">
		<select bind:value={ruleForm.direction}
			class="bg-surface-selected border border-line-2 rounded px-2 py-1 text-xs text-ink-1 focus:border-action-warm">
			<option value="ingress">인바운드</option>
			<option value="egress">아웃바운드</option>
		</select>
		<select bind:value={ruleForm.ethertype}
			class="bg-surface-selected border border-line-2 rounded px-2 py-1 text-xs text-ink-1 focus:border-action-warm">
			<option value="IPv4">IPv4</option>
			<option value="IPv6">IPv6</option>
		</select>
		<select bind:value={ruleForm.protocol}
			class="bg-surface-selected border border-line-2 rounded px-2 py-1 text-xs text-ink-1 focus:border-action-warm">
			<option value="">전체 (Any)</option>
			<option value="tcp">TCP</option>
			<option value="udp">UDP</option>
			<option value="icmp">ICMP</option>
		</select>
		<input bind:value={ruleForm.remote_ip_prefix} placeholder="원격 IP (예: 0.0.0.0/0)"
			class="bg-surface-selected border border-line-2 rounded px-2 py-1 text-xs text-ink-1 placeholder-ink-3 focus:border-action-warm focus:outline-none" />
	</div>
	{#if ruleForm.protocol === 'tcp' || ruleForm.protocol === 'udp'}
		<div class="grid grid-cols-2 gap-2 mb-2 max-w-xs">
			<input bind:value={ruleForm.port_range_min} placeholder="시작 포트"
				class="bg-surface-selected border border-line-2 rounded px-2 py-1 text-xs text-ink-1 placeholder-ink-3 focus:border-action-warm focus:outline-none" />
			<input bind:value={ruleForm.port_range_max} placeholder="끝 포트"
				class="bg-surface-selected border border-line-2 rounded px-2 py-1 text-xs text-ink-1 placeholder-ink-3 focus:border-action-warm focus:outline-none" />
		</div>
	{/if}
	{#if error}
		<p class="text-xs text-red-400 mb-2">{error}</p>
	{/if}
	<div class="flex gap-2">
		<button onclick={onAdd} disabled={adding}
			class="text-xs text-action-warm hover:text-action-warm-hover px-2 py-1 border border-action-warm hover:border-action-warm rounded transition-colors disabled:text-ink-3">
			{adding ? '추가 중...' : '추가'}
		</button>
		<button onclick={onCancel}
			class="text-xs text-ink-2 hover:text-ink-1 px-2 py-1 border border-line-2 rounded transition-colors">취소</button>
	</div>
</div>
