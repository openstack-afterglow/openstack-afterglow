<script lang="ts">
	import { onMount } from 'svelte';
	import { api, ApiError } from '$lib/api/client';
	import { MOTION_DURATION_MS } from '$lib/design/tokens';
	import { motionDuration } from '$lib/utils/motion';
	import { t } from '$lib/i18n/ns/shared';
	import { t as tc } from '$lib/i18n/ns/common';
	import { ActivityIndicator } from '$lib/components/ui';

	interface QuotaItem {
		limit: number;
		in_use: number;
	}

	interface ProjectQuota {
		compute: {
			instances?: QuotaItem;
			cores?: QuotaItem;
			ram?: QuotaItem;
		};
		volume: {
			volumes?: QuotaItem;
			gigabytes?: QuotaItem;
		};
	}

	interface Props {
		projectId: string;
		projectName: string;
		token?: string;
		authProjectId?: string;
		onClose?: () => void;
		onUpdated?: () => void;
	}

	let { projectId, projectName, token, authProjectId, onClose, onUpdated }: Props = $props();

	let quota = $state<ProjectQuota | null>(null);
	let loading = $state(true);
	let saving = $state(false);
	let error = $state('');
	let successMsg = $state('');

	// 편집 폼 상태 (-1 = 무제한)
	let formInstances = $state<number>(0);
	let formCores = $state<number>(0);
	let formRam = $state<number>(0);
	let formVolumes = $state<number>(0);
	let formGigabytes = $state<number>(0);

	onMount(() => {
		loadQuota();
	});

	async function loadQuota() {
		loading = true;
		error = '';
		try {
			quota = await api.get<ProjectQuota>(`/api/v1/admin/quotas/${projectId}`, token, authProjectId);
			formInstances = quota.compute.instances?.limit ?? -1;
			formCores = quota.compute.cores?.limit ?? -1;
			formRam = quota.compute.ram?.limit ?? -1;
			formVolumes = quota.volume.volumes?.limit ?? -1;
			formGigabytes = quota.volume.gigabytes?.limit ?? -1;
		} catch (e) {
			error = e instanceof ApiError ? e.message : t('quotaPanel.loadFailed');
		} finally {
			loading = false;
		}
	}

	async function saveQuota() {
		saving = true;
		error = '';
		successMsg = '';
		try {
			await api.put(
				`/api/v1/admin/quotas/${projectId}`,
				{
					instances: formInstances,
					cores: formCores,
					ram: formRam,
					volumes: formVolumes,
					gigabytes: formGigabytes
				},
				token,
				authProjectId
			);
			successMsg = t('quotaPanel.updated');
			onUpdated?.();
			await loadQuota();
		} catch (e) {
			error = e instanceof ApiError ? e.message : t('quotaPanel.updateFailed');
		} finally {
			saving = false;
		}
	}

	function usageBar(inUse: number, limit: number): number {
		if (limit <= 0) return 0;
		return Math.min(100, Math.round((inUse / limit) * 100));
	}

	function usageGrad(inUse: number, limit: number): string {
		if (limit <= 0) return 'var(--color-surface-sunken)';
		const pct = (inUse / limit) * 100;
		if (pct >= 95) return 'var(--gradient-usage-danger)';
		if (pct >= 80) return 'var(--gradient-usage-warning)';
		return 'var(--gradient-usage)';
	}

	function limitLabel(limit: number): string {
		return limit === -1 ? '∞' : String(limit);
	}
</script>

<!-- 오버레이 -->
<div
	class="motion-fade fixed inset-0 bg-surface-scrim-soft z-[var(--z-panel)]"
	role="button"
	tabindex="0"
	aria-label={t('quotaPanel.closeOverlay')}
	onclick={onClose}
	onkeydown={(e) => e.key === 'Escape' && onClose?.()}
></div>

