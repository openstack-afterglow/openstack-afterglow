<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { get } from 'svelte/store';
	import { api, ApiError } from '$lib/api/client';
	import { auth } from '$lib/stores/auth';
	import { wizard } from '$lib/stores/wizard';
	import { useVmCreate } from '$lib/stores/vmCreateStore.svelte';
	import { Alert, Button, Field, TextInput, ToggleGroup } from '$lib/components/ui';
	import { CLOUD_INIT_PRESETS } from '$lib/config/cloudInitPresets';
	import { t } from '$lib/i18n/ns/vm-wizard';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import RichText from '$lib/i18n/RichText.svelte';

	import {
		isValidGithubUsername,
		normalizeRequestedInstanceName,
	} from '$lib/utils/instanceCreate';
	import type { GithubSshHistoryEntry, GithubSshProfile } from '$lib/types/compute';

	const s = useVmCreate();
	const normalizedInstanceName = $derived(normalizeRequestedInstanceName($wizard.instanceName));
	const githubUsernameError = $derived(
		$wizard.sshAccessMode === 'github' && !isValidGithubUsername($wizard.githubUsername)
			? t('config.github.usernameInvalid')
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
	let cloudInitFileInput: HTMLInputElement;
	let cloudInitSelection = $state<
		| { kind: 'preset'; preset: (typeof CLOUD_INIT_PRESETS)[number] }
		| { kind: 'file'; name: string }
		| null
	>(null);
	let githubLookupStatus = $state<'idle' | 'loading' | 'valid' | 'error'>('idle');
	let githubLookupError = $state('');
	let githubHistory = $state<GithubSshHistoryEntry[]>([]);
	let githubLookupTimer: ReturnType<typeof setTimeout> | undefined;
	let githubLookupFor = '';
	let githubLookupGeneration = 0;
	let githubHistoryRequested = false;
	let githubPendingFor = '';

	function githubKey(value: string): string {
		return value.trim().toLowerCase();
	}

	async function loadGithubHistory() {
		const { token, projectId } = get(auth);
		if (!token) return;
		githubHistoryRequested = true;
		try {
			githubHistory = await api.get<GithubSshHistoryEntry[]>(
				'/api/v1/instances/github-users/history',
				token,
				projectId ?? undefined,
			);
		} catch {
			githubHistory = [];
		}
	}

	function isCurrentGithubLookup(username: string, generation: number): boolean {
		const current = get(wizard);
		return generation === githubLookupGeneration
			&& current.sshAccessMode === 'github'
			&& s.githubSshEligible
			&& githubKey(current.githubUsername) === githubKey(username);
	}

	async function verifyGithubUsername(username: string, generation: number) {
		const { token, projectId } = get(auth);
		if (!token || !isCurrentGithubLookup(username, generation)) return;
		githubPendingFor = githubKey(username);
		githubLookupStatus = 'loading';
		githubLookupError = '';
		try {
			const profile = await api.post<GithubSshProfile>(
				'/api/v1/instances/github-users/lookup',
				{ username },
				token,
				projectId ?? undefined,
			);
			if (!isCurrentGithubLookup(username, generation)) return;
			if (githubKey(profile.login) !== githubKey(username) || !profile.has_public_keys) {
				githubLookupStatus = 'error';
				githubLookupError = t('config.github.lookupFailed');
				return;
			}
			githubLookupStatus = 'valid';
			wizard.update(w => ({ ...w, githubUsername: profile.login, githubProfile: profile }));
			await loadGithubHistory();
		} catch (error) {
			if (!isCurrentGithubLookup(username, generation)) return;
			githubLookupStatus = 'error';
			githubLookupError = error instanceof ApiError ? error.message : t('config.github.lookupFailed');
		} finally {
			if (generation === githubLookupGeneration) githubPendingFor = '';
		}
	}

	function selectGithubHistoryEntry(login: string) {
		wizard.update(w => ({
			...w,
			githubUsername: login,
			githubProfile: githubKey(w.githubUsername) === githubKey(login)
				&& githubKey(w.githubProfile?.login ?? '') === githubKey(login)
				&& w.githubProfile?.has_public_keys
				? w.githubProfile : null,
		}));
	}

	$effect(() => {
		const username = $wizard.githubUsername.trim();
		const enabled = $wizard.sshAccessMode === 'github' && s.githubSshEligible;
		const key = enabled && isValidGithubUsername(username) ? githubKey(username) : '';
		clearTimeout(githubLookupTimer);
		if (key !== githubLookupFor) {
			githubLookupFor = key;
			githubLookupGeneration += 1;
			githubPendingFor = '';
			githubLookupStatus = 'idle';
			githubLookupError = '';
		}
		if (!key) {
			if ($wizard.githubProfile) wizard.update(w => ({ ...w, githubProfile: null }));
			return;
		}
		const profile = $wizard.githubProfile;
		if (profile?.has_public_keys && githubKey(profile.login) === key) {
			githubLookupStatus = 'valid';
			githubLookupError = '';
			return;
		}
		if (profile) wizard.update(w => ({ ...w, githubProfile: null }));
		if (githubPendingFor === key) return;
		const generation = githubLookupGeneration;
		githubLookupTimer = setTimeout(() => void verifyGithubUsername(username, generation), 400);
		return () => clearTimeout(githubLookupTimer);
	});

	$effect(() => {
		if ($wizard.sshAccessMode === 'github' && s.githubSshEligible && !githubHistoryRequested) {
			void loadGithubHistory();
		}
	});

	onDestroy(() => {
		clearTimeout(githubLookupTimer);
		githubLookupGeneration += 1;
	});


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
			cloudInitLibraryError = error instanceof ApiError ? error.message : t('config.cloudInit.loadFailed');
		} finally {
			cloudInitLibraryLoading = false;
		}
	}

	async function saveCloudInitPreset() {
		if (!cloudInitPresetName.trim() || !$wizard.cloudInit.trim()) {
			cloudInitLibraryError = t('config.cloudInit.nameAndContentRequired');
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
			cloudInitLibraryError = error instanceof ApiError ? error.message : t('config.cloudInit.saveFailed');
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
			cloudInitLibraryError = error instanceof ApiError ? error.message : t('config.cloudInit.deleteFailed');
		}
	}

