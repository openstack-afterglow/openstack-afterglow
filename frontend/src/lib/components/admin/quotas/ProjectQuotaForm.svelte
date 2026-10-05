<script lang="ts">
	import { tick, untrack } from 'svelte';
	import { t } from '$lib/i18n/ns/admin-identity';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import type { Quotas } from '$lib/types/quotas';
	import Alert from '$lib/components/ui/Alert.svelte';

	function formatRam(mb: number): string {
		if (mb >= 1024) {
			const digits = mb % 1024 === 0 ? 0 : 1;
			return `${(mb / 1024).toLocaleString(intlLocale(), { useGrouping: false, minimumFractionDigits: digits, maximumFractionDigits: digits })} GB`;
		}
		return `${mb.toLocaleString(intlLocale(), { useGrouping: false })} MB`;
	}

	type SectionId = 'compute' | 'volume' | 'network' | 'file_storage';

	interface FieldDef {
		key: string;
		label: string;
		help?: string;
		unit?: string;
		putKey?: string;
		formatUsage?: (val: number) => string;
	}

	interface SectionDef {
		id: SectionId;
		label: string;
		description: string;
		fields: FieldDef[];
	}

	const SECTIONS: SectionDef[] = [
		{
			id: 'compute',
			get label() { return t('quotaForm.compute.label'); },
			get description() { return t('quotaForm.compute.description'); },
			fields: [
				{ key: 'instances', get label() { return t('quotaForm.compute.instances.label'); }, get help() { return t('quotaForm.compute.instances.help'); } },
				{ key: 'cores', get label() { return t('quotaForm.compute.cores.label'); }, get help() { return t('quotaForm.compute.cores.help'); } },
				{ key: 'ram', get label() { return t('quotaForm.compute.ram.label'); }, get help() { return t('quotaForm.compute.ram.help'); }, formatUsage: formatRam },
				{ key: 'metadata_items', get label() { return t('quotaForm.compute.metadataItems.label'); }, get help() { return t('quotaForm.compute.metadataItems.help'); } },
				{ key: 'key_pairs', get label() { return t('quotaForm.compute.keyPairs.label'); }, get help() { return t('quotaForm.compute.keyPairs.help'); } },
				{ key: 'server_groups', get label() { return t('quotaForm.compute.serverGroups.label'); }, get help() { return t('quotaForm.compute.serverGroups.help'); } },
				{ key: 'server_group_members', get label() { return t('quotaForm.compute.serverGroupMembers.label'); }, get help() { return t('quotaForm.compute.serverGroupMembers.help'); } },
				{ key: 'injected_files', get label() { return t('quotaForm.compute.injectedFiles.label'); }, get help() { return t('quotaForm.compute.injectedFiles.help'); } },
				{ key: 'injected_file_content_bytes', get label() { return t('quotaForm.compute.injectedFileContentBytes.label'); }, get help() { return t('quotaForm.compute.injectedFileContentBytes.help'); } },
				{ key: 'injected_file_path_bytes', get label() { return t('quotaForm.compute.injectedFilePathBytes.label'); }, get help() { return t('quotaForm.compute.injectedFilePathBytes.help'); } },
			],
		},
		{
			id: 'volume',
			get label() { return t('quotaForm.volume.label'); },
			get description() { return t('quotaForm.volume.description'); },
			fields: [
				{ key: 'volumes', get label() { return t('quotaForm.volume.volumes.label'); }, get help() { return t('quotaForm.volume.volumes.help'); } },
				{ key: 'snapshots', get label() { return t('quotaForm.volume.snapshots.label'); }, get help() { return t('quotaForm.volume.snapshots.help'); } },
				{ key: 'gigabytes', get label() { return t('quotaForm.volume.gigabytes.label'); }, get help() { return t('quotaForm.volume.gigabytes.help'); }, unit: 'GB' },
			],
		},
		{
			id: 'network',
			get label() { return t('quotaForm.network.label'); },
			get description() { return t('quotaForm.network.description'); },
			fields: [
				{ key: 'network', get label() { return t('quotaForm.network.network.label'); }, get help() { return t('quotaForm.network.network.help'); } },
				{ key: 'subnet', get label() { return t('quotaForm.network.subnet.label'); }, get help() { return t('quotaForm.network.subnet.help'); } },
				{ key: 'port', get label() { return t('quotaForm.network.port.label'); }, get help() { return t('quotaForm.network.port.help'); } },
				{ key: 'router', get label() { return t('quotaForm.network.router.label'); }, get help() { return t('quotaForm.network.router.help'); } },
				{ key: 'floatingip', get label() { return t('quotaForm.network.floatingip.label'); }, get help() { return t('quotaForm.network.floatingip.help'); } },
				{ key: 'security_group', get label() { return t('quotaForm.network.securityGroup.label'); }, get help() { return t('quotaForm.network.securityGroup.help'); } },
				{ key: 'security_group_rule', get label() { return t('quotaForm.network.securityGroupRule.label'); }, get help() { return t('quotaForm.network.securityGroupRule.help'); } },
			],
		},
		{
			id: 'file_storage',
			get label() { return t('quotaForm.fileStorage.label'); },
			get description() { return t('quotaForm.fileStorage.description'); },
			fields: [
				{ key: 'shares', get label() { return t('quotaForm.fileStorage.shares.label'); }, get help() { return t('quotaForm.fileStorage.shares.help'); }, putKey: 'shares' },
				{ key: 'gigabytes', get label() { return t('quotaForm.fileStorage.gigabytes.label'); }, get help() { return t('quotaForm.fileStorage.gigabytes.help'); }, unit: 'GB', putKey: 'share_gigabytes' },
				{ key: 'snapshots', get label() { return t('quotaForm.fileStorage.snapshots.label'); }, get help() { return t('quotaForm.fileStorage.snapshots.help'); }, putKey: 'share_snapshots' },
				{ key: 'snapshot_gigabytes', get label() { return t('quotaForm.fileStorage.snapshotGigabytes.label'); }, get help() { return t('quotaForm.fileStorage.snapshotGigabytes.help'); }, unit: 'GB', putKey: 'share_snapshot_gigabytes' },
				{ key: 'share_networks', get label() { return t('quotaForm.fileStorage.shareNetworks.label'); }, get help() { return t('quotaForm.fileStorage.shareNetworks.help'); }, putKey: 'share_networks' },
				{ key: 'share_groups', get label() { return t('quotaForm.fileStorage.shareGroups.label'); }, get help() { return t('quotaForm.fileStorage.shareGroups.help'); }, putKey: 'share_groups' },
				{ key: 'share_group_snapshots', get label() { return t('quotaForm.fileStorage.shareGroupSnapshots.label'); }, get help() { return t('quotaForm.fileStorage.shareGroupSnapshots.help'); }, putKey: 'share_group_snapshots' },
			],
		},
	];

	let {
		quotas,
		projectId = '',
		saving = false,
		savingSection = null,
		sectionErrors = {},
		sectionSuccesses = {},
		onSaveSection,
	}: {
		quotas: Quotas;
		projectId?: string;
		saving?: boolean;
		savingSection?: string | null;
		sectionErrors?: Record<string, string>;
		sectionSuccesses?: Record<string, string>;
		onSaveSection: (section: SectionId, changes: Record<string, number>) => Promise<{ success: boolean; status?: string; updated?: string[]; errors?: Record<string, string>; refreshed?: boolean; refreshError?: string }>;
	} = $props();

	let drafts = $state<Record<SectionId, Record<string, number | null>>>({
		compute: {},
		volume: {},
		network: {},
		file_storage: {},
	});

	let baselines = $state<Record<SectionId, Record<string, number>>>({
		compute: {},
		volume: {},
		network: {},
		file_storage: {},
	});

	let localErrors = $state<Record<string, string>>({});
	let localSuccesses = $state<Record<string, string>>({});
	let localSavingSection = $state<string | null>(null);
	let lastProjectId: string | undefined;

	$effect(() => {
		const currentProjectId = projectId;
		const currentQuotas = quotas;
		untrack(() => {
			const isNewProject = lastProjectId !== currentProjectId;
			if (isNewProject) {
				lastProjectId = currentProjectId;
				localErrors = {};
				localSuccesses = {};
			}
			for (const sec of SECTIONS) {
				const nextBase: Record<string, number> = {};
				const nextDraft: Record<string, number | null> = {};
				const secQuotas = currentQuotas[sec.id];
				for (const field of sec.fields) {
					const q = secQuotas?.[field.key];
					if (!q || !Number.isInteger(q.limit)) continue;
					const previous = baselines[sec.id][field.key];
					const draft = drafts[sec.id][field.key];
					nextBase[field.key] = q.limit;
					nextDraft[field.key] = isNewProject || draft === undefined || draft === previous ? q.limit : draft;
				}
				baselines[sec.id] = nextBase;
				drafts[sec.id] = nextDraft;
			}
		});
	});

	function hasChanges(secId: SectionId): boolean {
		const sec = SECTIONS.find((s) => s.id === secId);
		if (!sec || !quotas?.[secId]) return false;
		for (const field of sec.fields) {
			if (quotas[secId]?.[field.key] === undefined) continue;
			const d = drafts[secId]?.[field.key];
			const b = baselines[secId]?.[field.key];
			if (d !== b) return true;
		}
		return false;
	}

	function getSectionPayload(secId: SectionId): Record<string, number> {
		const sec = SECTIONS.find((s) => s.id === secId);
		if (!sec || !quotas?.[secId]) return {};
		const payload: Record<string, number> = {};
		for (const field of sec.fields) {
			if (quotas[secId]?.[field.key] === undefined) continue;
			const d = drafts[secId]?.[field.key];
			const b = baselines[secId]?.[field.key];
			if (d !== b) {
				if (d === undefined || d === null || !Number.isInteger(d) || d < -1) {
					throw new Error(t('quotaForm.invalidLimit', { label: field.label }));
				}
				payload[field.putKey ?? field.key] = d;
			}
		}
		return payload;
	}

	async function handleSaveSection(secId: SectionId) {
		localErrors[secId] = '';
		localSuccesses[secId] = '';
		let payload: Record<string, number>;
		try {
			payload = getSectionPayload(secId);
		} catch (err: unknown) {
			localErrors[secId] = err instanceof Error ? err.message : t('quotaForm.invalidInput');
			return;
		}

		if (Object.keys(payload).length === 0) {
			return;
		}

		const targetProjectId = projectId;
		localSavingSection = secId;
		try {
			const res = await onSaveSection(secId, payload);
			if (projectId !== targetProjectId) return;
			if (res.success && res.refreshed === false) {
				localErrors[secId] = res.refreshError || t('quotaForm.refreshFailed');
			} else if (res.success) {
				await tick();
				if (projectId !== targetProjectId) return;
				for (const field of SECTIONS.find((s) => s.id === secId)?.fields ?? []) {
					const key = field.putKey ?? field.key;
					const refreshed = quotas[secId]?.[field.key];
					if (refreshed && drafts[secId][field.key] === payload[key]) {
						baselines[secId][field.key] = refreshed.limit;
						drafts[secId][field.key] = refreshed.limit;
					}
				}
				localSuccesses[secId] = t('quotaForm.saved');
				localErrors[secId] = '';
			} else {
				localErrors[secId] = res.errors?.[secId] || Object.values(res.errors ?? {}).join(', ') || t('quotaForm.saveFailed');
			}
		} catch (err: unknown) {
			if (projectId === targetProjectId) localErrors[secId] = err instanceof Error ? err.message : t('quotaForm.saveError');
		} finally {
			localSavingSection = null;
		}
	}

	function handleResetSection(secId: SectionId) {
		if (baselines[secId]) {
			drafts[secId] = { ...baselines[secId] };
		}
		localErrors[secId] = '';
		localSuccesses[secId] = '';
	}
