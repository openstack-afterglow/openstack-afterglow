<script lang="ts">
	import type { SecurityGroup, SecurityGroupInstance, SecurityGroupRule, SecurityGroupRuleDraft } from '$lib/types/securityGroup';
	import AddRuleForm from './AddRuleForm.svelte';
	import { t } from '$lib/i18n/ns/network-pages';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import AnimatedNumber from '$lib/components/ui/AnimatedNumber.svelte';

	let {
		group,
		groups,
		instances,
		instancesError,
		instancesLoading,
		addRuleOpen,
		originalRuleId,
		addingRule,
		canAddRule,
		addError,
		ruleForm = $bindable(),
		targetType = $bindable(),
		onStartAdd,
		onEditRule,
		onCancelAdd,
		onAddRule,
		onRemoveOriginal,
		onDeleteRule,
		onDeleteGroup,
		onSelectGroup,
		onRetryInstances,
		onCloseMobile,
	}: {
		group: SecurityGroup;
		groups: SecurityGroup[];
		instances: SecurityGroupInstance[];
		instancesError: string;
		instancesLoading: boolean;
		addRuleOpen: boolean;
		originalRuleId: string | null;
		addingRule: boolean;
		canAddRule: boolean;
		addError: string;
		ruleForm: SecurityGroupRuleDraft;
		targetType: 'cidr' | 'group';
		onStartAdd: () => void;
		onEditRule: (rule: SecurityGroupRule) => void;
		onCancelAdd: () => void;
		onAddRule: () => Promise<void>;
		onRemoveOriginal: () => Promise<void>;
		onDeleteRule: (ruleId: string) => Promise<void>;
		onDeleteGroup: () => Promise<void>;
		onSelectGroup: (id: string) => void;
		onRetryInstances: () => Promise<void>;
		onCloseMobile: () => void;
	} = $props();

	function targetName(id: string): string {
		return groups.find((item) => item.id === id)?.name ?? id;
	}
</script>