function applyCloudInitPreset(event: Event) {
	const preset = CLOUD_INIT_PRESETS.find(item => item.id === (event.target as HTMLSelectElement).value);
	if (preset) {
		wizard.update(w => ({ ...w, cloudInit: preset.content }));
		cloudInitSelection = { kind: 'preset', preset };
	}
}

	async function loadCloudInitFile(event: Event) {
		const file = (event.target as HTMLInputElement).files?.[0];
		(event.target as HTMLInputElement).value = '';
		if (!file) return;
		if (file.size > 65_536) {
			cloudInitLibraryError = t('config.cloudInit.fileTooLarge');
			return;
		}
		try {
			const content = await file.text();
			if (!content || content.length > 65_536 || content.includes('\u0000')) throw new Error();
			wizard.update(w => ({ ...w, cloudInit: content }));
			cloudInitSelection = { kind: 'file', name: file.name };
			cloudInitLibraryError = '';
		} catch {
			cloudInitLibraryError = t('config.cloudInit.invalidFile');
		}
	}

	onMount(loadCloudInitLibrary);
</script>

<h2 class="text-lg font-semibold text-ink-0 mb-5">{t('config.title')}</h2>

<!-- VM 이름 -->
<div class="mb-4">
	<label for="vm-name" class="block text-[11.5px] font-semibold text-ink-2 tracking-tight flex items-center gap-1.5 mb-1.5">
		{t('config.name.label')} <span class="text-xs text-ink-2 font-normal px-1.5 py-0.5 rounded-full bg-surface-sunken">{t('config.optional')}</span>
	</label>
	{#if normalizedInstanceName}
		<p class="text-xs mb-1" aria-live="polite">
			<RichText segments={t.rich('config.name.actual', { name: normalizedInstanceName })} classes={{ code: 'font-mono' }} />
		</p>
	{/if}
	<input
		id="vm-name"
		bind:value={$wizard.instanceName}
		type="text"
		placeholder={t('config.name.placeholder')}
		class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2.5 text-ink-0 text-sm focus:outline-none focus:border-action-warm transition-colors"
	/>
	<p class="text-xs text-ink-2 mt-1">{t('config.name.help')}</p>
</div>

<!-- 네트워크 + 보안 그룹 -->
<div class="grid grid-cols-1 @lg/panel:grid-cols-2 gap-3.5 mb-4">
	<div>
		<label for="create-network" class="block text-[11.5px] font-semibold text-ink-2 tracking-tight flex items-center gap-1.5 mb-1.5">
			{t('config.network.label')} <span class="text-red-400">*</span>
		</label>
		<select
			id="create-network"
			value={$wizard.networkId ?? ''}
			onchange={e => s.selectNetwork((e.target as HTMLSelectElement).value || null)}
			class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2.5 text-ink-0 text-sm focus:outline-none focus:border-action-warm transition-colors"
		>
			<option value="">{t('config.network.default')}</option>
			{#each s.networks as net}
				<option value={net.id}>
					{t('config.network.option', { name: net.name, isDefault: net.id === s.defaultNetworkId, isExternal: !!net.is_external, isShared: !!net.is_shared })}
				</option>
			{/each}
		</select>
	</div>
	<div>
		<label for="create-sg" class="block text-[11.5px] font-semibold text-ink-2 tracking-tight flex items-center gap-1.5 mb-1.5">
			{t('config.securityGroup.label')} <span class="text-xs text-ink-2 font-normal px-1.5 py-0.5 rounded-full bg-surface-sunken">{t('config.optional')}</span>
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
			<option value="">{t('config.securityGroup.default')}</option>
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
			{t('config.keypair.label')} <span class="text-xs text-ink-2 font-normal px-1.5 py-0.5 rounded-full bg-surface-sunken">{t('config.optional')}</span>
		</p>
		<div class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2.5 text-ink-2 text-sm">
			{t('config.keypair.adminNone')}
		</div>
		<p class="text-xs text-warm-text/80 mt-1">{t('config.keypair.adminHelp')}</p>
	{:else}
		{#if s.githubSshEligible}
			<div class="mb-2">
				<ToggleGroup
					value={$wizard.sshAccessMode}
					options={[
						{ value: 'keypair', label: t('config.ssh.registeredKeypair') },
						{ value: 'github', label: t('config.ssh.githubUser') },
					]}
					onchange={(value) => s.selectSshAccessMode(value as 'keypair' | 'github')}
					ariaLabel={t('config.ssh.modeLabel')}
				/>
			</div>
		{/if}
		{#if $wizard.sshAccessMode === 'github' && s.githubSshEligible}
			<Field
				label={t('config.github.usernameLabel')}
				for="github-username"
				required
				error={githubUsernameError}
				help={t('config.github.help')}
			>
				<TextInput id="github-username" bind:value={$wizard.githubUsername} placeholder={t('config.github.placeholder')} />
			</Field>
			{#if githubHistory.length > 0}
				<div class="mt-2 flex flex-wrap items-center gap-1.5">
					<span class="text-xs text-ink-2">{t('config.github.recent')}</span>
					{#each githubHistory as entry (entry.id)}
						<Button
							variant={githubKey($wizard.githubUsername) === githubKey(entry.login) ? 'secondary' : 'subtle'}
							size="xs"
							onclick={() => selectGithubHistoryEntry(entry.login)}
						>
							@{entry.login}
						</Button>
					{/each}
				</div>
			{/if}
			<div class="mt-2 text-xs" aria-live="polite">
				{#if githubLookupStatus === 'loading'}<span class="text-ink-2">{t('config.github.loading')}</span>
				{:else if githubLookupStatus === 'valid' && $wizard.githubProfile}
					<span class="text-positive">
						{$wizard.githubProfile.name
							? t('config.github.verifiedWithName', { login: $wizard.githubProfile.login, name: $wizard.githubProfile.name })
							: t('config.github.verified', { login: $wizard.githubProfile.login })}
					</span>
					<a
						class="ml-1.5 text-accent underline underline-offset-2"
						href={$wizard.githubProfile.html_url}
						target="_blank"
						rel="noopener noreferrer"
					>{t('config.github.profile')}</a>
				{:else if githubLookupStatus === 'error'}<span class="text-danger">{githubLookupError}</span>{/if}
			</div>
		{:else}
			<label for="create-keypair" class="block text-[11.5px] font-semibold text-ink-2 tracking-tight flex items-center gap-1.5 mb-1.5">
				{t('config.keypair.label')} <span class="text-red-400">*</span>
			</label>
			<select
				id="create-keypair"
				value={$wizard.keyName ?? ''}
				onchange={e => wizard.update(w => ({ ...w, keyName: (e.target as HTMLSelectElement).value || null }))}
				class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2.5 text-ink-0 text-sm focus:outline-none focus:border-action-warm transition-colors"
			>
				<option value="">{t('config.keypair.select')}</option>
				{#each s.keypairs as kp}
					<option value={kp.name}>{kp.name}</option>
				{/each}
			</select>
			{#if s.keypairs.length === 0}
				<p class="text-xs text-warm-text mt-1">{t('config.keypair.empty')}</p>
			{/if}
		{/if}
	{/if}
</div>

<!-- 루트 디스크 -->
{#if $wizard.squashfsMode}
<div class="mb-4 p-3 rounded-lg bg-surface-selected/20 border border-action-warm/40 text-warm-text text-xs">
	{t('config.rootDisk.squashfsHelp')}
</div>
{:else if $wizard.bootSource === 'image'}
<div class="grid grid-cols-1 @lg/panel:grid-cols-2 gap-3.5 mb-4">
	<div>
		<label for="boot-volume-size" class="block text-[11.5px] font-semibold text-ink-2 tracking-tight flex items-center gap-1.5 mb-1.5">
			{t('config.rootDisk.label')} <span class="text-red-400">*</span>
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
			<span class="text-xs text-ink-2">1 – 16,384 GB</span>
		</div>
	</div>
	<div class="flex items-end pb-1">
		<label class="flex items-center gap-2 px-3 py-2 rounded-lg bg-surface-sunken/60 border border-line-2 cursor-pointer w-full">
			<input
				type="checkbox"
				bind:checked={$wizard.deleteBootVolumeOnTermination}
				class="w-4 h-4 rounded border-line-2 bg-surface-sunken text-warm-text focus:ring-line-2 flex-shrink-0"
			/>
			<span class="text-sm text-ink-2">{t('config.rootDisk.deleteWithVm')}</span>
		</label>
	</div>
</div>
{:else}
<div class="mb-4 p-3 rounded-lg bg-surface-selected/20 border border-action-warm/40 text-warm-text text-xs">
	<RichText segments={t.rich('config.rootDisk.existingVolumeHelp', { volume: $wizard.bootVolumeName ?? $wizard.bootVolumeId })} classes={{ strong: 'font-medium' }} />
</div>
{/if}

<!-- 파일 스토리지 마운트 -->
{#if s.fileStorages.length > 0}
<div class="mb-4">
	<div class="flex items-center justify-between mb-1.5">
		<p class="block text-[11.5px] font-semibold text-ink-2 tracking-tight">
			{t('config.mounts.label')} <span class="text-xs text-ink-2 font-normal px-1.5 py-0.5 rounded-full bg-surface-sunken">{t('config.optional')}</span>
		</p>
		<button
			type="button"
			onclick={() => wizard.update(w => ({ ...w, dataMounts: [...w.dataMounts, { fileStorageId: '', mountPoint: '', readOnly: false }] }))}
			class="text-xs text-warm-text hover:text-warm-text-hover transition-colors"
		>{t('config.mounts.add')}</button>
	</div>
	{#if $wizard.dataMounts.length === 0}
		<p class="text-xs text-ink-2">{t('config.mounts.empty')}</p>
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
							<option value="">{t('config.mounts.selectStorage')}</option>
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
							class="w-3.5 h-3.5 rounded border-line-2 bg-surface-sunken text-warm-text"
						/>{t('config.mounts.readOnly')}
					</label>
					<button
						type="button"
						onclick={() => wizard.update(w => ({ ...w, dataMounts: w.dataMounts.filter((_, j) => j !== i) }))}
						class="text-ink-2 hover:text-red-400 transition-colors mt-0.5 shrink-0"
						aria-label={t('config.mounts.delete')}
					>
						<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
						</svg>
					</button>
				</div>
			{/each}
		</div>
		<p class="text-[10.5px] text-ink-2 mt-1">{t('config.mounts.pathsHelp')}</p>
	{/if}
</div>
{/if}

<!-- cloud-init 다크 에디터 -->
<div class="mb-4">
	<label for="cloud-init" class="block text-[11.5px] font-semibold text-ink-2 tracking-tight flex items-center gap-1.5 mb-1.5">
		CLOUD-INIT <span class="text-xs text-ink-2 font-normal px-1.5 py-0.5 rounded-full bg-surface-sunken">{t('config.optional')}</span>
	</label>
	<div class="relative">
		<div class="absolute top-2 right-2 flex gap-1 z-[2] bg-surface-base border border-line-2 rounded-md p-0.5">
			<select aria-label={t('config.cloudInit.defaultPresets')} onchange={applyCloudInitPreset} class="px-2 py-1 text-[10.5px] font-mono bg-surface-base text-ink-1 rounded">
				<option value="">{t('config.cloudInit.examples')}</option>
				{#each CLOUD_INIT_PRESETS as preset}<option value={preset.id}>{preset.label}</option>{/each}
			</select>
			<Button type="button" variant="subtle" size="sm" onclick={() => cloudInitFileInput.click()}>{t('config.cloudInit.openFile')}</Button>
			<input bind:this={cloudInitFileInput} type="file" accept=".yaml,.yml,.txt,text/plain" class="sr-only" onchange={loadCloudInitFile} />
		</div>
		<textarea
			id="cloud-init"
			bind:value={$wizard.cloudInit}
			rows="8"
			placeholder="#cloud-config&#10;package_update: true&#10;packages:&#10;  - htop"
			class="w-full p-3.5 font-mono text-xs bg-surface-sunken text-ink-1 rounded-lg border border-line-2 outline-none min-h-[140px] resize-y leading-relaxed focus:border-action-warm"
		></textarea>
	</div>
	{#if cloudInitSelection}
		<p class="mt-2 text-xs text-positive" aria-live="polite">
			{cloudInitSelection.kind === 'file'
				? t('config.cloudInit.appliedFile', { name: cloudInitSelection.name })
				: t('config.cloudInit.appliedPreset', { name: cloudInitSelection.preset.label })}
		</p>
	{/if}
	{#if $wizard.cloudInit.trim()}
		<div class="mt-3 border border-line-2 rounded-lg p-3 space-y-3">
			<div class="grid grid-cols-1 @lg/panel:grid-cols-[1fr_auto] gap-2 items-end">
				<Field label={t('config.cloudInit.nameLabel')} for="cloud-init-preset-name" help={t('config.cloudInit.nameHelp')}>
					<TextInput id="cloud-init-preset-name" bind:value={cloudInitPresetName} placeholder={t('config.cloudInit.namePlaceholder')} />
				</Field>
				<Button type="button" variant="secondary" size="sm" onclick={saveCloudInitPreset} disabled={cloudInitPresetSaving}>
					{cloudInitPresetSaving ? t('config.cloudInit.saving') : t('config.cloudInit.saveCurrent')}
				</Button>
			</div>
		</div>
	{/if}

	<div class="mt-3 border border-line-2 rounded-lg p-3 space-y-3">
		<div class="grid grid-cols-1 @lg/panel:grid-cols-2 gap-2">
			<div>
				<label for="cloud-init-load" class="block text-[11.5px] font-semibold text-ink-2 mb-1">{t('config.cloudInit.loadSaved')}</label>
				<select
					id="cloud-init-load"
					onchange={applyCloudInitSnippet}
					disabled={cloudInitLibraryLoading || (cloudInitPresets.length === 0 && cloudInitHistory.length === 0)}
					class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm disabled:opacity-50"
				>
					<option value="">{t('config.cloudInit.selectSaved')}</option>
					{#if cloudInitPresets.length > 0}
						<optgroup label={t('config.cloudInit.savedPresets')}>
							{#each cloudInitPresets as snippet}
								<option value={snippet.id}>{snippet.name}</option>
							{/each}
						</optgroup>
					{/if}
					{#if cloudInitHistory.length > 0}
						<optgroup label={t('config.cloudInit.recentRuns')}>
							{#each cloudInitHistory as snippet}
								<option value={snippet.id}>{snippet.created_at ? new Date(snippet.created_at).toLocaleString(intlLocale()) : t('config.cloudInit.runNumber', { id: snippet.id })}</option>
							{/each}
						</optgroup>
					{/if}
				</select>
			</div>
			{#if cloudInitPresets.length > 0}
				<div>
					<p class="block text-[11.5px] font-semibold text-ink-2 mb-1">{t('config.cloudInit.managePresets')}</p>
					<div class="flex flex-wrap gap-1.5">
						{#each cloudInitPresets as snippet}
							<Button type="button" variant="subtle" size="sm" onclick={() => deleteCloudInitSnippet(snippet.id)}>
								{t('config.cloudInit.deletePreset', { name: snippet.name })}
							</Button>
						{/each}
					</div>
				</div>
			{/if}
		</div>
		{#if cloudInitLibraryError}
			<Alert tone="danger">{cloudInitLibraryError}</Alert>
		{/if}
		<p class="text-xs text-ink-2">{t('config.cloudInit.historyHelp')}</p>
	</div>
</div>
