<script lang="ts">
	import { t } from '$lib/i18n/ns/images-keys';
	import { useImageDetailController } from '$lib/stores/imageDetailController.svelte';
	import { ActivityIndicator, Alert, Button, Card, Field, Pill, TableShell, TextInput } from '$lib/components/ui';

	const s = useImageDetailController();
	const id = $props.id();
	const controlsLocked = $derived(!s.canEditMetadata || s.windowsSaving || s.editingProps || s.savingProps || s.savingVisibility);
	const currentFields = [
		['os_type', 'windowsSetup.current.osType'],
		['os_distro', 'windowsSetup.current.osDistro'],
		['windows_initial_password_method', 'windowsSetup.current.method'],
		['os_admin_user', 'windowsSetup.current.account'],
		['img_config_drive', 'windowsSetup.current.configDrive'],
	] as const;
</script>

<section class="min-w-0 [overflow-wrap:anywhere]" data-testid="windows-service-setup" aria-labelledby={`${id}-title`}>
	<Card surface="base" padding="md">
		<div class="space-y-4">
			<div class="flex flex-wrap items-start justify-between gap-2">
				<h3 id={`${id}-title`} class="text-sm font-semibold text-ink-0">{t('windowsSetup.title')}</h3>
				<span data-testid="windows-setup-status" data-status={s.windowsStatus}>
					<Pill tone="neutral" class="!text-xs !whitespace-normal">{t(`windowsSetup.status.${s.windowsStatus}`)}</Pill>
				</span>
			</div>
			<div class="space-y-1 text-xs leading-relaxed text-ink-2">
				<p>{t('windowsSetup.description')}</p>
				<p>{t('windowsSetup.metadataOnly')}</p>
			</div>

			<dl class="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3 text-xs" data-testid="windows-setup-current">
				{#each currentFields as [key, label] (key)}
					<div class="min-w-0">
						<dt class="text-ink-2 mb-1">{t(label)}</dt>
						<dd class="text-ink-0 font-mono break-all" data-property={key}>{s.windowsCurrentProperties[key] === '' ? '""' : s.windowsCurrentProperties[key] ?? t('windowsSetup.unset')}</dd>
					</div>
				{/each}
			</dl>

			<div class="space-y-2 text-xs leading-relaxed text-ink-2" data-testid="windows-setup-requirements">
				<h4 class="font-semibold text-ink-1">{t('windowsSetup.requirementsTitle')}</h4>
				<ul class="list-disc pl-4 space-y-1">
					<li>{t('windowsSetup.requirements.guest')}</li>
					<li>{t('windowsSetup.requirements.hardware')}</li>
					<li>{t('windowsSetup.requirements.access')}</li>
				</ul>
			</div>
			<div data-testid="windows-setup-warning">
				<Alert tone="warning" title={t('windowsSetup.warningTitle')}>{t('windowsSetup.warning')}</Alert>
			</div>

			{#if s.windowsSuccess}
				<div data-testid="windows-setup-success">
					<Alert tone="success">{t('windowsSetup.saved')}</Alert>
				</div>
			{/if}
			{#if !s.canEditMetadata}
				<p class="text-xs leading-relaxed text-ink-2" data-testid="windows-setup-readonly">{t('windowsSetup.readonly')}</p>
			{:else}
				{#if s.editingProps || s.savingProps}
					<div data-testid="windows-setup-conflict">
						<Alert tone="neutral">{t('windowsSetup.draftConflict')}</Alert>
					</div>
				{/if}
				{#if !s.windowsEditing}
					<span data-testid="windows-setup-start">
						<Button variant="outline" dataTour="windows-setup-start" disabled={controlsLocked}
							onclick={() => { if (!controlsLocked) s.startWindowsSetup(); }} class="min-h-11 max-w-full !whitespace-normal">
							{t('windowsSetup.start')}
						</Button>
					</span>
				{:else}
					<form class="motion-fade space-y-4 border-t border-line pt-4" data-testid="windows-setup-form" aria-busy={s.windowsSaving}
						onsubmit={(event) => { event.preventDefault(); if (!controlsLocked && s.canSaveWindowsSetup) s.saveWindowsSetup(); }}>
						<fieldset disabled={controlsLocked} class="min-w-0 space-y-3">
							<Field label={t('windowsSetup.accountLabel')} for={`${id}-account`} required
								help={t('windowsSetup.accountHelp')} error={!s.windowsAccountValid ? t('windowsSetup.invalidAccount') : undefined}>
								<span data-testid="windows-setup-account">
									<TextInput id={`${id}-account`} bind:value={s.windowsAccount}
										disabled={controlsLocked} required autocomplete="off" ariaInvalid={!s.windowsAccountValid} />
								</span>
							</Field>
							<div class="grid grid-cols-1 gap-3 lg:grid-cols-2">
								<div>
									<label class="setup-choice" for={`${id}-win11`}>
										<input id={`${id}-win11`} data-testid="windows-setup-win11" type="checkbox" bind:checked={s.windowsWin11} disabled={controlsLocked} aria-describedby={`${id}-win11-help`} />
										<span>{t('windowsSetup.win11Label')}</span>
									</label>
									<p id={`${id}-win11-help`} class="text-xs leading-relaxed text-ink-2 mt-1">{t('windowsSetup.win11Help')}</p>
								</div>
								<div>
									<label class="setup-choice" for={`${id}-qga`}>
										<input id={`${id}-qga`} data-testid="windows-setup-qga" type="checkbox" bind:checked={s.windowsQga} disabled={controlsLocked} aria-describedby={`${id}-qga-help`} />
										<span>{t('windowsSetup.qgaLabel')}</span>
									</label>
									<p id={`${id}-qga-help`} class="text-xs leading-relaxed text-ink-2 mt-1">{t('windowsSetup.qgaHelp')}</p>
								</div>
							</div>
							<label class="setup-choice" for={`${id}-confirm`}>
								<input id={`${id}-confirm`} data-testid="windows-setup-confirmation" type="checkbox" bind:checked={s.windowsConfirmed} disabled={controlsLocked} required aria-describedby={`${id}-confirm-help`} />
								<span>{t('windowsSetup.acknowledge')}</span>
							</label>
							<p id={`${id}-confirm-help`} class="text-xs leading-relaxed text-ink-2" data-testid="windows-setup-ack-required">
								{#if !s.windowsConfirmed}{t('windowsSetup.ackRequired')}{/if}
							</p>
						</fieldset>

						<div class="space-y-2 text-xs" data-testid="windows-setup-preview">
							<h4 class="font-semibold text-ink-1">{t('windowsSetup.changesTitle')}</h4>
							{#if s.windowsChanges.length === 0}
								<p class="text-ink-2">{t('windowsSetup.noChanges')}</p>
							{:else}
								<TableShell class="min-w-0">
								<table class="!min-w-0 block w-full table-fixed md:table">
									<thead class="sr-only"><tr><th scope="col">{t('windowsSetup.property')}</th><th scope="col">{t('windowsSetup.currentValue')}</th><th scope="col">{t('windowsSetup.proposedValue')}</th></tr></thead>
									<tbody class="block divide-y divide-line md:table-row-group">
										{#each s.windowsChanges as change (change.key)}
											<tr class="grid grid-cols-1 gap-2 py-2 md:table-row" data-testid="windows-setup-change" data-property={change.key}>
												<td class="min-w-0 font-mono text-ink-1 break-all align-top md:py-2 md:pr-3"><span class="sr-only">{t('windowsSetup.property')}: </span>{change.key}</td>
												<td class="min-w-0 space-y-1 align-top md:py-2 md:pr-3">
													<span class="block text-ink-2">{t('windowsSetup.currentValue')}</span>
													<span class="block font-mono text-ink-0 break-all" data-testid="windows-setup-change-current">{change.current === '' ? '""' : change.current ?? t('windowsSetup.unset')}</span>
												</td>
												<td class="min-w-0 space-y-1 align-top md:py-2">
													<span class="block text-ink-2">{t('windowsSetup.proposedValue')}</span>
													<span class="block font-mono text-ink-0 break-all" data-testid="windows-setup-change-proposed">{change.proposed}</span>
												</td>
											</tr>
										{/each}
									</tbody>
								</table>
								</TableShell>
							{/if}
							<p class="text-ink-2 leading-relaxed">{t('windowsSetup.preserved')}</p>
						</div>

						{#if s.windowsError}
							<div data-testid="windows-setup-error"><Alert tone="danger">{s.windowsError}</Alert></div>
						{/if}
						<div class="flex flex-wrap justify-end gap-2">
							<span data-testid="windows-setup-cancel" class="max-w-full">
								<Button variant="outline" dataTour="windows-setup-cancel" disabled={controlsLocked}
									onclick={() => { if (!controlsLocked) s.cancelWindowsSetup(); }} class="min-h-11 max-w-full !whitespace-normal">{t('windowsSetup.cancel')}</Button>
							</span>
							<span data-testid="windows-setup-save" class="max-w-full">
								<Button type="submit" dataTour="windows-setup-save" disabled={controlsLocked || !s.canSaveWindowsSetup} ariaBusy={s.windowsSaving}
									class="min-h-11 max-w-full !whitespace-normal">
									{#if s.windowsSaving}<ActivityIndicator size="xs" label={t('windowsSetup.saving')} />{:else if s.windowsError}{t('windowsSetup.retry')}{:else}{t('windowsSetup.save')}{/if}
								</Button>
							</span>
						</div>
					</form>
				{/if}
			{/if}
		</div>
	</Card>
</section>

<style>
	.setup-choice {
		display: flex;
		align-items: flex-start;
		gap: 0.5rem;
		min-height: 2.75rem;
		font-size: 0.8125rem;
		line-height: 1.5;
		color: var(--color-ink-1);
	}
	.setup-choice input {
		width: 1rem;
		height: 1rem;
		flex-shrink: 0;
		margin-top: 0.125rem;
		accent-color: var(--color-action-warm);
	}
	.setup-choice input:disabled { opacity: 0.55; cursor: not-allowed; }
	.setup-choice input:focus-visible {
		outline: none;
		box-shadow: var(--focus-ring);
	}
</style>
