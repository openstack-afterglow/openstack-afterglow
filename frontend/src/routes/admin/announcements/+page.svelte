<script lang="ts">
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import { createTableView } from '$lib/utils/tableView.svelte';
	import TableColumnHeader from '$lib/components/ui/TableColumnHeader.svelte';
	import TableViewControls from '$lib/components/ui/TableViewControls.svelte';
	import RegexSearch from '$lib/components/ui/RegexSearch.svelte';
	import PageShell from '$lib/components/ui/PageShell.svelte';
	import { onDestroy } from 'svelte';
	import { auth, authReady, logoutInProgress, projectSwitching } from '$lib/stores/auth';
	import { sessionScopeKey } from '$lib/utils/authSession';
	import { createEmailOwner } from '$lib/utils/emailOwner';
	import { t as tm } from '$lib/i18n/ns/admin-email';
	import AnnouncementEmailAction from '$lib/components/admin/AnnouncementEmailAction.svelte';
	import MailOperationResult from '$lib/components/admin/MailOperationResult.svelte';
	import { createAdminAnnouncementsController } from '$lib/stores/adminAnnouncementsController.svelte';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { toast } from '$lib/stores/toast';
	import { formatIsoDateTime } from '$lib/utils/format';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import SearchSelect from '$lib/components/ui/SearchSelect.svelte';
	import type { AnnouncementAdmin, AnnouncementSeverity, AnnouncementTargetType } from '$lib/types/announcements';
	import { t } from '$lib/i18n/ns/admin-system';
	import { t as td } from '$lib/i18n/ns/domain-admin';
	import Field from '$lib/components/ui/Field.svelte';
	import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
	import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';
	import TutorialStartButton from '$lib/tutorial/TutorialStartButton.svelte';

	const FALLBACK_SEVERITIES: AnnouncementSeverity[] = ['info', 'warning', 'danger'];
	const FALLBACK_TARGET_TYPES: AnnouncementTargetType[] = ['all', 'project', 'user'];

	let ownerEpoch = $state(0);
	let mailBusy = $state(false);
	let sendEmail = $state(false);
	let emailAttempt = $state('');
	let emailUnknown = $state(false);
	// Announcement created in this page session; the tutorial anchors only its delete control.
	let lastCreatedId = $state<number | null>(null);
	const unavailable = $derived(!$auth.token || !$authReady || !$auth.isSystemAdmin || $logoutInProgress || $projectSwitching);
	const ctrl = createAdminAnnouncementsController({
		token: () => $auth.token ?? undefined,
		projectId: () => $auth.projectId ?? undefined,
		ownerKey: () => sessionScopeKey($auth),
		ownerEpoch: () => ownerEpoch,
		allowed: () => !unavailable,
	});
	const mutationBusy = $derived(ctrl.creating || ctrl.deleting || ctrl.togglingId !== null || mailBusy || unavailable);


	let form = $state({
		title: '',
		body: '',
		severity: 'info' as AnnouncementSeverity,
		target_type: 'all' as AnnouncementTargetType,
		target_id: '',
		starts_at: '',
		ends_at: '',
	});
	const owner = createEmailOwner(() => {
		ownerEpoch++; ctrl.invalidateOwner(); resetForm(); mailBusy = false; sendEmail = false; emailAttempt = ''; emailUnknown = false; lastCreatedId = null;
		if (owner.capture()) { void ctrl.load(); void ctrl.loadOptions(); void ctrl.loadDomains(); }
	});
	onDestroy(ctrl.dispose);
	const targetOptions = $derived(
		form.target_type === 'project'
			? ctrl.allProjects.map((project) => ({ value: project.id, label: project.name, description: project.id }))
			: ctrl.allUsers.map((user) => ({ value: user.id, label: user.name, description: user.id })),
	);
	const targetLoading = $derived(form.target_type === 'project' ? ctrl.projectsLoading : ctrl.usersLoading);
	const targetEmptyText = $derived(
		(form.target_type === 'project' ? ctrl.projectsError : ctrl.usersError)
			|| (form.target_type === 'project' ? t('announcements.empty.projects') : t('announcements.empty.users')),
	);

	function resetForm() {
		form = { title: '', body: '', severity: 'info', target_type: 'all', target_id: '', starts_at: '', ends_at: '' };
		sendEmail = false;
	}

	function onTargetTypeChange() {
		form.target_id = '';
		ctrl.selectDomain(form.target_type === 'all' ? '' : ctrl.domainId, form.target_type === 'project' ? 'project' : 'user');
	}

	async function handleCreate() {
		if (mutationBusy || emailUnknown) return;
		const scope = owner.capture(); if (!scope) return;
		ctrl.createError = '';
		if (!form.title.trim() || !form.body.trim()) {
			ctrl.createError = t('announcements.validation.titleBodyRequired');
			return;
		}
		if (form.target_type !== 'all' && !form.target_id) {
			ctrl.createError = t('announcements.validation.targetRequired');
			return;
		}
		const requestedEmail = sendEmail;
		const operationId = requestedEmail ? crypto.randomUUID() : '';
		if (requestedEmail) emailAttempt = operationId;
		const previousIds = new Set(ctrl.announcements.map((a) => a.id));
		const submittedTitle = form.title.trim();
		const result = await ctrl.create({
			title: form.title,
			body: form.body,
			severity: form.severity,
			target_type: form.target_type,
			target_id: form.target_type === 'all' ? null : form.target_id,
			starts_at: form.starts_at ? new Date(form.starts_at).toISOString() : null,
			ends_at: form.ends_at ? new Date(form.ends_at).toISOString() : null,
			send_email: requestedEmail,
			...(requestedEmail ? { email_operation_id: operationId } : {}),
		});
		if (!scope.current()) return;
		emailUnknown = result.status === 'indeterminate';
		if (result.status === 'invalid' || result.status === 'rejected') emailAttempt = '';
		if (result.status === 'ok') {
			lastCreatedId = ctrl.announcements.find((a) => !previousIds.has(a.id) && a.title === submittedTitle)?.id ?? null;
			resetForm();
			toast.success(t('announcements.toast.sent'));
		}
	}

	async function handleToggleActive(a: AnnouncementAdmin) {
		if (mutationBusy) return;
		await ctrl.toggleActive(a);
	}

	async function handleDelete(a: AnnouncementAdmin) {
		if (mutationBusy) return;
		const scope = owner.capture(); if (!scope) return;
		const confirmed = await confirmDialog(t('announcements.deleteDialog.body', { title: a.title }));
		if (!confirmed || !scope.current() || mutationBusy) return;
		ctrl.deleteTarget = a;
		await ctrl.confirmDelete();
		if (ctrl.deleteError) toast.error(ctrl.deleteError);
	}

	function targetLabel(a: AnnouncementAdmin): string {
		if (a.target_type === 'all') return t('announcements.target.all');
		if (a.target_type === 'project') {
			const match = ctrl.allProjects.find((p) => p.id === a.target_id);
			return t('announcements.target.project', { name: String(match?.name ?? a.target_id) });
		}
		const match = ctrl.allUsers.find((u) => u.id === a.target_id);
		return t('announcements.target.user', { name: String(match?.name ?? a.target_id) });
	}

	function severityLabel(s: AnnouncementSeverity): string {
		return t(({ info: 'announcements.severity.info', warning: 'announcements.severity.warning', danger: 'announcements.severity.danger' } as const)[s]);
	}

	function severityStyle(s: AnnouncementSeverity): string {
		const color = {
			info: 'var(--color-state-info)',
			warning: 'var(--color-state-warning)',
			danger: 'var(--color-state-danger)',
		}[s];
		return `color: ${color}; border-color: color-mix(in oklab, ${color} 40%, transparent); background: color-mix(in oklab, ${color} 15%, transparent);`;
	}

	function activeStyle(isActive: boolean): string {
		if (isActive) {
			return 'color: var(--color-state-success); border-color: color-mix(in oklab, var(--color-state-success) 40%, transparent); background: color-mix(in oklab, var(--color-state-success) 15%, transparent);';
		}
		return 'color: var(--color-ink-3); border-color: var(--color-line); background: var(--color-surface-sunken);';
	}
	const tableSearchId = $props.id();
	let tableSearch = $state('');
	const tableView = createTableView<AnnouncementAdmin>({ rows: () => ctrl.announcements, locale: () => intlLocale(), search: () => tableSearch, columns: () => [{ key: 'sentAt', label: t('announcements.history.sentAt'), value: row => row.created_at }, { key: 'title', label: t('announcements.history.announcementTitle'), value: row => row.title }, { key: 'severity', label: t('announcements.history.severity'), value: row => severityLabel(row.severity) }, { key: 'target', label: t('announcements.history.target'), value: row => targetLabel(row) }, { key: 'status', label: t('announcements.history.status'), value: row => row.is_active ? t('announcements.status.active') : t('announcements.status.inactive') }, { key: 'author', label: t('announcements.history.author'), value: row => row.created_by_username }] });
