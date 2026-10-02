<script lang="ts">
	import { tick } from 'svelte';
	import Modal from '$lib/components/ui/Modal.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import { t } from '$lib/i18n/ns/chat-studio';

	interface Props {
		open: boolean;
		onClose: () => void;
		onCreate: (name: string) => Promise<boolean>;
	}

	let { open, onClose, onCreate }: Props = $props();
	let name = $state('');
	let saving = $state(false);
	let nameInput = $state<HTMLInputElement | null>(null);

	$effect(() => {
		if (!open) return;
		name = '';
		void tick().then(() => nameInput?.focus());
	});

	const canSubmit = $derived(name.trim().length > 0 && !saving);

	function close() {
		if (!saving) onClose();
	}

	async function submit() {
		if (!canSubmit) return;
		saving = true;
		try {
			if (await onCreate(name.trim())) onClose();
		} finally {
			saving = false;
		}
	}
</script>

<Modal {open} dismissible={!saving} onClose={close} labelledBy="create-project-dialog-title">
	<section class="create-dialog">
		<header class="create-dialog-head">
			<h2 id="create-project-dialog-title">{t('createProject.title')}</h2>
			<Button variant="ghost" size="icon" type="button" onclick={close} ariaLabel={t('createProject.close')}>
				<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.9" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" stroke-linecap="round" /></svg>
			</Button>
		</header>
		<form
			class="create-form"
			onsubmit={(event) => {
				event.preventDefault();
				void submit();
			}}
		>
			<Field label={t('createProject.nameLabel')} for="project-name" required>
				<TextInput id="project-name" bind:element={nameInput} bind:value={name} maxlength={100} placeholder={t('createProject.namePlaceholder')} required />
			</Field>
			<p class="create-note">
				{t('createProject.description')}
			</p>
			<div class="form-actions">
				<Button variant="ghost" type="button" onclick={close}>{t('createProject.cancel')}</Button>
				<Button variant="accent" type="submit" disabled={!canSubmit}>
					{saving ? t('createProject.creating') : t('createProject.title')}
				</Button>
			</div>
		</form>
	</section>
</Modal>

<style>
	.create-dialog {
		width: min(31rem, calc(100vw - 2rem));
		border: 1px solid var(--color-line);
		border-radius: 1rem;
		background: var(--color-surface-raised);
		box-shadow: 0 1.5rem 4rem color-mix(in oklab, var(--color-ink-0) 25%, transparent);
		padding: 1.25rem;
	}
	.create-dialog-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		margin-bottom: 1.1rem;
	}
	.create-dialog-head h2 {
		margin: 0;
		font-size: 1rem;
		font-weight: 650;
		color: var(--color-ink-0);
	}
	.create-form {
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}
	.create-note {
		margin: 0;
		padding: 0.75rem;
		border-radius: 0.7rem;
		background: var(--color-surface-sunken);
		color: var(--color-ink-2);
		font-size: 0.78rem;
		line-height: 1.5;
	}
	.form-actions {
		display: flex;
		justify-content: flex-end;
		gap: 0.5rem;
	}
</style>