</script>


{#each SECTIONS as sec}
	{@const secQuotas = quotas?.[sec.id]}
	{@const secError = quotas?.errors?.[sec.id]}
	{@const isAvailable = quotas?.availability?.[sec.id] !== false && secQuotas !== null && secQuotas !== undefined}
	{@const displayError = localErrors[sec.id] || sectionErrors[sec.id] || ''}
	{@const displaySuccess = localSuccesses[sec.id] || sectionSuccesses[sec.id] || ''}
	{@const isSaving = localSavingSection === sec.id || savingSection === sec.id}

	<div class="bg-surface-base border border-line rounded-xl p-6 mb-6" data-testid={`quota-section-${sec.id}`}>
		<div class="flex items-center justify-between mb-4">
			<div>
				<h2 class="text-sm font-semibold text-ink-0 uppercase tracking-wide">{sec.label}</h2>
				{#if sec.description}
					<p class="text-xs text-ink-2 mt-0.5">{sec.description}</p>
				{/if}
			</div>
			{#if isAvailable && hasChanges(sec.id)}
				<span class="text-xs bg-action-warm/15 text-action-warm px-2 py-0.5 rounded-full font-medium">{t('quotaForm.modified')}</span>
			{/if}
		</div>

		{#if !isAvailable}
			{#if sec.id === 'file_storage' && (!secError || secError === 'service_disabled')}
				<div class="bg-surface-sunken/60 border border-line-2 rounded-lg p-4 text-sm text-ink-2">
					{t('quotaForm.fileStorageDisabled')}
				</div>
			{:else if secError}
				<Alert tone="danger" title={t('quotaForm.serviceUnavailableTitle', { label: sec.label })} class="text-sm">
					{secError}
				</Alert>
			{:else}
				<div class="bg-surface-sunken/60 border border-line-2 rounded-lg p-4 text-sm text-ink-2">
					{t('quotaForm.serviceUnavailable', { label: sec.label })}
				</div>
			{/if}
		{:else}
			<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
				{#each sec.fields as field}
					{@const quotaItem = secQuotas[field.key]}
					{@const isSupported = quotaItem !== undefined && quotaItem !== null}
					<div>
						<div class="flex items-center justify-between mb-1.5">
							<label class="block text-xs text-ink-2" for={`field-${sec.id}-${field.key}`}>
								{field.label}
							</label>
							{#if !isSupported}
								<span class="text-[10px] text-ink-3 bg-surface-sunken px-1.5 py-0.5 rounded border border-line/40">{t('quotaForm.unsupported')}</span>
							{:else if drafts[sec.id]?.[field.key] === -1}
								<span class="text-[10px] text-accent font-medium bg-accent/10 px-1.5 py-0.5 rounded">{t('quotaForm.unlimited')}</span>
							{/if}
						</div>

						{#if isSupported}
							{@const inUse = quotaItem.in_use}
							<div class="text-sm text-ink-2 mb-1 flex items-center justify-between">
								<span>
									{t('quotaForm.usage', { usage: inUse === undefined || inUse === null ? '-' : (field.formatUsage ? field.formatUsage(inUse) : (field.unit ? `${inUse} ${field.unit}` : inUse)) })}
								</span>
								{#if drafts[sec.id]?.[field.key] !== baselines[sec.id]?.[field.key]}
									<span class="text-xs text-action-warm">{t('quotaForm.editing')}</span>
								{/if}
							</div>
							<input
								id={`field-${sec.id}-${field.key}`}
								data-testid={`quota-${sec.id}-${field.key}`}
								type="number"
								min="-1"
								bind:value={drafts[sec.id][field.key]}
								class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm"
							/>
						{:else}
							<div class="text-sm text-ink-3 mb-1">{t('quotaForm.usage', { usage: '-' })}</div>
							<input
								id={`field-${sec.id}-${field.key}`}
								data-testid={`quota-${sec.id}-${field.key}-disabled`}
								disabled
								value=""
								placeholder={t('quotaForm.unsupportedPlaceholder')}
								class="w-full bg-surface-sunken/40 border border-line/40 rounded-lg px-3 py-2 text-ink-3 text-sm cursor-not-allowed italic"
							/>
						{/if}
						{#if field.help}
							<p class="text-[11px] text-ink-3 mt-1">{field.help}</p>
						{/if}
					</div>
				{/each}
			</div>

			{#if displayError}
				<Alert tone="danger" class="mt-4">{displayError}</Alert>
			{/if}
			{#if displaySuccess}
				<div class="bg-state-success/12 border border-state-success/32 text-state-success-text rounded-lg px-4 py-2.5 text-sm mt-4">
					{displaySuccess}
				</div>
			{/if}

			<div class="flex items-center justify-end gap-3 mt-6 pt-4 border-t border-line/50">
				{#if hasChanges(sec.id)}
					<button
						type="button"
						onclick={() => handleResetSection(sec.id)}
						disabled={isSaving}
						class="px-3 py-1.5 bg-surface-sunken hover:bg-surface-selected text-ink-2 hover:text-ink-0 text-sm rounded-lg transition-colors disabled:opacity-40"
					>
						{t('quotaForm.cancel')}
					</button>
				{/if}
				<button
					type="button"
					data-testid={`save-${sec.id}-btn`}
					onclick={() => handleSaveSection(sec.id)}
					disabled={!onSaveSection || !hasChanges(sec.id) || saving || isSaving}
					class="px-4 py-1.5 bg-action-warm hover:bg-action-warm-hover text-ink-0 text-sm font-medium rounded-lg disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
				>
					{isSaving ? t('quotaForm.saving') : t('quotaForm.saveSection', { label: sec.label })}
				</button>
			</div>
		{/if}
	</div>
{/each}
