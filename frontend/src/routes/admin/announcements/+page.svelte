<script lang="ts">
	import { onMount } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { createAdminAnnouncementsController } from '$lib/stores/adminAnnouncementsController.svelte';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { toast } from '$lib/stores/toast';
	import { formatIsoDateTime } from '$lib/utils/format';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import SearchSelect from '$lib/components/ui/SearchSelect.svelte';
	import type { AnnouncementAdmin, AnnouncementSeverity, AnnouncementTargetType } from '$lib/types/announcements';

	const FALLBACK_SEVERITIES: AnnouncementSeverity[] = ['info', 'warning', 'danger'];
	const FALLBACK_TARGET_TYPES: AnnouncementTargetType[] = ['all', 'project', 'user'];

	const ctrl = createAdminAnnouncementsController({
		token: () => $auth.token ?? undefined,
		projectId: () => $auth.projectId ?? undefined,
	});

	onMount(() => {
		void ctrl.load();
		void ctrl.loadOptions();
	});

	let form = $state({
		title: '',
		body: '',
		severity: 'info' as AnnouncementSeverity,
		target_type: 'all' as AnnouncementTargetType,
		target_id: '',
		starts_at: '',
		ends_at: '',
	});
	const targetOptions = $derived(
		form.target_type === 'project'
			? ctrl.allProjects.map((project) => ({ value: project.id, label: project.name, description: project.id }))
			: ctrl.allUsers.map((user) => ({ value: user.id, label: user.name, description: user.id })),
	);
	const targetLoading = $derived(form.target_type === 'project' ? ctrl.projectsLoading : ctrl.usersLoading);
	const targetEmptyText = $derived(
		(form.target_type === 'project' ? ctrl.projectsError : ctrl.usersError)
			|| (form.target_type === 'project' ? '일치하는 프로젝트가 없습니다' : '일치하는 유저가 없습니다'),
	);

	function resetForm() {
		form = { title: '', body: '', severity: 'info', target_type: 'all', target_id: '', starts_at: '', ends_at: '' };
	}

	function onTargetTypeChange() {
		form.target_id = '';
		if (form.target_type === 'project') void ctrl.loadProjects();
		if (form.target_type === 'user') void ctrl.loadUsers();
	}

	async function handleCreate() {
		ctrl.createError = '';
		if (!form.title.trim() || !form.body.trim()) {
			ctrl.createError = '제목과 본문을 입력하세요';
			return;
		}
		if (form.target_type !== 'all' && !form.target_id) {
			ctrl.createError = '대상을 선택하세요';
			return;
		}
		const ok = await ctrl.create({
			title: form.title,
			body: form.body,
			severity: form.severity,
			target_type: form.target_type,
			target_id: form.target_type === 'all' ? null : form.target_id,
			starts_at: form.starts_at ? new Date(form.starts_at).toISOString() : null,
			ends_at: form.ends_at ? new Date(form.ends_at).toISOString() : null,
		});
		if (ok) {
			resetForm();
			toast.success('공지를 발송했습니다');
		}
	}

	async function handleToggleActive(a: AnnouncementAdmin) {
		await ctrl.toggleActive(a);
	}

	async function handleDelete(a: AnnouncementAdmin) {
		const confirmed = await confirmDialog(`"${a.title}" 공지를 삭제하시겠습니까? 되돌릴 수 없습니다.`);
		if (!confirmed) return;
		ctrl.deleteTarget = a;
		await ctrl.confirmDelete();
		if (ctrl.deleteError) toast.error(ctrl.deleteError);
	}

	function targetLabel(a: AnnouncementAdmin): string {
		if (a.target_type === 'all') return '전체';
		if (a.target_type === 'project') {
			const match = ctrl.allProjects.find((p) => p.id === a.target_id);
			return `프로젝트: ${match?.name ?? a.target_id}`;
		}
		const match = ctrl.allUsers.find((u) => u.id === a.target_id);
		return `유저: ${match?.name ?? a.target_id}`;
	}

	function severityLabel(s: AnnouncementSeverity): string {
		return { info: '안내', warning: '경고', danger: '위험' }[s];
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
</script>

<div class="p-4 md:p-6 max-w-6xl mx-auto">
	<PageHeader breadcrumb="ADMIN / ANNOUNCEMENTS" title="공지 관리" subtitle="전체 · 특정 프로젝트 · 특정 유저에게 공지를 발송합니다" />

	{#if ctrl.error}
		<Alert tone="danger" class="mb-4">{ctrl.error}</Alert>
	{/if}

	<Card padding="lg" class="mb-5">
		<h2 class="text-sm font-semibold text-[var(--color-ink-0)] mb-4">새 공지 작성</h2>
		{#if ctrl.createError}
			<Alert tone="danger" class="mb-4">{ctrl.createError}</Alert>
		{/if}
		<div class="space-y-4">
			<div>
				<label class="block text-xs text-[var(--color-ink-2)] mb-1.5 uppercase tracking-wide" for="announcement-title">제목</label>
				<input
					id="announcement-title"
					bind:value={form.title}
					type="text"
					maxlength="200"
					class="w-full bg-[var(--color-surface-sunken)] border border-[var(--color-line-2)] rounded-lg px-3 py-2 text-[var(--color-ink-0)] text-sm focus:outline-none focus:border-[var(--color-accent)]"
				/>
			</div>
			<div>
				<label class="block text-xs text-[var(--color-ink-2)] mb-1.5 uppercase tracking-wide" for="announcement-body">본문</label>
				<textarea
					id="announcement-body"
					bind:value={form.body}
					rows="4"
					maxlength="10000"
					class="w-full bg-[var(--color-surface-sunken)] border border-[var(--color-line-2)] rounded-lg px-3 py-2 text-[var(--color-ink-0)] text-sm focus:outline-none focus:border-[var(--color-accent)] resize-y"
				></textarea>
			</div>
			<div class="grid grid-cols-1 md:grid-cols-3 gap-4">
				<div>
					<label class="block text-xs text-[var(--color-ink-2)] mb-1.5 uppercase tracking-wide" for="announcement-severity">심각도</label>
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
					<label class="block text-xs text-[var(--color-ink-2)] mb-1.5 uppercase tracking-wide" for="announcement-target-type">대상</label>
					<select
						id="announcement-target-type"
						bind:value={form.target_type}
						onchange={onTargetTypeChange}
						class="w-full bg-[var(--color-surface-sunken)] border border-[var(--color-line-2)] rounded-lg px-3 py-2 text-[var(--color-ink-0)] text-sm focus:outline-none focus:border-[var(--color-accent)]"
					>
						{#each (ctrl.options?.target_types ?? FALLBACK_TARGET_TYPES) as t}
							<option value={t}>{t === 'all' ? '전체 유저' : t === 'project' ? '특정 프로젝트' : '특정 유저'}</option>
						{/each}
					</select>
				</div>
				{#if form.target_type !== 'all'}
					<div>
						<label class="block text-xs text-[var(--color-ink-2)] mb-1.5 uppercase tracking-wide" for="announcement-target-id">
							{form.target_type === 'project' ? '프로젝트 선택' : '유저 선택'}
						</label>
						<SearchSelect
							id="announcement-target-id"
							value={form.target_id}
							options={targetOptions}
							loading={targetLoading}
							placeholder={form.target_type === 'project' ? '프로젝트를 선택하세요' : '유저를 선택하세요'}
							searchPlaceholder={form.target_type === 'project' ? '프로젝트 이름 또는 ID 검색' : '유저 이름 또는 ID 검색'}
							emptyText={targetEmptyText}
							ariaLabel={form.target_type === 'project' ? '프로젝트 선택' : '유저 선택'}
							onchange={(value) => (form.target_id = value)}
						/>
					</div>
				{/if}
			</div>
			<div class="grid grid-cols-1 md:grid-cols-2 gap-4">
				<div>
					<label class="block text-xs text-[var(--color-ink-2)] mb-1.5 uppercase tracking-wide" for="announcement-starts-at">시작 시각 (선택)</label>
					<input
						id="announcement-starts-at"
						bind:value={form.starts_at}
						type="datetime-local"
						class="w-full bg-[var(--color-surface-sunken)] border border-[var(--color-line-2)] rounded-lg px-3 py-2 text-[var(--color-ink-0)] text-sm focus:outline-none focus:border-[var(--color-accent)]"
					/>
				</div>
				<div>
					<label class="block text-xs text-[var(--color-ink-2)] mb-1.5 uppercase tracking-wide" for="announcement-ends-at">종료 시각 (선택)</label>
					<input
						id="announcement-ends-at"
						bind:value={form.ends_at}
						type="datetime-local"
						class="w-full bg-[var(--color-surface-sunken)] border border-[var(--color-line-2)] rounded-lg px-3 py-2 text-[var(--color-ink-0)] text-sm focus:outline-none focus:border-[var(--color-accent)]"
					/>
				</div>
			</div>
		</div>
		<div class="flex justify-end mt-5">
			<Button variant="accent" disabled={ctrl.creating} onclick={handleCreate}>
				{ctrl.creating ? '발송 중...' : '공지 발송'}
			</Button>
		</div>
	</Card>

	<Card padding="lg">
		<h2 class="text-sm font-semibold text-[var(--color-ink-0)] mb-4">발송 이력</h2>
		{#if ctrl.loading}
			<LoadingSkeleton variant="table" rows={5} />
		{:else if ctrl.announcements.length === 0}
			<div class="text-center text-[var(--color-ink-3)] text-sm py-8">발송된 공지가 없습니다</div>
		{:else}
			<div class="overflow-x-auto">
				<table class="w-full text-sm">
					<thead>
						<tr class="text-left text-xs uppercase tracking-wide text-[var(--color-ink-3)] border-b border-[var(--color-line)]">
							<th class="py-2 pr-4 font-medium">발송일</th>
							<th class="py-2 pr-4 font-medium">제목</th>
							<th class="py-2 pr-4 font-medium">심각도</th>
							<th class="py-2 pr-4 font-medium">대상</th>
							<th class="py-2 pr-4 font-medium">상태</th>
							<th class="py-2 pr-4 font-medium">작성자</th>
							<th class="py-2 font-medium"></th>
						</tr>
					</thead>
					<tbody>
						{#each ctrl.announcements as a (a.id)}
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
										disabled={ctrl.togglingId === a.id}
										class="px-2 py-0.5 rounded text-xs border transition-colors disabled:opacity-40"
										style={activeStyle(a.is_active)}
									>{a.is_active ? '게시중' : '비활성'}</button>
								</td>
								<td class="py-2.5 pr-4 text-[var(--color-ink-2)] whitespace-nowrap">{a.created_by_username}</td>
								<td class="py-2.5">
									<button
										onclick={() => handleDelete(a)}
										aria-label="공지 삭제"
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
		{/if}
	</Card>
</div>