<!-- 슬라이드 패널 -->
<div class="motion-enter fixed right-0 top-0 h-full w-[440px] bg-surface-canvas border-l border-line z-[var(--z-modal)] flex flex-col shadow-[var(--shadow-restraint)]">
	<!-- 헤더 -->
	<div class="flex items-center justify-between px-5 py-4 border-b border-line flex-shrink-0">
		<div>
			<h2 class="text-sm font-semibold text-ink-0">{projectName}</h2>
			<p class="text-xs text-ink-2 mt-0.5">{projectId}</p>
		</div>
		<button
			onclick={onClose}
			class="text-ink-2 hover:text-ink-0 text-xl leading-none ml-3 flex-shrink-0"
			aria-label={tc('actions.close')}
		>×</button>
	</div>

	<div class="flex-1 overflow-y-auto p-5 space-y-5">
		{#if loading}
			<ActivityIndicator variant="spinner" size="sm" label={t('quotaPanel.loading')} />
		{:else if error && !quota}
			<div class="text-red-400 text-sm">{error}</div>
		{:else if quota}
			<!-- 컴퓨트 쿼터 -->
			<div>
				<h3 class="text-xs font-semibold text-ink-2 uppercase tracking-wide mb-3">{t('quotaPanel.compute')}</h3>
				<div class="space-y-4">
					<!-- 인스턴스 -->
					<div>
						<div class="flex items-center justify-between mb-1">
							<label class="text-sm text-ink-2" for="q-instances">{t('quotaPanel.instances')}</label>
							<span class="text-xs text-ink-2">{t('quotaPanel.usage', { used: quota.compute.instances?.in_use ?? 0, limit: limitLabel(quota.compute.instances?.limit ?? -1) })}</span>
						</div>
						{#if (quota.compute.instances?.limit ?? -1) > 0}
							<div class="w-full h-1 bg-surface-sunken rounded-full overflow-hidden mb-2">
								<div
									class="quota-fill w-full h-full rounded-full"
									style="transform: scaleX({usageBar(quota.compute.instances?.in_use ?? 0, quota.compute.instances?.limit ?? 0) / 100}); background: {usageGrad(quota.compute.instances?.in_use ?? 0, quota.compute.instances?.limit ?? 0)}"
								></div>
							</div>
						{/if}
						<input
							id="q-instances"
							type="number"
							bind:value={formInstances}
							min="-1"
							class="w-full bg-surface-sunken border border-line-2 rounded px-3 py-1.5 text-sm text-ink-0 focus:outline-none focus:border-action-warm"
						/>
						<p class="text-xs text-ink-2 mt-1">{t('quotaPanel.unlimitedHint')}</p>
					</div>

					<!-- CPU -->
					<div>
						<div class="flex items-center justify-between mb-1">
							<label class="text-sm text-ink-2" for="q-cores">{t('quotaPanel.cores')}</label>
							<span class="text-xs text-ink-2">{t('quotaPanel.usage', { used: quota.compute.cores?.in_use ?? 0, limit: limitLabel(quota.compute.cores?.limit ?? -1) })}</span>
						</div>
						{#if (quota.compute.cores?.limit ?? -1) > 0}
							<div class="w-full h-1 bg-surface-sunken rounded-full overflow-hidden mb-2">
								<div
									class="quota-fill w-full h-full rounded-full"
									style="transform: scaleX({usageBar(quota.compute.cores?.in_use ?? 0, quota.compute.cores?.limit ?? 0) / 100}); background: {usageGrad(quota.compute.cores?.in_use ?? 0, quota.compute.cores?.limit ?? 0)}"
								></div>
							</div>
						{/if}
						<input
							id="q-cores"
							type="number"
							bind:value={formCores}
							min="-1"
							class="w-full bg-surface-sunken border border-line-2 rounded px-3 py-1.5 text-sm text-ink-0 focus:outline-none focus:border-action-warm"
						/>
					</div>

					<!-- RAM -->
					<div>
						<div class="flex items-center justify-between mb-1">
							<label class="text-sm text-ink-2" for="q-ram">RAM (MB)</label>
							<span class="text-xs text-ink-2">{t('quotaPanel.usageMb', { used: quota.compute.ram?.in_use ?? 0, limit: limitLabel(quota.compute.ram?.limit ?? -1) })}</span>
						</div>
						{#if (quota.compute.ram?.limit ?? -1) > 0}
							<div class="w-full h-1 bg-surface-sunken rounded-full overflow-hidden mb-2">
								<div
									class="quota-fill w-full h-full rounded-full"
									style="transform: scaleX({usageBar(quota.compute.ram?.in_use ?? 0, quota.compute.ram?.limit ?? 0) / 100}); background: {usageGrad(quota.compute.ram?.in_use ?? 0, quota.compute.ram?.limit ?? 0)}"
								></div>
							</div>
						{/if}
						<input
							id="q-ram"
							type="number"
							bind:value={formRam}
							min="-1"
							class="w-full bg-surface-sunken border border-line-2 rounded px-3 py-1.5 text-sm text-ink-0 focus:outline-none focus:border-action-warm"
						/>
					</div>
				</div>
			</div>

			<!-- 볼륨 쿼터 -->
			<div>
				<h3 class="text-xs font-semibold text-ink-2 uppercase tracking-wide mb-3">{t('quotaPanel.volume')}</h3>
				<div class="space-y-4">
					<!-- 볼륨 수 -->
					<div>
						<div class="flex items-center justify-between mb-1">
							<label class="text-sm text-ink-2" for="q-volumes">{t('quotaPanel.volumeCount')}</label>
							<span class="text-xs text-ink-2">{t('quotaPanel.usage', { used: quota.volume.volumes?.in_use ?? 0, limit: limitLabel(quota.volume.volumes?.limit ?? -1) })}</span>
						</div>
						{#if (quota.volume.volumes?.limit ?? -1) > 0}
							<div class="w-full h-1 bg-surface-sunken rounded-full overflow-hidden mb-2">
								<div
									class="quota-fill w-full h-full rounded-full"
									style="transform: scaleX({usageBar(quota.volume.volumes?.in_use ?? 0, quota.volume.volumes?.limit ?? 0) / 100}); background: {usageGrad(quota.volume.volumes?.in_use ?? 0, quota.volume.volumes?.limit ?? 0)}"
								></div>
							</div>
						{/if}
						<input
							id="q-volumes"
							type="number"
							bind:value={formVolumes}
							min="-1"
							class="w-full bg-surface-sunken border border-line-2 rounded px-3 py-1.5 text-sm text-ink-0 focus:outline-none focus:border-action-warm"
						/>
					</div>

					<!-- 용량 -->
					<div>
						<div class="flex items-center justify-between mb-1">
							<label class="text-sm text-ink-2" for="q-gigabytes">{t('quotaPanel.gigabytes')}</label>
							<span class="text-xs text-ink-2">{t('quotaPanel.usageGb', { used: quota.volume.gigabytes?.in_use ?? 0, limit: limitLabel(quota.volume.gigabytes?.limit ?? -1) })}</span>
						</div>
						{#if (quota.volume.gigabytes?.limit ?? -1) > 0}
							<div class="w-full h-1 bg-surface-sunken rounded-full overflow-hidden mb-2">
								<div
									class="quota-fill w-full h-full rounded-full"
									style="transform: scaleX({usageBar(quota.volume.gigabytes?.in_use ?? 0, quota.volume.gigabytes?.limit ?? 0) / 100}); background: {usageGrad(quota.volume.gigabytes?.in_use ?? 0, quota.volume.gigabytes?.limit ?? 0)}"
								></div>
							</div>
						{/if}
						<input
							id="q-gigabytes"
							type="number"
							bind:value={formGigabytes}
							min="-1"
							class="w-full bg-surface-sunken border border-line-2 rounded px-3 py-1.5 text-sm text-ink-0 focus:outline-none focus:border-action-warm"
						/>
					</div>
				</div>
			</div>

			{#if error}
				<div class="text-red-400 text-sm">{error}</div>
			{/if}
			{#if successMsg}
				<div class="text-green-400 text-sm">{successMsg}</div>
			{/if}
		{/if}
	</div>

	<!-- 저장 버튼 -->
	{#if quota && !loading}
		<div class="px-5 py-4 border-t border-line flex-shrink-0">
			<button
				onclick={saveQuota}
				disabled={saving}
				class="w-full bg-action-warm hover:bg-action-warm-hover disabled:bg-surface-selected disabled:cursor-not-allowed text-action-on-warm text-sm font-medium py-2 rounded-lg transition-colors"
			>
				{#if saving}
					<ActivityIndicator variant="spinner" tone="ink" size="sm" label={t('quotaPanel.saving')} />
				{:else}
					{t('quotaPanel.save')}
				{/if}
			</button>
		</div>
	{/if}
</div>

<style>
	.quota-fill {
		transform-origin: left;
		transition: transform var(--motion-duration-base) var(--motion-ease-standard);
	}
</style>