</script>

<PageShell>
	<PageHeader breadcrumb={t('announcements.breadcrumb')} title={t('announcements.title')} subtitle={t('announcements.subtitle')}>
		{#snippet actions()}
			<TutorialStartButton tour="admin-announcements" compactOnMobile />
		{/snippet}
	</PageHeader>

	{#if ctrl.error}
		<Alert tone="danger" class="mb-4">{ctrl.error}</Alert>
	{/if}

	<Card padding="lg" class="mb-5">
		<h2 class="text-sm font-semibold text-[var(--color-ink-0)] mb-4">{t('announcements.form.title')}</h2>
		{#if ctrl.createError}
			<Alert tone="danger" class="mb-4">{ctrl.createError}</Alert>
		{/if}
		{#if emailUnknown}<Alert tone="warning" class="mb-4">{tm('unknown')}</Alert>{/if}
		{#if emailAttempt && !ctrl.emailOperation}<p class="mb-3 text-sm font-mono [overflow-wrap:anywhere]">{tm('operation', { id: emailAttempt })}</p>{/if}
		{#if ctrl.emailOperation}<MailOperationResult operation={ctrl.emailOperation} />{/if}
		<fieldset disabled={mutationBusy || emailUnknown} class="min-w-0" data-tour="admin-announcements-form">
		<div class="space-y-4">
			<div>
				<label class="block text-xs text-[var(--color-ink-2)] mb-1.5 uppercase tracking-wide" for="announcement-title">{t('announcements.form.titleLabel')}</label>
				<input
					id="announcement-title"
					bind:value={form.title}
					type="text"
					maxlength="200"
					class="w-full bg-[var(--color-surface-sunken)] border border-[var(--color-line-2)] rounded-lg px-3 py-2 text-[var(--color-ink-0)] text-sm focus:outline-none focus:border-[var(--color-accent)]"
				/>
			</div>
			<div>
				<label class="block text-xs text-[var(--color-ink-2)] mb-1.5 uppercase tracking-wide" for="announcement-body">{t('announcements.form.bodyLabel')}</label>
				<textarea
					id="announcement-body"
					bind:value={form.body}
					rows="4"
					maxlength="10000"
					class="w-full bg-[var(--color-surface-sunken)] border border-[var(--color-line-2)] rounded-lg px-3 py-2 text-[var(--color-ink-0)] text-sm focus:outline-none focus:border-[var(--color-accent)] resize-y"
				></textarea>
			</div>
			<div class="grid grid-cols-1 md:grid-cols-3 gap-4" data-tour="admin-announcements-audience">
				<div>
					<label class="block text-xs text-[var(--color-ink-2)] mb-1.5 uppercase tracking-wide" for="announcement-severity">{t('announcements.form.severityLabel')}</label>
					<select
						id="announcement-severity"
						bind:value={form.severity}
						class="w-full bg-[var(--color-surface-sunken)] border border-[var(--color-line-2)] rounded-lg px-3 py-2 text-[var(--color-ink-0)] text-sm focus:outline-none focus:border-[var(--color-accent)]"
					>
						{#each (ctrl.options?.severities ?? FALLBACK_SEVERITIES) as s}
							<option value={s}>{severityLabel(s)}</option>
						{/each}
					</select>
				</div>
				<div>
					<label class="block text-xs text-[var(--color-ink-2)] mb-1.5 uppercase tracking-wide" for="announcement-target-type">{t('announcements.form.targetLabel')}</label>
					<select
						id="announcement-target-type"
						bind:value={form.target_type}
						onchange={onTargetTypeChange}
						class="w-full bg-[var(--color-surface-sunken)] border border-[var(--color-line-2)] rounded-lg px-3 py-2 text-[var(--color-ink-0)] text-sm focus:outline-none focus:border-[var(--color-accent)]"
					>
						{#each (ctrl.options?.target_types ?? FALLBACK_TARGET_TYPES) as targetType}
							<option value={targetType}>{targetType === 'all' ? t('announcements.targetType.all') : targetType === 'project' ? t('announcements.targetType.project') : t('announcements.targetType.user')}</option>
						{/each}
					</select>
				</div>
				{#if form.target_type !== 'all'}
					<div class="min-w-0">
						<Field for="announcement-user-domain" label={td('scope.domain')} help={td('scope.help')}>
							<SearchSelect id="announcement-user-domain" value={ctrl.domainId} options={ctrl.domains.map(domain => ({ value: domain.id, label: domain.name, description: domain.id }))} loading={ctrl.domainsLoading} placeholder={td('scope.choose')} ariaLabel={td('scope.domain')} onchange={(value) => { form.target_id = ''; ctrl.selectDomain(value, form.target_type === 'project' ? 'project' : 'user'); }} />
						</Field>
						{#if ctrl.domainsError}<Alert class="mt-2">{ctrl.domainsError}<Button variant="ghost" size="sm" onclick={() => { form.target_id = ''; ctrl.selectDomain(''); void ctrl.loadDomains(); }}>{td('actions.refresh')}</Button></Alert>{/if}
						{#if ctrl.usersError}<Alert class="mt-2">{ctrl.usersError}<Button variant="ghost" size="sm" onclick={ctrl.loadUsers}>{td('actions.refresh')}</Button></Alert>{/if}
						{#if ctrl.projectsError}<Alert class="mt-2">{ctrl.projectsError}<Button variant="ghost" size="sm" onclick={ctrl.loadProjects}>{td('actions.refresh')}</Button></Alert>{/if}
					</div>
				{/if}
				{#if form.target_type !== 'all'}
					<div>
						<label class="block text-xs text-[var(--color-ink-2)] mb-1.5 uppercase tracking-wide" for="announcement-target-id">
							{form.target_type === 'project' ? t('announcements.picker.projectLabel') : t('announcements.picker.userLabel')}
						</label>
						<SearchSelect
							id="announcement-target-id"
							value={form.target_id}
							options={targetOptions}
							loading={targetLoading}
							disabled={!ctrl.domainId || ctrl.domainsLoading || !!ctrl.domainsError}
							placeholder={form.target_type === 'project' ? t('announcements.picker.projectPlaceholder') : t('announcements.picker.userPlaceholder')}
							searchPlaceholder={form.target_type === 'project' ? t('announcements.picker.projectSearchPlaceholder') : t('announcements.picker.userSearchPlaceholder')}
							emptyText={targetEmptyText}
							ariaLabel={form.target_type === 'project' ? t('announcements.picker.projectLabel') : t('announcements.picker.userLabel')}
							onchange={(value) => (form.target_id = value)}
						/>
					</div>
				{/if}
			</div>
			<div class="grid grid-cols-1 md:grid-cols-2 gap-4">
				<div>
					<label class="block text-xs text-[var(--color-ink-2)] mb-1.5 uppercase tracking-wide" for="announcement-starts-at">{t('announcements.form.startsAtLabel')}</label>
					<input
						id="announcement-starts-at"
						bind:value={form.starts_at}
						type="datetime-local"
						class="w-full bg-[var(--color-surface-sunken)] border border-[var(--color-line-2)] rounded-lg px-3 py-2 text-[var(--color-ink-0)] text-sm focus:outline-none focus:border-[var(--color-accent)]"
					/>
				</div>
				<div>
					<label class="block text-xs text-[var(--color-ink-2)] mb-1.5 uppercase tracking-wide" for="announcement-ends-at">{t('announcements.form.endsAtLabel')}</label>
					<input
						id="announcement-ends-at"
						bind:value={form.ends_at}
						type="datetime-local"
						class="w-full bg-[var(--color-surface-sunken)] border border-[var(--color-line-2)] rounded-lg px-3 py-2 text-[var(--color-ink-0)] text-sm focus:outline-none focus:border-[var(--color-accent)]"
					/>
				</div>
			</div>
			<label class="flex min-h-11 items-center gap-3 text-sm text-ink-1"><input id="announcement-send-email" type="checkbox" bind:checked={sendEmail} />{tm('sendWithAnnouncement')}</label>
			<p class="text-sm text-ink-2">{tm('schedule')}</p>
		</div>
		<div class="flex justify-end mt-5">
			<Button variant="accent" disabled={mutationBusy || emailUnknown} ariaBusy={ctrl.creating} onclick={handleCreate} dataTour="admin-announcements-submit">
				{#if ctrl.creating}<LoadingState variant="control" label="" aria-hidden="true" />{/if}{ctrl.creating ? t('announcements.actions.sending') : t('announcements.actions.send')}
			</Button>
		</div>
		</fieldset>
	</Card>

	<div data-tour="admin-announcements-history">
	<Card padding="lg">
		<h2 class="text-sm font-semibold text-[var(--color-ink-0)] mb-4">{t('announcements.history.title')}</h2>
		<RegexSearch id={tableSearchId} bind:value={tableSearch} /><TableViewControls view={tableView} />
		{#if ctrl.loading}
			<LoadingState variant="surface" />
		{:else if ctrl.announcements.length === 0}
			<div class="text-center text-[var(--color-ink-3)] text-sm py-8">{t('announcements.history.empty')}</div>
		{:else}
			<ResponsiveTable>
				{#snippet cards()}
					{#each tableView.rows as a (a.id)}
						<CompactResourceCard>
							<div class="flex min-w-0 items-start justify-between gap-2">
								<span class="min-w-0 font-medium">{a.title}</span>
								<span class="shrink-0 rounded border px-1.5 py-0.5 text-xs" style={severityStyle(a.severity)}>{severityLabel(a.severity)}</span>
							</div>
							<dl>
								<div><dt>{t('announcements.history.target')}</dt><dd>{targetLabel(a)}</dd></div>
								<div><dt>{t('announcements.history.sentAt')}</dt><dd>{formatIsoDateTime(a.created_at)}</dd></div>
							</dl>
							{#snippet details()}
								<dl><div><dt>{t('announcements.history.author')}</dt><dd>{a.created_by_username}</dd></div></dl>
							{/snippet}
							{#snippet actions()}
								<button
									onclick={() => handleToggleActive(a)}
									disabled={mutationBusy}
									class="rounded border px-3 py-2 text-xs transition-colors disabled:opacity-40"
									style={activeStyle(a.is_active)}
								>{a.is_active ? t('announcements.status.active') : t('announcements.status.inactive')}</button>
								<Button variant="danger" size="sm" disabled={mutationBusy} onclick={() => handleDelete(a)} dataTour={lastCreatedId === a.id ? 'admin-announcements-delete' : undefined}>{t('announcements.actions.delete')}</Button>
								<AnnouncementEmailAction announcement={a} disabled={mutationBusy} onbusy={(value) => { mailBusy = value; }} />
							{/snippet}
						</CompactResourceCard>
					{/each}
				{/snippet}
			<div class="overflow-x-auto">
				<table class="w-full text-sm">
					<thead>
						<tr class="text-left text-xs uppercase tracking-wide text-[var(--color-ink-3)] border-b border-[var(--color-line)]">
<TableColumnHeader view={tableView} columnKey="sentAt" />
<TableColumnHeader view={tableView} columnKey="title" />
<TableColumnHeader view={tableView} columnKey="severity" />
<TableColumnHeader view={tableView} columnKey="target" />
<TableColumnHeader view={tableView} columnKey="status" />
<TableColumnHeader view={tableView} columnKey="author" />
							<th class="py-2 font-medium"></th>
						</tr>
					</thead>
					<tbody>
						{#each tableView.rows as a (a.id)}
							<tr class="border-b border-[var(--color-line)] last:border-0">
								<td class="py-2.5 pr-4 text-[var(--color-ink-2)] tabular-nums whitespace-nowrap">{formatIsoDateTime(a.created_at)}</td>
								<td class="py-2.5 pr-4 text-[var(--color-ink-0)] max-w-[240px] truncate" title={a.title}>{a.title}</td>
								<td class="py-2.5 pr-4">
									<span class="px-1.5 py-0.5 rounded text-xs border" style={severityStyle(a.severity)}>{severityLabel(a.severity)}</span>
								</td>
								<td class="py-2.5 pr-4 text-[var(--color-ink-1)] whitespace-nowrap">{targetLabel(a)}</td>
								<td class="py-2.5 pr-4">
									<button
										onclick={() => handleToggleActive(a)}
										disabled={mutationBusy}
										class="px-2 py-0.5 rounded text-xs border transition-colors disabled:opacity-40"
										style={activeStyle(a.is_active)}
									>{a.is_active ? t('announcements.status.active') : t('announcements.status.inactive')}</button>
								</td>
								<td class="py-2.5 pr-4 text-[var(--color-ink-2)] whitespace-nowrap">{a.created_by_username}</td>
								<td class="py-2.5">
									<AnnouncementEmailAction announcement={a} disabled={mutationBusy} onbusy={(value) => { mailBusy = value; }} />
									<button
										data-tour={lastCreatedId === a.id ? 'admin-announcements-delete' : undefined}
										onclick={() => handleDelete(a)}
										aria-label={t('announcements.actions.delete')}
										disabled={mutationBusy}
										class="p-1.5 text-[var(--color-ink-3)] hover:text-[var(--color-state-danger)] transition-colors rounded-md hover:bg-[var(--color-surface-sunken)]"
									>
										<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>
									</button>
								</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
			</ResponsiveTable>
		{/if}
	</Card>
	</div>
</PageShell>
