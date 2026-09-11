<script lang="ts">
	import { onMount } from 'svelte';
	import { get } from 'svelte/store';
	import { api, ApiError } from '$lib/api/client';
	import { auth } from '$lib/stores/auth';
	import { wizard } from '$lib/stores/wizard';
	import { useVmCreate } from '$lib/stores/vmCreateStore.svelte';
	import { Alert, Button, Field, TextInput, ToggleGroup } from '$lib/components/ui';
	import {
		isValidGithubUsername,
		normalizeRequestedInstanceName,
	} from '$lib/utils/instanceCreate';

	const s = useVmCreate();
	const normalizedInstanceName = $derived(normalizeRequestedInstanceName($wizard.instanceName));
	const githubUsernameError = $derived(
		$wizard.sshAccessMode === 'github' && !isValidGithubUsername($wizard.githubUsername)
			? 'GitHub 사용자 ID는 1~39자의 영문자, 숫자, 하이픈만 사용할 수 있습니다.'
			: undefined,
	);

	type CloudInitSnippet = {
		id: number;
		kind: 'history' | 'preset';
		name: string | null;
		content: string;
		created_at: string | null;
	};

	let cloudInitHistory = $state<CloudInitSnippet[]>([]);
	let cloudInitPresets = $state<CloudInitSnippet[]>([]);
	let cloudInitPresetName = $state('');
	let cloudInitLibraryError = $state('');
	let cloudInitLibraryLoading = $state(false);
	let cloudInitPresetSaving = $state(false);

	async function loadCloudInitLibrary() {
		const { token, projectId } = get(auth);
		if (!token) return;
		cloudInitLibraryLoading = true;
		cloudInitLibraryError = '';
		try {
			const library = await api.get<{ history: CloudInitSnippet[]; presets: CloudInitSnippet[] }>(
				'/api/v1/instances/cloud-init/library',
				token,
				projectId ?? undefined,
			);
			cloudInitHistory = library.history;
			cloudInitPresets = library.presets;
		} catch (error) {
			cloudInitLibraryError = error instanceof ApiError ? error.message : 'cloud-init 저장소를 불러오지 못했습니다.';
		} finally {
			cloudInitLibraryLoading = false;
		}
	}

	async function saveCloudInitPreset() {
		if (!cloudInitPresetName.trim() || !$wizard.cloudInit.trim()) {
			cloudInitLibraryError = '저장 이름과 cloud-init 내용을 입력하세요.';
			return;
		}
		const { token, projectId } = get(auth);
		if (!token) return;
		cloudInitPresetSaving = true;
		cloudInitLibraryError = '';
		try {
			await api.post(
				'/api/v1/instances/cloud-init/presets',
				{ name: cloudInitPresetName, content: $wizard.cloudInit },
				token,
				projectId ?? undefined,
			);
			cloudInitPresetName = '';
			await loadCloudInitLibrary();
		} catch (error) {
			cloudInitLibraryError = error instanceof ApiError ? error.message : 'cloud-init 프리셋을 저장하지 못했습니다.';
		} finally {
			cloudInitPresetSaving = false;
		}
	}

	function applyCloudInitSnippet(event: Event) {
		const id = Number((event.target as HTMLSelectElement).value);
		const snippet = [...cloudInitPresets, ...cloudInitHistory].find(item => item.id === id);
		if (snippet) wizard.update(w => ({ ...w, cloudInit: snippet.content }));
		(event.target as HTMLSelectElement).value = '';
	}

	async function deleteCloudInitSnippet(snippetId: number) {
		const { token, projectId } = get(auth);
		if (!token) return;
		try {
			await api.delete(`/api/v1/instances/cloud-init/library/${snippetId}`, token, projectId ?? undefined);
			await loadCloudInitLibrary();
		} catch (error) {
			cloudInitLibraryError = error instanceof ApiError ? error.message : 'cloud-init 항목을 삭제하지 못했습니다.';
		}
	}

	onMount(loadCloudInitLibrary);
