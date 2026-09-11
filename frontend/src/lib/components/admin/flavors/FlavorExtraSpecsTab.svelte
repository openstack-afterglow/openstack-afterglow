<script lang="ts">
	import { onMount, untrack } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import {
		FLAVOR_SPEC_TEMPLATES,
		FLAVOR_SPEC_CATEGORIES,
		type FlavorSpecTemplate,
	} from '$lib/constants/flavorSpecTemplates';
	import type { GpuCatalogDevice } from '$lib/types/gpu';

	interface Flavor {
		id: string;
		name: string;
		vcpus: number;
		ram: number;
		disk: number;
		is_public: boolean;
		description: string | null;
		extra_specs: Record<string, string>;
		is_gpu: boolean;
		gpu_count: number;
	}

	let {
		flavor: flavorIn,
		onChanged,
	}: {
		flavor: Flavor;
		onChanged: () => void;
	} = $props();

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	let flavor = $state(untrack(() => flavorIn));
	$effect(() => {
		flavor = flavorIn;
	});

	let newSpecKey = $state('');
	let newSpecValue = $state('');
	let specSaving = $state(false);
	let specError = $state('');
	let editingSpecKey = $state<string | null>(null);
	let editingSpecValue = $state('');

	// 템플릿 선택 ('' = 직접 입력)
	let selectedTemplateKey = $state('');
	let gpuAlias = $state('');
	let gpuCount = $state(1);

	const currentTemplate = $derived<FlavorSpecTemplate | null>(
		FLAVOR_SPEC_TEMPLATES.find((t) => t.key === selectedTemplateKey) ?? null
	);

	// GPU alias 후보 (카탈로그의 비-audio 장치 대표 alias)
	let gpuAliasOptions = $state<{ alias: string; name: string }[]>([]);

	async function loadGpuAliases() {
		try {
			const res = await api.get<{ devices: GpuCatalogDevice[] }>('/api/v1/admin/gpu-devices', token, projectId);
			const seen = new Set<string>();
			gpuAliasOptions = res.devices
				.filter((d) => !d.is_audio && d.aliases.length > 0)
				.map((d) => ({ alias: d.aliases[0], name: d.name }))
				.filter((o) => (seen.has(o.alias) ? false : (seen.add(o.alias), true)));
		} catch {
			gpuAliasOptions = [];
		}
	}

	function selectTemplate(key: string) {
		selectedTemplateKey = key;
		const t = FLAVOR_SPEC_TEMPLATES.find((tpl) => tpl.key === key);
		if (!t) {
			newSpecKey = '';
			newSpecValue = '';
			return;
		}
		newSpecKey = t.key;
		if (t.valueType === 'enum') {
			newSpecValue = t.defaultValue ?? t.options?.[0] ?? '';
		} else {
			newSpecValue = t.defaultValue ?? '';
		}
		if (t.valueType === 'gpu_alias') {
			gpuAlias = gpuAliasOptions[0]?.alias ?? '';
			gpuCount = 1;
		}
	}

	function effectiveValue(): string {
		// gpu_alias 템플릿: alias 드롭다운 + 개수로 값 생성 (카탈로그 로드 실패 시 직접 입력 폴백)
		if (currentTemplate?.valueType === 'gpu_alias' && gpuAliasOptions.length > 0) {
			return gpuAlias ? `${gpuAlias}:${gpuCount}` : '';
		}
		return newSpecValue.trim();
	}

	async function addExtraSpec() {
		const value = effectiveValue();
		if (!newSpecKey.trim()) return;
		specSaving = true;
		specError = '';
		try {
			await api.post(
				`/api/v1/admin/flavors/${flavor.id}/extra-specs`,
				{ key: newSpecKey.trim(), value },
				token,
				projectId,
			);
			flavor = {
				...flavor,
				extra_specs: { ...flavor.extra_specs, [newSpecKey.trim()]: value },
			};
			newSpecKey = '';
			newSpecValue = '';
			selectedTemplateKey = '';
			onChanged();
		} catch (e: unknown) {
			specError = e instanceof ApiError ? e.message : 'extra_spec 추가 실패';
		} finally {
			specSaving = false;
		}
	}

	onMount(loadGpuAliases);

	function startEditSpec(key: string, value: string) {
		editingSpecKey = key;
		editingSpecValue = value;
	}

	function cancelEditSpec() {
		editingSpecKey = null;
		editingSpecValue = '';
	}

	async function saveEditSpec() {
		if (!editingSpecKey) return;
		specSaving = true;
		specError = '';
		try {
			await api.post(
				`/api/v1/admin/flavors/${flavor.id}/extra-specs`,
				{ key: editingSpecKey, value: editingSpecValue.trim() },
				token,
				projectId,
			);
			flavor = {
				...flavor,
				extra_specs: { ...flavor.extra_specs, [editingSpecKey]: editingSpecValue.trim() },
			};
			editingSpecKey = null;
			editingSpecValue = '';
			onChanged();
		} catch (e) {
			specError = e instanceof ApiError ? e.message : 'extra_spec 수정 실패';
		} finally {
			specSaving = false;
		}
	}

	async function deleteExtraSpec(key: string) {
		specError = '';
		try {
			await api.delete(
				`/api/v1/admin/flavors/${flavor.id}/extra-specs/${encodeURIComponent(key)}`,
				token,
				projectId,
			);
			const specs = { ...flavor.extra_specs };
			delete specs[key];
			flavor = { ...flavor, extra_specs: specs };
			onChanged();
		} catch (e) {
			specError = e instanceof ApiError ? e.message : 'extra_spec 삭제 실패';
		}
	}
</script>

