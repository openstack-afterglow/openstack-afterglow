<script lang="ts">
	import type { SecurityGroup, SecurityGroupRuleDraft } from '$lib/types/securityGroup';

	let {
		ruleForm = $bindable(),
		targetType = $bindable(),
		groups,
		originalRuleId,
		adding,
		canAdd,
		error,
		onAdd,
		onCancel,
		onRemoveOriginal,
	}: {
		ruleForm: SecurityGroupRuleDraft;
		targetType: 'cidr' | 'group';
		groups: SecurityGroup[];
		originalRuleId: string | null;
		adding: boolean;
		canAdd: boolean;
		error: string;
		onAdd: () => Promise<void>;
		onCancel: () => void;
		onRemoveOriginal: () => Promise<void>;
	} = $props();

	const control = 'w-full bg-surface-sunken border border-line-2 rounded-md px-2 py-1.5 text-sm text-ink-1 focus:border-action-warm focus:outline-none';
</script>

<div class="border-t border-line bg-surface-base p-3 md:p-4" data-testid="inline-rule-form">
	<p class="text-sm font-medium text-ink-0 mb-3">{originalRuleId ? '규칙 값 복사' : '새 규칙'}</p>
	{#if originalRuleId}
		<p class="text-xs text-ink-2 mb-3">Neutron 규칙은 직접 수정할 수 없습니다. 기존 규칙을 제거한 뒤 복사한 값으로 새 규칙을 추가하세요. 제거와 추가 사이에는 접근 정책이 달라집니다.</p>
	{/if}
	<div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
		<label class="text-xs text-ink-2">방향
			<select bind:value={ruleForm.direction} class="{control} mt-1">
				<option value="ingress">인바운드</option>
				<option value="egress">아웃바운드</option>
			</select>
		</label>
		<label class="text-xs text-ink-2">IP 버전
			<select bind:value={ruleForm.ethertype} class="{control} mt-1">
				<option value="IPv4">IPv4</option>
				<option value="IPv6">IPv6</option>
			</select>
		</label>
		<label class="text-xs text-ink-2">프로토콜
			<select bind:value={ruleForm.protocol} class="{control} mt-1">
				<option value="">전체 (Any)</option>
				<option value="tcp">TCP</option>
				<option value="udp">UDP</option>
				<option value="icmp">ICMP</option>
			</select>
		</label>
		<label class="text-xs text-ink-2">원격 대상 유형
			<select bind:value={targetType} onchange={() => { ruleForm.remote_ip_prefix = ''; ruleForm.remote_group_id = ''; }} class="{control} mt-1">
				<option value="cidr">IP 대역 (CIDR)</option>
				<option value="group">보안 그룹</option>
			</select>
		</label>
		{#if targetType === 'cidr'}
			<label class="text-xs text-ink-2 md:col-span-2">원격 IP 대역
				<input bind:value={ruleForm.remote_ip_prefix} placeholder={ruleForm.ethertype === 'IPv6' ? '비우면 ::/0' : '비우면 0.0.0.0/0'} class="{control} mt-1 placeholder-ink-3" />
			</label>
		{:else}
			<label class="text-xs text-ink-2 md:col-span-2">원격 보안 그룹
				<select bind:value={ruleForm.remote_group_id} class="{control} mt-1">
					<option value="">보안 그룹 선택</option>
					{#each groups as group (group.id)}
						<option value={group.id}>{group.name} ({group.id.slice(0, 8)})</option>
					{/each}
				</select>
			</label>
		{/if}
		{#if ruleForm.protocol === 'tcp' || ruleForm.protocol === 'udp'}
			<label class="text-xs text-ink-2">시작 포트
				<input bind:value={ruleForm.port_range_min} type="text" inputmode="numeric" placeholder="1–65535" class="{control} mt-1 placeholder-ink-3" />
			</label>
			<label class="text-xs text-ink-2">끝 포트
				<input bind:value={ruleForm.port_range_max} type="text" inputmode="numeric" placeholder="끝 포트" aria-describedby="rule-end-port-help" class="{control} mt-1 placeholder-ink-3" />
				<span id="rule-end-port-help" class="block text-xs text-ink-2 mt-1">비우면 시작 포트와 동일</span>
			</label>
		{/if}
	</div>
	{#if error}<p role="alert" class="text-xs text-state-danger-text mt-3">{error}</p>{/if}
	<div class="flex flex-wrap gap-2 mt-3">
		{#if originalRuleId}
			<button type="button" onclick={onRemoveOriginal} disabled={adding} class="text-xs text-state-danger-text border border-state-danger rounded-md px-3 py-1.5 disabled:opacity-50">기존 규칙 제거</button>
		{/if}
		<button type="button" onclick={onAdd} disabled={adding || !canAdd} class="text-xs bg-action-warm text-action-on-warm rounded-md px-3 py-1.5 disabled:opacity-50">{adding ? '추가 중...' : '새 규칙 추가'}</button>
		<button type="button" onclick={onCancel} class="text-xs text-ink-2 border border-line-2 rounded-md px-3 py-1.5">취소</button>
	</div>
	{#if !canAdd}<p class="text-xs text-ink-2 mt-2">규칙 쿼터가 가득 찼거나 확인되지 않았습니다. 기존 규칙을 제거한 뒤 쿼터를 새로 확인하세요.</p>{/if}
</div>