</script>

<h2 class="text-lg font-semibold text-ink-0 mb-5">인스턴스 설정</h2>

<!-- VM 이름 -->
<div class="mb-4">
	<label for="vm-name" class="block text-[11.5px] font-semibold text-ink-2 tracking-tight flex items-center gap-1.5 mb-1.5">
		VM 이름 <span class="text-[10px] text-ink-3 font-normal px-1.5 py-0.5 rounded-full bg-surface-sunken">선택</span>
	</label>
	{#if normalizedInstanceName}
		<p class="text-xs mb-1" aria-live="polite">
			실제 인스턴스 이름: <code class="font-mono">{normalizedInstanceName}</code>
		</p>
	{/if}
	<input
		id="vm-name"
		bind:value={$wizard.instanceName}
		type="text"
		placeholder="비워두면 자동 생성"
		class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2.5 text-ink-0 text-sm focus:outline-none focus:border-action-warm transition-colors"
	/>
	<p class="text-xs text-ink-3 mt-1">입력하지 않으면 같은 프로젝트 안에서 중복되지 않는 안전한 영문 이름이 자동 생성됩니다.</p>
</div>

<!-- 네트워크 + 보안 그룹 -->
<div class="grid grid-cols-1 @lg/panel:grid-cols-2 gap-3.5 mb-4">
	<div>
		<label for="create-network" class="block text-[11.5px] font-semibold text-ink-2 tracking-tight flex items-center gap-1.5 mb-1.5">
			네트워크 <span class="text-red-400">*</span>
		</label>
		<select
			id="create-network"
			value={$wizard.networkId ?? ''}
			onchange={e => s.selectNetwork((e.target as HTMLSelectElement).value || null)}
			class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2.5 text-ink-0 text-sm focus:outline-none focus:border-action-warm transition-colors"
		>
			<option value="">기본 네트워크</option>
			{#each s.networks as net}
				<option value={net.id}>
					{net.name}{net.id === s.defaultNetworkId ? ' (기본)' : ''}{net.is_external ? ' (외부)' : ''}{net.is_shared ? ' (공유)' : ''}
				</option>
			{/each}
		</select>
	</div>
	<div>
		<label for="create-sg" class="block text-[11.5px] font-semibold text-ink-2 tracking-tight flex items-center gap-1.5 mb-1.5">
			보안 그룹 <span class="text-[10px] text-ink-3 font-normal px-1.5 py-0.5 rounded-full bg-surface-sunken">선택</span>
		</label>
		<select
			id="create-sg"
			value={$wizard.securityGroups[0] ?? ''}
			onchange={e => {
				const v = (e.target as HTMLSelectElement).value;
				wizard.update(w => ({ ...w, securityGroups: v ? [v] : [] }));
			}}
			class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2.5 text-ink-0 text-sm focus:outline-none focus:border-action-warm transition-colors"
		>
			<option value="">기본</option>
			{#each s.securityGroups as sg}
				<option value={sg.name}>{sg.name}</option>
			{/each}
		</select>
	</div>
</div>

<!-- SSH 접근 -->
<div class="mb-4">
	{#if s.adminMode}
		<p class="block text-[11.5px] font-semibold text-ink-2 tracking-tight flex items-center gap-1.5 mb-1.5">
			키페어 <span class="text-[10px] text-ink-3 font-normal px-1.5 py-0.5 rounded-full bg-surface-sunken">선택</span>
		</p>
		<div class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2.5 text-ink-3 text-sm">
			없음 (관리자 생성 — 콘솔 비밀번호 사용)
		</div>
		<p class="text-xs text-action-warm/80 mt-1">admin 모드에서는 대상 프로젝트의 키페어에 접근할 수 없습니다.</p>
	{:else}
		{#if s.githubSshEligible}
			<div class="mb-2">
				<ToggleGroup
					value={$wizard.sshAccessMode}
					options={[
						{ value: 'keypair', label: '등록 키페어' },
						{ value: 'github', label: 'GitHub 사용자' },
					]}
					onchange={(value) => s.selectSshAccessMode(value as 'keypair' | 'github')}
					ariaLabel="SSH 접근 방식"
				/>
			</div>
		{/if}
		{#if $wizard.sshAccessMode === 'github' && s.githubSshEligible}
			<Field
				label="GitHub 사용자 ID"
				for="github-username"
				required
				error={githubUsernameError}
				help="Ubuntu가 첫 부팅 때 GitHub 공개키를 기본 사용자에 1회 가져옵니다. GitHub 연결과 공개키 등록이 필요합니다."
			>
				<TextInput id="github-username" bind:value={$wizard.githubUsername} placeholder="예: octocat" />
			</Field>
		{:else}
			<label for="create-keypair" class="block text-[11.5px] font-semibold text-ink-2 tracking-tight flex items-center gap-1.5 mb-1.5">
				키페어 <span class="text-red-400">*</span>
			</label>
			<select
				id="create-keypair"
				value={$wizard.keyName ?? ''}
				onchange={e => wizard.update(w => ({ ...w, keyName: (e.target as HTMLSelectElement).value || null }))}
				class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2.5 text-ink-0 text-sm focus:outline-none focus:border-action-warm transition-colors"
			>
				<option value="">키페어 선택</option>
				{#each s.keypairs as kp}
					<option value={kp.name}>{kp.name}</option>
				{/each}
			</select>
			{#if s.keypairs.length === 0}
				<p class="text-xs text-action-warm mt-1">등록된 키페어가 없습니다.</p>
			{/if}
		{/if}
	{/if}
</div>

<!-- 루트 디스크 -->
{#if $wizard.squashfsMode}
<div class="mb-4 p-3 rounded-lg bg-surface-selected/20 border border-action-warm/40 text-action-warm text-xs">
	squashfs 라이브러리 소비 VM은 선택한 레이어의 Glance base image에서 직접 부팅합니다. 루트 디스크 크기와 삭제 옵션은 이 베타 경로에서 적용되지 않습니다.
</div>
{:else if $wizard.bootSource === 'image'}
<div class="grid grid-cols-1 @lg/panel:grid-cols-2 gap-3.5 mb-4">
	<div>
		<label for="boot-volume-size" class="block text-[11.5px] font-semibold text-ink-2 tracking-tight flex items-center gap-1.5 mb-1.5">
			루트 디스크 <span class="text-red-400">*</span>
		</label>
		<div class="flex items-center gap-3">
			<input
				id="boot-volume-size"
				bind:value={$wizard.bootVolumeSizeGb}
				type="number"
				min="1"
				max="16384"
				class="w-24 bg-surface-sunken border border-line-2 rounded-lg px-3 py-2.5 text-ink-0 text-sm focus:outline-none focus:border-action-warm transition-colors"
			/>
			<span class="text-[11px] text-ink-3">1 – 16,384 GB</span>
		</div>
	</div>
	<div class="flex items-end pb-1">
		<label class="flex items-center gap-2 px-3 py-2 rounded-lg bg-surface-sunken/60 border border-line-2 cursor-pointer w-full">
			<input
				type="checkbox"
				bind:checked={$wizard.deleteBootVolumeOnTermination}
				class="w-4 h-4 rounded border-line-2 bg-surface-sunken text-action-warm focus:ring-line-2 flex-shrink-0"
			/>
			<span class="text-sm text-ink-2">VM 삭제 시 루트 디스크 함께 삭제</span>
		</label>
	</div>
</div>
{:else}
<div class="mb-4 p-3 rounded-lg bg-surface-selected/20 border border-action-warm/40 text-action-warm text-xs">
	기존 부팅 볼륨 사용 시 루트 디스크 크기 설정이 적용되지 않습니다. 볼륨: <span class="font-medium">{$wizard.bootVolumeName ?? $wizard.bootVolumeId}</span>
</div>
{/if}

<!-- 파일 스토리지 마운트 -->
{#if s.fileStorages.length > 0}
<div class="mb-4">
	<div class="flex items-center justify-between mb-1.5">
		<p class="block text-[11.5px] font-semibold text-ink-2 tracking-tight">
			파일 스토리지 마운트 <span class="text-[10px] text-ink-3 font-normal px-1.5 py-0.5 rounded-full bg-surface-sunken">선택</span>
		</p>
		<button
			type="button"
			onclick={() => wizard.update(w => ({ ...w, dataMounts: [...w.dataMounts, { fileStorageId: '', mountPoint: '', readOnly: false }] }))}
			class="text-xs text-action-warm hover:text-action-warm-hover transition-colors"
		>+ 추가</button>
	</div>
	{#if $wizard.dataMounts.length === 0}
		<p class="text-[11px] text-ink-3">마운트할 파일 스토리지가 없습니다. "+ 추가"를 눌러 추가하세요.</p>
	{:else}
		<div class="space-y-2">
			{#each $wizard.dataMounts as mount, i}
				<div class="flex gap-2 items-start bg-surface-sunken/60 rounded-lg p-2.5">
					<div class="flex-1 grid grid-cols-1 @lg/panel:grid-cols-2 gap-2">
						<select
							value={mount.fileStorageId}
							onchange={e => wizard.update(w => {
								const m = [...w.dataMounts];
								m[i] = { ...m[i], fileStorageId: (e.target as HTMLSelectElement).value };
								return { ...w, dataMounts: m };
							})}
							class="bg-surface-selected border border-line-2 text-ink-1 text-xs rounded px-2 py-1.5 focus:outline-none focus:border-action-warm"
						>
							<option value="">스토리지 선택...</option>
							{#each s.fileStorages.filter(fs => fs.status === 'available') as fs}
								<option value={fs.id}>{fs.name || fs.id.slice(0, 12)} ({fs.share_proto})</option>
							{/each}
						</select>
						<input
							type="text"
							value={mount.mountPoint}
							oninput={e => wizard.update(w => {
								const m = [...w.dataMounts];
								m[i] = { ...m[i], mountPoint: (e.target as HTMLInputElement).value };
								return { ...w, dataMounts: m };
							})}
							placeholder="/mnt/mydata"
							class="bg-surface-selected border border-line-2 text-ink-1 text-xs rounded px-2 py-1.5 focus:outline-none focus:border-action-warm"
						/>
					</div>
					<label class="flex items-center gap-1.5 text-xs text-ink-2 shrink-0 mt-1.5">
						<input
							type="checkbox"
							checked={mount.readOnly}
							onchange={e => wizard.update(w => {
								const m = [...w.dataMounts];
								m[i] = { ...m[i], readOnly: (e.target as HTMLInputElement).checked };
								return { ...w, dataMounts: m };
							})}
							class="w-3.5 h-3.5 rounded border-line-2 bg-surface-sunken text-action-warm"
						/>읽기 전용
					</label>
					<button
						type="button"
						onclick={() => wizard.update(w => ({ ...w, dataMounts: w.dataMounts.filter((_, j) => j !== i) }))}
						class="text-ink-3 hover:text-red-400 transition-colors mt-0.5 shrink-0"
						aria-label="삭제"
					>
						<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
						</svg>
					</button>
				</div>
			{/each}
		</div>
		<p class="text-[10.5px] text-ink-3 mt-1">/mnt, /data, /srv, /home 하위 경로만 허용됩니다.</p>
	{/if}
</div>
{/if}

<!-- cloud-init 다크 에디터 -->
<div class="mb-4">
	<label for="cloud-init" class="block text-[11.5px] font-semibold text-ink-2 tracking-tight flex items-center gap-1.5 mb-1.5">
		CLOUD-INIT <span class="text-[10px] text-ink-3 font-normal px-1.5 py-0.5 rounded-full bg-surface-sunken">선택</span>
	</label>
	<div class="relative">
		<div class="absolute top-2 right-2 flex gap-1 z-[2] bg-surface-base border border-line-2 rounded-md p-0.5">
			<button type="button" disabled class="px-2 py-1 text-[10.5px] font-mono text-ink-3 rounded opacity-50 cursor-not-allowed">예제 ▾</button>
			<button type="button" disabled class="px-2 py-1 text-[10.5px] font-mono text-ink-3 rounded opacity-50 cursor-not-allowed">YAML ✓</button>
		</div>
		<textarea
			id="cloud-init"
			bind:value={$wizard.cloudInit}
			rows="8"
			placeholder="#cloud-config&#10;package_update: true&#10;packages:&#10;  - htop"
			class="w-full p-3.5 font-mono text-xs bg-[#0f172a] text-ink-1 rounded-lg border border-line-2 outline-none min-h-[140px] resize-y leading-relaxed focus:border-action-warm"
		></textarea>
	</div>
	<div class="mt-3 border border-line-2 rounded-lg p-3 space-y-3">
		<div class="grid grid-cols-1 @lg/panel:grid-cols-[1fr_auto] gap-2 items-end">
			<Field label="저장 이름" for="cloud-init-preset-name" help="프리셋은 계정에 암호화되어 저장됩니다.">
				<TextInput id="cloud-init-preset-name" bind:value={cloudInitPresetName} placeholder="예: 초기 패키지 설치" />
			</Field>
			<Button type="button" variant="secondary" size="sm" onclick={saveCloudInitPreset} disabled={cloudInitPresetSaving}>
				{cloudInitPresetSaving ? '저장 중...' : '현재 내용 저장'}
			</Button>
		</div>

		<div class="grid grid-cols-1 @lg/panel:grid-cols-2 gap-2">
			<div>
				<label for="cloud-init-load" class="block text-[11.5px] font-semibold text-ink-2 mb-1">저장된 항목 불러오기</label>
				<select
					id="cloud-init-load"
					onchange={applyCloudInitSnippet}
					disabled={cloudInitLibraryLoading || (cloudInitPresets.length === 0 && cloudInitHistory.length === 0)}
					class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm disabled:opacity-50"
				>
					<option value="">프리셋 또는 최근 실행 선택</option>
					{#if cloudInitPresets.length > 0}
						<optgroup label="저장한 프리셋">
							{#each cloudInitPresets as snippet}
								<option value={snippet.id}>{snippet.name}</option>
							{/each}
						</optgroup>
					{/if}
					{#if cloudInitHistory.length > 0}
						<optgroup label="최근 실행 (최대 20개)">
							{#each cloudInitHistory as snippet}
								<option value={snippet.id}>{snippet.created_at ? new Date(snippet.created_at).toLocaleString() : `실행 #${snippet.id}`}</option>
							{/each}
						</optgroup>
					{/if}
				</select>
			</div>
			{#if cloudInitPresets.length > 0}
				<div>
					<p class="block text-[11.5px] font-semibold text-ink-2 mb-1">저장한 프리셋 관리</p>
					<div class="flex flex-wrap gap-1.5">
						{#each cloudInitPresets as snippet}
							<Button type="button" variant="subtle" size="sm" onclick={() => deleteCloudInitSnippet(snippet.id)}>
								{snippet.name} 삭제
							</Button>
						{/each}
					</div>
				</div>
			{/if}
		</div>
		{#if cloudInitLibraryError}
			<Alert tone="danger">{cloudInitLibraryError}</Alert>
		{/if}
		<p class="text-[11px] text-ink-3">실행에 성공한 비어 있지 않은 cloud-init은 최근 실행 이력에 자동 저장됩니다.</p>
	</div>
</div>