{#if specError}
	<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-3 py-2 text-xs mb-3">{specError}</div>
{/if}

{#if Object.keys(flavor.extra_specs).length === 0}
	<div class="text-ink-3 text-sm mb-4">등록된 속성이 없습니다</div>
{:else}
	<div class="space-y-1 mb-4">
		{#each Object.entries(flavor.extra_specs) as [k, v]}
			<div class="bg-surface-base border border-line rounded-lg px-3 py-2">
				{#if editingSpecKey === k}
					<div class="flex items-center gap-2">
						<span class="text-xs text-action-warm font-mono break-all shrink-0">{k}</span>
						<span class="text-ink-3">=</span>
						<input
							bind:value={editingSpecValue}
							type="text"
							class="flex-1 min-w-0 bg-surface-sunken border border-action-warm rounded px-2 py-1 text-xs text-ink-0 font-mono focus:outline-none"
							onkeydown={(e) => {
								if (e.key === 'Enter') saveEditSpec();
								if (e.key === 'Escape') cancelEditSpec();
							}}
						/>
						<button onclick={saveEditSpec} disabled={specSaving} class="text-green-400 hover:text-green-300 text-xs shrink-0">저장</button>
						<button onclick={cancelEditSpec} class="text-ink-2 hover:text-ink-2 text-xs shrink-0">취소</button>
					</div>
				{:else}
					<div class="flex items-center justify-between">
						<button
							class="flex-1 min-w-0 text-left cursor-pointer hover:bg-surface-sunken/50 rounded -mx-1 px-1 py-0.5 transition-colors"
							onclick={() => startEditSpec(k, v)}
						>
							<span class="text-xs text-action-warm font-mono break-all">{k}</span>
							<span class="text-ink-3 mx-2">=</span>
							<span class="text-xs text-ink-2 font-mono break-all">{v}</span>
						</button>
						<button onclick={() => deleteExtraSpec(k)} class="ml-2 text-red-400 hover:text-red-300 text-xs shrink-0">삭제</button>
					</div>
				{/if}
			</div>
		{/each}
	</div>
{/if}

<div class="text-sm text-ink-2 mb-2">속성 추가/수정</div>
<div class="space-y-2">
	<select
		value={selectedTemplateKey}
		onchange={(e) => selectTemplate(e.currentTarget.value)}
		class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-1.5 text-ink-0 text-sm focus:outline-none focus:border-action-warm"
	>
		<option value="">직접 입력</option>
		{#each FLAVOR_SPEC_CATEGORIES as category}
			<optgroup label={category}>
				{#each FLAVOR_SPEC_TEMPLATES.filter((t) => t.category === category) as t}
					<option value={t.key}>{t.label} ({t.key})</option>
				{/each}
			</optgroup>
		{/each}
	</select>

	{#if currentTemplate}
		<div class="text-xs text-ink-3">{currentTemplate.description}</div>
		{#if currentTemplate.valueType === 'gpu_alias'}
			{#if gpuAliasOptions.length === 0}
				<div class="text-xs text-yellow-400">GPU alias 카탈로그를 불러올 수 없습니다 — 값을 직접 입력하세요</div>
				<input
					bind:value={newSpecValue}
					type="text"
					placeholder="예: RTX3090:1"
					class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-1.5 text-ink-0 text-sm font-mono focus:outline-none focus:border-action-warm"
				/>
			{:else}
				<div class="flex gap-2">
					<select
						bind:value={gpuAlias}
						class="flex-1 min-w-0 bg-surface-sunken border border-line-2 rounded-lg px-3 py-1.5 text-ink-0 text-sm font-mono focus:outline-none focus:border-action-warm"
					>
						{#each gpuAliasOptions as o (o.alias)}
							<option value={o.alias}>{o.alias} — {o.name}</option>
						{/each}
					</select>
					<input
						bind:value={gpuCount}
						type="number"
						min="1"
						title="GPU 개수"
						class="w-20 bg-surface-sunken border border-line-2 rounded-lg px-3 py-1.5 text-ink-0 text-sm focus:outline-none focus:border-action-warm"
					/>
				</div>
				<div class="text-xs text-ink-3 font-mono">값: {gpuAlias ? `${gpuAlias}:${gpuCount}` : '-'}</div>
			{/if}
		{:else if currentTemplate.valueType === 'enum'}
			<select
				bind:value={newSpecValue}
				class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-1.5 text-ink-0 text-sm font-mono focus:outline-none focus:border-action-warm"
			>
				{#each currentTemplate.options ?? [] as opt}
					<option value={opt}>{opt}</option>
				{/each}
			</select>
		{:else}
			<input
				bind:value={newSpecValue}
				type={currentTemplate.valueType === 'number' ? 'number' : 'text'}
				placeholder={currentTemplate.placeholder ?? '값'}
				class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-1.5 text-ink-0 text-sm font-mono focus:outline-none focus:border-action-warm"
			/>
		{/if}
	{:else}
		<input
			bind:value={newSpecKey}
			type="text"
			placeholder="키 (예: hw:numa_nodes)"
			class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-1.5 text-ink-0 text-sm font-mono focus:outline-none focus:border-action-warm"
		/>
		<input
			bind:value={newSpecValue}
			type="text"
			placeholder="값"
			class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-1.5 text-ink-0 text-sm font-mono focus:outline-none focus:border-action-warm"
		/>
	{/if}
	<button
		onclick={addExtraSpec}
		disabled={specSaving || !newSpecKey.trim() || (currentTemplate?.valueType === 'gpu_alias' && gpuAliasOptions.length > 0 && !gpuAlias)}
		class="w-full px-3 py-1.5 bg-action-warm hover:bg-action-warm-hover text-action-on-warm text-sm rounded-lg disabled:opacity-30"
	>
		{specSaving ? '저장 중...' : '추가/수정'}
	</button>
</div>
