<script lang="ts">
	import { Alert, Button, Card, Field, Modal, TextareaInput, TextInput } from '$lib/components/ui';
	import { t } from '$lib/i18n/ns/images-keys';
	let {
		open = $bindable(),
		onCreate,
	}: {
		open: boolean;
		onCreate: (form: { name: string; public_key: string }) => Promise<{ private_key?: string } | string>;
	} = $props();

	let form = $state({ name: '', public_key: '' });
	let creating = $state(false);
	let error = $state('');
	let createdPrivateKey = $state<string | null>(null);

	$effect(() => {
		if (!open) {
			form = { name: '', public_key: '' };
			error = '';
			creating = false;
			createdPrivateKey = null;
		}
	});

	function handleFileUpload(event: Event) {
		const input = event.target as HTMLInputElement;
		const file = input.files?.[0];
		if (!file) return;
		if (file.size > 65536) {
			error = t('keypairCreate.error.fileTooLarge');
			input.value = '';
			return;
		}
		const reader = new FileReader();
		reader.onload = (e) => {
			const content = ((e.target?.result as string) ?? '').trim();
			if (content && !/^(ssh-rsa|ssh-ed25519|ssh-dss|ecdsa-sha2-\S+)\s/.test(content)) {
				error = t('keypairCreate.error.invalidPublicKey');
				return;
			}
			form.public_key = content;
		};
		reader.readAsText(file);
		input.value = '';
	}

	async function submit() {
		if (!form.name.trim()) return;
		creating = true;
		error = '';
		const result = await onCreate({ ...form });
		creating = false;
		if (typeof result === 'string') {
			error = result;
		} else {
			if (result.private_key) {
				createdPrivateKey = result.private_key;
			} else {
				open = false;
			}
		}
	}
</script>

<Modal bind:open dismissible={!creating} labelledBy="keypair-create-title">
	<div class="w-[min(28rem,calc(100vw-2rem))] max-h-[calc(100dvh-2rem)] overflow-y-auto">
		<Card surface="modal" padding="lg">
			{#if createdPrivateKey}
				<h2 id="keypair-create-title" class="mb-3 text-lg font-semibold text-ink-0">{t('keypairCreate.privateKey.title')}</h2>
				<Alert tone="warning" class="mb-3">{t('keypairCreate.privateKey.warning')}</Alert>
				<pre class="mb-4 max-h-48 overflow-auto rounded-md bg-surface-sunken p-3 text-xs text-green-300">{createdPrivateKey}</pre>
				<Button onclick={() => (open = false)} variant="primary" class="w-full">{t('keypairCreate.actions.confirm')}</Button>
			{:else}
				<h2 id="keypair-create-title" class="mb-5 text-lg font-semibold text-ink-0">{t('keypairCreate.title')}</h2>
				<div class="space-y-4">
					<Field label={t('keypairCreate.form.name.label')} for="keypair-name" required>
						<TextInput id="keypair-name" bind:value={form.name} placeholder={t('keypairCreate.form.name.placeholder')} />
					</Field>
					<Field label={t('keypairCreate.form.publicKey.label')} help={t('keypairCreate.form.publicKey.help')} for="keypair-pubkey">
						<div class="mb-1.5 flex justify-end">
							<label class="cursor-pointer text-xs text-warm-text transition-colors hover:text-warm-text-hover">
								{t('keypairCreate.form.publicKey.chooseFile')}
								<input type="file" accept=".pub,.pem,.txt" class="hidden" onchange={handleFileUpload} />
							</label>
						</div>
						<TextareaInput
							id="keypair-pubkey"
							bind:value={form.public_key}
							placeholder={t('keypairCreate.form.publicKey.placeholder')}
							rows={3}
							class="font-mono"
							ariaDescribedBy="keypair-pubkey-message"
						/>
					</Field>
				</div>
				{#if error}<Alert tone="danger" class="mt-3">{error}</Alert>{/if}
				<div class="mt-6 flex justify-end gap-3">
					<Button onclick={() => (open = false)} variant="secondary" disabled={creating}>{t('keypairCreate.actions.cancel')}</Button>
					<Button onclick={submit} disabled={creating || !form.name.trim()} variant="primary">{creating ? t('keypairCreate.actions.creating') : t('keypairCreate.actions.create')}</Button>
				</div>
			{/if}
		</Card>
	</div>
</Modal>