<!-- 모바일: 전체화면 오버레이 / 태블릿·데스크톱: 인라인. 모바일에서 fixed 레이어이므로 opacity 진입만 쓴다. -->
<div class="security-group-rules motion-fade fixed inset-0 bg-surface-canvas overflow-y-auto p-4 md:static md:inset-auto md:bg-surface-base md:border md:border-line md:rounded-lg md:p-5 md:overflow-visible">
	<div class="flex items-center mb-4 gap-2">
		<button type="button" aria-label={t('securityGroupRules.backToList')} onclick={onCloseMobile} class="md:hidden text-ink-2 hover:text-ink-0 p-2">
			<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7"/></svg>
		</button>
		<div class="min-w-0">
			<div class="text-ink-0 text-sm font-semibold font-mono truncate">{group.name}</div>
			{#if group.description}<div class="text-xs text-ink-2 mt-0.5">{group.description}</div>{/if}
		</div>
		{#if group.name !== 'default'}
			<button type="button" onclick={onDeleteGroup} class="ml-auto text-xs text-state-danger-text border border-state-danger rounded-md px-3 py-1.5 shrink-0">{t('securityGroupRules.delete')}</button>
		{/if}
	</div>

	<section class="border border-line rounded-lg p-3 mb-4" aria-label={t('securityGroupRules.instancesLabel')}>
		<h2 class="text-sm font-medium text-ink-0 mb-2">{instancesError || instancesLoading ? t('securityGroupRules.instancesTitle') : t('securityGroupRules.instancesCount', { count: instances.length })}</h2>
		{#if instancesLoading}
			<ActivityIndicator size="xs" label={t('securityGroupRules.instancesLoading')} />
		{:else if instancesError}
			<p role="alert" class="text-xs text-state-danger-text">{instancesError} <button type="button" onclick={onRetryInstances} class="underline">{t('securityGroupRules.retryInstances')}</button></p>
		{:else if instances.length === 0}
			<p class="text-xs text-ink-2">{t('securityGroupRules.noInstances')}</p>
		{:else}
			<ul class="flex flex-wrap gap-2">
				{#each instances as instance (instance.id)}
					<li><a class="inline-flex items-center gap-1.5 border border-line-2 rounded-md px-2 py-1 text-xs text-accent hover:underline" href={`/dashboard/compute/instances/${instance.id}`} title={instance.id}>{instance.name || instance.id} <span class="text-ink-2">{instance.status}</span></a></li>
				{/each}
			</ul>
		{/if}
	</section>

	<section aria-label={t('securityGroupRules.rulesLabel')} class="border border-line rounded-lg overflow-hidden bg-surface-base">
		<div class="flex items-center justify-between gap-2 px-3 py-2 border-b border-line">
			<h2 class="text-sm font-medium text-ink-0"><AnimatedNumber value={group.rules.length} format={(value) => t('securityGroupRules.rulesCount', { count: Math.round(value) })} /></h2>
			<button type="button" onclick={onStartAdd} aria-expanded={addRuleOpen} class="text-xs text-warm-text border border-action-warm rounded-md px-2 py-1.5 shrink-0">{t('securityGroupRules.add')}</button>
		</div>
		<div class="overflow-x-auto">
			<div class="min-w-[42rem]">
				<div class="grid grid-cols-[6.5rem_3.5rem_5rem_5rem_minmax(8rem,1fr)_8rem] gap-2 px-3 py-2.5 border-b border-line text-xs text-ink-2 font-medium items-center">
					<div>{t('securityGroupRules.direction')}</div><div>{t('securityGroupRules.ipVersion')}</div><div>{t('securityGroupRules.protocol')}</div><div>{t('securityGroupRules.port')}</div><div>{t('securityGroupRules.sourceTarget')}</div><div>{t('securityGroupRules.actions')}</div>
				</div>
				{#if group.rules.length === 0}
					<div class="text-xs text-ink-2 px-3 py-5">{t('securityGroupRules.noRules')}</div>
				{/if}
				<div class="motion-stagger">
				{#each group.rules as rule (rule.id)}
					<div class="grid grid-cols-[6.5rem_3.5rem_5rem_5rem_minmax(8rem,1fr)_8rem] gap-2 px-3 py-2.5 text-xs items-center border-b border-line">
						<div><span class="text-state-info-text">{rule.direction === 'ingress' ? t('securityGroupRules.ingress') : t('securityGroupRules.egress')}</span></div>
						<div class="text-ink-1 font-mono">{rule.ethertype}</div>
						<div class="text-ink-1 font-mono uppercase">{rule.protocol ?? t('securityGroupRules.anyProtocol')}</div>
						<div class="text-ink-1 font-mono">{rule.port_range_min != null ? rule.port_range_min + (rule.port_range_max !== rule.port_range_min ? '-' + rule.port_range_max : '') : '—'}</div>
						<div class="min-w-0 text-ink-1 font-mono">
							{#if rule.remote_group_id}
								<button type="button" onclick={() => onSelectGroup(rule.remote_group_id!)} title={rule.remote_group_id} class="text-accent hover:underline text-left truncate max-w-full">{t('securityGroupRules.remoteGroup', { name: targetName(rule.remote_group_id) })}</button>
							{:else}
								<span title={rule.remote_ip_prefix ?? ''}>{rule.remote_ip_prefix ?? (rule.ethertype === 'IPv6' ? '::/0' : '0.0.0.0/0')}</span>
							{/if}
						</div>
						<div class="flex gap-2 justify-end">
							<button type="button" onclick={() => onEditRule(rule)} class="text-accent hover:underline">{t('securityGroupRules.edit')}</button>
							<button type="button" onclick={() => onDeleteRule(rule.id)} class="text-state-danger-text hover:underline">{t('securityGroupRules.remove')}</button>
						</div>
					</div>
				{/each}
				</div>
			</div>
		</div>
		{#if addRuleOpen}
			<AddRuleForm bind:ruleForm bind:targetType {groups} {originalRuleId} adding={addingRule} canAdd={canAddRule} error={addError} onAdd={onAddRule} onCancel={onCancelAdd} onRemoveOriginal={onRemoveOriginal} />
		{/if}
	</section>
</div>

<style>
	.security-group-rules { z-index: var(--z-modal); }
	@media (min-width: 768px) {
		.security-group-rules { z-index: auto; min-width: 0; }
	}
</style>
