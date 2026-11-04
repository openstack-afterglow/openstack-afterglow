import { onDestroy, untrack } from 'svelte';
import { get } from 'svelte/store';
import { api, ApiError } from '$lib/api/client';
import { auth } from '$lib/stores/auth';
import { t } from '$lib/i18n/ns/usage-schedule';
import type { UsageScheduleDraft, UsageScheduleInfo } from '$lib/types/instanceUsage';
import { defaultUsageDraft, scheduleDraft, usageDraftError, usagePayload } from '$lib/utils/instanceUsage';
import { sessionScopeKey } from '$lib/utils/authSession';
import { beginExperienceAction, beginExperienceLoad, experienceApplied, experienceDiscarded, experienceState, type ExperienceContext } from '$lib/utils/experience';

interface UsageRequestOwner {
	id: string;
	project: string | undefined;
	admin: boolean;
	token: string | undefined;
	headerProject: string | undefined;
	user: string | null;
	epoch: number;
	generation: number;
}

export function createInstanceUsageController(options: {
	instanceId: () => string; projectId: () => string | undefined; adminMode: () => boolean;
	canWrite: () => boolean; onUpdated?: () => void;
}) {
	let schedule = $state<UsageScheduleInfo | null>(null);
	let draft = $state<UsageScheduleDraft>(defaultUsageDraft());
	let loading = $state(false);
	let saving = $state(false);
	let error = $state('');
	let saved = $state(false);
	let confirmed = $state(false);
	let authEpoch = $state(0);
	let generation = 0;
	let controller: AbortController | null = null;
	let disposed = false;
	let sessionOwner = '';
	const unsubscribe = auth.subscribe(state => {
		const next = state.token ? sessionScopeKey(state) : '';
		if (next !== sessionOwner) { sessionOwner = next; authEpoch += 1; }
	});

	function snapshot(): UsageRequestOwner {
		const state = get(auth);
		return { id: options.instanceId(), project: options.projectId(), admin: options.adminMode(),
			token: state.token ?? undefined, headerProject: state.projectId ?? undefined,
			user: state.userId, epoch: authEpoch, generation };
	}
	function current(owner: UsageRequestOwner) {
		const state = get(auth);
		return !disposed && owner.generation === generation && owner.epoch === authEpoch
			&& owner.id === options.instanceId() && owner.project === options.projectId()
			&& owner.admin === options.adminMode() && !!state.token
			&& owner.headerProject === (state.projectId ?? undefined) && owner.user === state.userId;
	}
	function path(owner: UsageRequestOwner) {
		return `/api/v1/${owner.admin ? 'admin/' : ''}instances/${encodeURIComponent(owner.id)}/usage-schedule`;
	}
	function refresh() {
		return refreshAttempt(beginExperienceAction('monitoring', 'refresh', 'resource.detail'));
	}
	async function refreshAttempt(parentExperience?: ExperienceContext) {
		if (saving) return;
		controller?.abort();
		generation += 1;
		const owner = snapshot();
		const recoveryDraft = !confirmed && schedule ? { ...draft } : null;
		confirmed = false;
		saved = false;
		error = '';
		if (!owner.id || !owner.project || !owner.token) return;
		controller = new AbortController();
		const experience = parentExperience ?? beginExperienceLoad('monitoring', 'resource.detail');
		loading = true;
		experienceState(experience, 'loading');
		try {
			const result = await api.withExperience(experience).get<UsageScheduleInfo | null>(path(owner), owner.token,
				owner.admin ? owner.headerProject : owner.project, { signal: controller.signal, cache: 'no-store' });
			if (!current(owner)) { experienceDiscarded(experience, disposed ? 'unmounted' : 'stale'); return; }
			if (result && result.instance_id !== owner.id) throw new Error('Schedule identity mismatch');
			schedule = result;
			draft = result ? recoveryDraft ?? scheduleDraft(result) : defaultUsageDraft();
			confirmed = true;
			experienceState(experience, result ? 'ready' : 'empty');
			void experienceApplied(experience, {}, () => current(owner));
		} catch (cause) {
			if (current(owner)) {
				error = cause instanceof ApiError ? cause.message : t('loadFailed');
				experienceState(experience, 'error'); void experienceApplied(experience, {}, () => current(owner));
			} else experienceDiscarded(experience, disposed ? 'unmounted' : 'stale');
		} finally {
			if (current(owner)) loading = false;
		}
	}
	async function save() {
		const owner = snapshot();
		const previous = schedule;
		if (!owner.token || !owner.project || !options.canWrite() || !confirmed || loading || saving
			|| !previous || !['active', 'blocked', 'complete'].includes(previous.state) || usageDraftError(draft, previous.expires_at)) return;
		const payload = { ...usagePayload(draft, previous.expires_at), revision: previous.revision };
		const effectiveExpiry = payload.expires_at ?? previous.expires_at;
		if (['blocked', 'complete'].includes(previous.state) && Date.parse(effectiveExpiry) <= Date.now()) {
			error = t('pastDate');
			return;
		}
		if (['blocked', 'complete'].includes(previous.state) && Date.parse(effectiveExpiry) <= Date.parse(previous.expires_at)) {
			error = t('shorterDate');
			return;
		}
		saving = true;
		const experience = beginExperienceAction('monitoring', 'update', 'resource.detail');
		experienceState(experience, 'loading');
		error = '';
		saved = false;
		controller = new AbortController();
		try {
			const result = await api.withExperience(experience).put<UsageScheduleInfo>(path(owner), payload, owner.token,
				owner.admin ? owner.headerProject : owner.project, { signal: controller.signal, replayOnUnauthorized: false });
			if (!current(owner) || !options.canWrite()) { experienceDiscarded(experience, disposed ? 'unmounted' : 'scope_changed'); return; }
			if (result.instance_id !== owner.id) throw new Error('Schedule identity mismatch');
			schedule = result;
			draft = scheduleDraft(result);
			saved = true;
			experienceState(experience, 'ready');
			void experienceApplied(experience, {}, () => current(owner) && options.canWrite());
			options.onUpdated?.();
		} catch (cause) {
			if (!current(owner)) { experienceDiscarded(experience, disposed ? 'unmounted' : 'stale'); return; }
			// An error may follow a native write. Keep the draft, but require an explicit fresh read before another write.
			confirmed = false;
			error = cause instanceof ApiError ? cause.message : t('saveFailed');
			experienceState(experience, 'error');
			void experienceApplied(experience, {}, () => current(owner));
		} finally {
			if (current(owner)) saving = false;
		}
	}
	$effect(() => {
		void options.instanceId(); void options.projectId(); void options.adminMode(); void options.canWrite(); void authEpoch;
		untrack(() => {
			generation += 1;
			controller?.abort();
			schedule = null; draft = defaultUsageDraft(); loading = false; saving = false; confirmed = false; error = ''; saved = false;
			void refreshAttempt();
		});
	});
	onDestroy(() => { disposed = true; generation += 1; controller?.abort(); unsubscribe(); });
	return {
		get schedule() { return schedule; }, get draft() { return draft; },
		set draft(value: UsageScheduleDraft) { draft = value; saved = false; },
		get loading() { return loading; }, get saving() { return saving; }, get error() { return error; }, get saved() { return saved; },
		get editable() { return confirmed && !loading && !saving && options.canWrite() && !!schedule && ['active', 'blocked', 'complete'].includes(schedule.state); },
		refresh, save,
	};
}
