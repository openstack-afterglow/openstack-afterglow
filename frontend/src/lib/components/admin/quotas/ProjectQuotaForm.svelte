<script lang="ts">
	import { tick, untrack } from 'svelte';
	import { formatRam } from '$lib/utils/quotaFormat';
	import type { Quotas } from '$lib/types/quotas';
	import Alert from '$lib/components/ui/Alert.svelte';

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
			label: 'Compute 쿼터',
			description: '가상 머신 인스턴스, vCPU, 메모리 및 관련 리소스 한도',
			fields: [
				{ key: 'instances', label: '인스턴스', help: '최대 가상 머신 인스턴스 수' },
				{ key: 'cores', label: 'CPU 코어', help: '최대 vCPU 개수' },
				{ key: 'ram', label: 'RAM (MB)', help: '최대 메모리 용량 (MB)', formatUsage: formatRam },
				{ key: 'metadata_items', label: '메타데이터 항목', help: '인스턴스당 메타데이터 항목 최대 개수' },
				{ key: 'key_pairs', label: '키 페어', help: '사용자당 SSH 키 페어 최대 개수' },
				{ key: 'server_groups', label: '서버 그룹', help: '생성 가능한 서버 그룹 최대 개수' },
				{ key: 'server_group_members', label: '서버 그룹 멤버', help: '서버 그룹당 최대 인스턴스 수' },
				{ key: 'injected_files', label: '주입 파일', help: '주입 가능한 파일 최대 개수' },
				{ key: 'injected_file_content_bytes', label: '주입 파일 내용 (바이트)', help: '주입 파일당 최대 내용 크기' },
				{ key: 'injected_file_path_bytes', label: '주입 파일 경로 (바이트)', help: '주입 파일 경로의 최대 바이트 길이' },
			],
		},
		{
			id: 'volume',
			label: 'Volume 쿼터',
			description: '블록 스토리지 볼륨, 스냅샷 및 총 용량 한도',
			fields: [
				{ key: 'volumes', label: '볼륨', help: '생성 가능한 볼륨 수' },
				{ key: 'snapshots', label: '스냅샷', help: '생성 가능한 볼륨 스냅샷 수' },
				{ key: 'gigabytes', label: '총 용량 (GB)', help: '할당 가능한 볼륨 총 용량 (GB)', unit: 'GB' },
				{ key: 'backups', label: '백업', help: '생성 가능한 볼륨 백업 수' },
				{ key: 'backup_gigabytes', label: '백업 용량 (GB)', help: '볼륨 백업의 총 용량 (GB)', unit: 'GB' },
			],
		},
		{
			id: 'network',
			label: 'Network 쿼터',
			description: '가상 네트워크, 서브넷, 포트, 라우터, 플로팅 IP 및 보안 그룹 한도',
			fields: [
				{ key: 'network', label: '네트워크', help: '생성 가능한 가상 네트워크 수' },
				{ key: 'subnet', label: '서브넷', help: '생성 가능한 서브넷 수' },
				{ key: 'port', label: '포트', help: '생성 가능한 가상 네트워크 포트 수' },
				{ key: 'router', label: '라우터', help: '생성 가능한 가상 라우터 수' },
				{ key: 'floatingip', label: '플로팅 IP', help: '할당 가능한 공인 IP(플로팅 IP) 수' },
				{ key: 'security_group', label: '보안 그룹', help: '생성 가능한 보안 그룹 수' },
				{ key: 'security_group_rule', label: '보안 그룹 규칙', help: '보안 그룹당 생성 가능한 규칙 수' },
			],
		},
		{
			id: 'file_storage',
			label: 'File Storage (Manila) 쿼터',
			description: '공유 파일시스템, 스토리지 용량, 스냅샷 및 공유 네트워크 한도',
			fields: [
				{ key: 'shares', label: '공유 (Shares)', help: '생성 가능한 공유 파일시스템 수', putKey: 'shares' },
				{ key: 'gigabytes', label: '공유 총 용량 (GB)', help: '할당 가능한 공유 총 용량 (GB)', unit: 'GB', putKey: 'share_gigabytes' },
				{ key: 'snapshots', label: '공유 스냅샷', help: '생성 가능한 공유 스냅샷 수', putKey: 'share_snapshots' },
				{ key: 'snapshot_gigabytes', label: '스냅샷 총 용량 (GB)', help: '할당 가능한 스냅샷 총 용량 (GB)', unit: 'GB', putKey: 'share_snapshot_gigabytes' },
				{ key: 'share_networks', label: '공유 네트워크', help: '생성 가능한 공유 네트워크 수', putKey: 'share_networks' },
				{ key: 'share_groups', label: '공유 그룹', help: '생성 가능한 공유 그룹 수', putKey: 'share_groups' },
				{ key: 'share_group_snapshots', label: '공유 그룹 스냅샷', help: '생성 가능한 공유 그룹 스냅샷 수', putKey: 'share_group_snapshots' },
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
		onSaveSection?: (section: SectionId, changes: Record<string, number>) => Promise<{ success: boolean; status?: string; updated?: string[]; errors?: Record<string, string>; refreshed?: boolean; refreshError?: string }>;
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
					throw new Error(`${field.label}: -1(무제한) 또는 0 이상의 정수를 입력해주세요.`);
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
			localErrors[secId] = err instanceof Error ? err.message : '입력값이 올바르지 않습니다.';
			return;
		}

		if (Object.keys(payload).length === 0) {
			return;
		}
		if (!onSaveSection) return;

		const targetProjectId = projectId;
		localSavingSection = secId;
		try {
			const res = await onSaveSection(secId, payload);
			if (projectId !== targetProjectId) return;
			if (res.success && res.refreshed === false) {
				localErrors[secId] = res.refreshError || '쿼터를 다시 불러올 수 없습니다. 다시 시도해주세요.';
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
				localSuccesses[secId] = '저장되었습니다.';
				localErrors[secId] = '';
			} else {
				localErrors[secId] = res.errors?.[secId] || Object.values(res.errors ?? {}).join(', ') || '저장에 실패했습니다.';
			}
		} catch (err: unknown) {
			if (projectId === targetProjectId) localErrors[secId] = err instanceof Error ? err.message : '저장 중 오류가 발생했습니다.';
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
				<span class="text-xs bg-action-warm/15 text-action-warm px-2 py-0.5 rounded-full font-medium">수정됨</span>
			{/if}
		</div>

		{#if !isAvailable}
			{#if sec.id === 'file_storage' && (!secError || secError === 'service_disabled')}
				<div class="bg-surface-sunken/60 border border-line-2 rounded-lg p-4 text-sm text-ink-2">
					파일 스토리지(Manila) 서비스가 활성화되어 있지 않습니다.
				</div>
			{:else if secError}
				<Alert tone="danger" title={`${sec.label} 서비스를 사용할 수 없습니다:`} class="text-sm">
					{secError}
				</Alert>
			{:else}
				<div class="bg-surface-sunken/60 border border-line-2 rounded-lg p-4 text-sm text-ink-2">
					{sec.label} 서비스를 사용할 수 없거나 정보를 불러올 수 없습니다.
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
								<span class="text-[10px] text-ink-3 bg-surface-sunken px-1.5 py-0.5 rounded border border-line/40">미지원</span>
							{:else if drafts[sec.id]?.[field.key] === -1}
								<span class="text-[10px] text-accent font-medium bg-accent/10 px-1.5 py-0.5 rounded">무제한</span>
							{/if}
						</div>

						{#if isSupported}
							{@const inUse = quotaItem.in_use}
							<div class="text-sm text-ink-2 mb-1 flex items-center justify-between">
								<span>
									사용: {inUse === undefined || inUse === null ? '-' : (field.formatUsage ? field.formatUsage(inUse) : (field.unit ? `${inUse} ${field.unit}` : inUse))}
								</span>
								{#if drafts[sec.id]?.[field.key] !== baselines[sec.id]?.[field.key]}
									<span class="text-xs text-action-warm">수정 중</span>
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
							<div class="text-sm text-ink-3 mb-1">사용: -</div>
							<input
								id={`field-${sec.id}-${field.key}`}
								data-testid={`quota-${sec.id}-${field.key}-disabled`}
								disabled
								value=""
								placeholder="지원되지 않음"
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
						취소
					</button>
				{/if}
				<button
					type="button"
					data-testid={`save-${sec.id}-btn`}
					onclick={() => handleSaveSection(sec.id)}
					disabled={!onSaveSection || !hasChanges(sec.id) || saving || isSaving}
					class="px-4 py-1.5 bg-action-warm hover:bg-action-warm-hover text-ink-0 text-sm font-medium rounded-lg disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
				>
					{isSaving ? '저장 중...' : `${sec.label} 저장`}
				</button>
			</div>
		{/if}
	</div>
{/each}
