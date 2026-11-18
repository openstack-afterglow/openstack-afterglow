<script lang="ts">
	import { onDestroy } from 'svelte';
	import { isAppendOnly, isVaultError, isVaultSlot, vaultApi, vaultContentLimit, vaultKinds, vaultRoles, type VaultKind, type VaultNote, type VaultRole, type VaultScope } from '$lib/api/chatVault';
	import type { Workspace } from '$lib/api/chatWorkspaces';
	import { t } from '$lib/i18n/ns/chat-settings';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import Modal from '$lib/components/ui/Modal.svelte';
	import SelectInput from '$lib/components/ui/SelectInput.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import TextareaInput from '$lib/components/ui/TextareaInput.svelte';

	interface Props {
		token: string;
		projectId: string;
		initialKind: VaultKind;
		workspace?: Workspace;
		canWrite: boolean;
		isCurrent: () => boolean;
		onClose: () => void;
		onCreated: (note: VaultNote) => void;
	}
	let { token, projectId, workspace, canWrite, isCurrent, initialKind, onClose, onCreated }: Props = $props();
	const uid = $props.id();
	const kinds = vaultKinds.filter((kind) => !isVaultSlot(kind));
	let kind = $state<VaultKind>('user_note');
	$effect.pre(() => { kind = initialKind; });
	let scope = $state<VaultScope>('domain');
	let title = $state('');
	let content = $state('');
	let projectKey = $state('');
	let role = $state<VaultRole | ''>('');
	const scopedProject = $derived(scope === 'domain' && kind !== 'user_note' ? projectKey.trim() : '');
	const invalidProject = $derived(!!scopedProject && !/^[a-z0-9][a-z0-9-]{0,79}$/.test(scopedProject));
	let projectField = $state<HTMLInputElement | null>(null);
	let projectTouched = $state(false);
	let saving = $state(false);
	let error = $state<'secretRefused' | 'saveFailed' | 'noteExists' | null>(null);
	let slug: string | undefined;
	const lifetime = new AbortController();
	onDestroy(() => lifetime.abort());

	const current = () => !lifetime.signal.aborted && isCurrent();
	async function submit(event: SubmitEvent) {
		event.preventDefault();
		if (!canWrite || !current() || saving || !content.trim()) return;
		if (invalidProject) {
			projectTouched = true;
			projectField?.focus();
			return;
		}
		saving = true;
		error = null;
		try {
			const note = await vaultApi(token, projectId, lifetime.signal).create({
				kind: workspace ? 'user_note' : kind,
				slug: slug ??= crypto.randomUUID(),
				title: title.trim() || content.trim().split('\n', 1)[0].slice(0, 120),
				content,
				mode: !workspace && isAppendOnly(kind) ? 'append' : 'create',
				scope: workspace ? 'domain' : scope,
				...(workspace ? { workspace_id: workspace.id } : {
					...(scopedProject ? { project_key: scopedProject } : {}),
					...(kind === 'role_memory' && role ? { role } : {})
				})
			});
			if (current()) onCreated(note);
		} catch (e) {
			if (current()) {
				error = isVaultError(e, 'secret_detected') ? 'secretRefused'
					: isVaultError(e, 'note_exists') || isVaultError(e, 'append_only') ? 'noteExists' : 'saveFailed';
			}
		} finally {
			if (current()) saving = false;
		}
	}
</script>

<Modal open={canWrite} {onClose} dismissible={!saving} labelledBy={`${uid}-title`}>
	<div class="w-[min(calc(100vw-2rem),28rem)] max-w-full">
		<Card surface="modal" padding="lg">
			<h2 id={`${uid}-title`} class="mb-4 text-lg font-semibold">{t('settings.vault.create')}</h2>
			<form class="space-y-3" method="post" aria-labelledby={`${uid}-title`} onsubmit={submit}>
				{#if workspace}
					<p class="text-sm [overflow-wrap:anywhere] text-[var(--color-ink-2)]">{t('settings.vault.workspaceTarget', { name: workspace.name })}</p>
				{:else}
					<Field for={`${uid}-kind`} label={t('settings.vault.kind')}>
						<SelectInput id={`${uid}-kind`} bind:value={kind} disabled={saving}>
							{#each kinds as option (option)}
								<option value={option}>{t(`settings.vault.kinds.${option}`)}</option>
							{/each}
						</SelectInput>
					</Field>
					<Field for={`${uid}-scope`} label={t('settings.vault.scope')}>
						<SelectInput id={`${uid}-scope`} bind:value={scope} disabled={saving}>
							<option value="domain">{t('settings.vault.scopes.domain')}</option>
							<option value="global">{t('settings.vault.scopes.global')}</option>
						</SelectInput>
					</Field>
					{#if scope === 'domain' && kind !== 'user_note'}
						<Field for={`${uid}-project`} label={t('settings.vault.projectKey')} help={t('settings.vault.projectKeyHelp')} error={projectTouched && invalidProject ? t('settings.vault.invalidProjectKey') : undefined}>
							<TextInput id={`${uid}-project`} bind:value={projectKey} bind:element={projectField} disabled={saving} maxlength={80} ariaInvalid={projectTouched && invalidProject} />
						</Field>
					{/if}
					{#if kind === 'role_memory'}
						<Field for={`${uid}-role`} label={t('settings.vault.role')}>
							<SelectInput id={`${uid}-role`} bind:value={role} disabled={saving}>
								<option value="">{t('settings.vault.noRole')}</option>
								{#each vaultRoles as option (option)}
									<option value={option}>{t(`settings.vault.roles.${option}`)}</option>
								{/each}
							</SelectInput>
						</Field>
					{/if}
				{/if}
				<Field for={`${uid}-name`} label={t('settings.vault.noteTitle')}>
					<TextInput id={`${uid}-name`} bind:value={title} disabled={saving} maxlength={200} />
				</Field>
				<Field for={`${uid}-content`} label={t('settings.vault.content')}>
					<TextareaInput id={`${uid}-content`} bind:value={content} rows={5} maxlength={vaultContentLimit} required disabled={saving} />
				</Field>
				{#if error}<Alert flat>{t(`settings.vault.${error}`)}</Alert>{/if}
				<div class="flex flex-wrap justify-end gap-2">
					<Button variant="secondary" onclick={onClose} disabled={saving}>{t('settings.memory.cancel')}</Button>
					<Button type="submit" disabled={saving || !content.trim()} ariaBusy={saving}>
						{saving ? t('settings.memory.saving') : isAppendOnly(kind) ? t('settings.vault.append') : t('settings.vault.create')}
					</Button>
				</div>
			</form>
		</Card>
	</div>
</Modal>
