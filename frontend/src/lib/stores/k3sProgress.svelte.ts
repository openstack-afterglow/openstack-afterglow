import { t } from '$lib/i18n/ns/drover';
import { t as tp } from '$lib/i18n/ns/drover-pages';
import type { K3sSseProgressMessage } from '$lib/api/k3sSseStream';
import { K3S_CREATE_STEPS, K3S_DELETE_STEPS } from '$lib/components/k3sSteps';
import { beginExperienceAction, experienceApplied, experienceDiscarded, experienceState, recordExperience, type ExperienceContext } from '$lib/utils/experience';

export type K3sProgressMode = 'create' | 'delete';

/** Only allowlisted, nonsecret native refusal facts survive a tab reload. */
export interface K3sRefusalSummary {
	reason: 'security_group_quota_exceeded' | 'security_group_quota_unavailable';
	quota?: { resource: 'security_group' | 'security_group_rule'; required: number; available: number };
}

export function createK3sProgress() {
	let mode = $state<K3sProgressMode>('create');
	let visible = $state(false);
	let step = $state('');
	let pct = $state(NaN);
	let msg = $state('');
	let error = $state('');
	let createdClusterId = $state<string | null>(null);
	let elapsedSeconds = $state(0);
	let stepTimings = $state<Record<string, number>>({});
	let lastStepSeen = $state('');
	let operationId = $state<string | null>(null);
	let sequence = 0;
	let uncertain = $state(false);
	let refusalSummary = $state<K3sRefusalSummary | null>(null);
	let observer: (() => void) | undefined;

	let timerHandle: ReturnType<typeof setInterval> | null = null;
	let timerStart = 0;
	let context: ExperienceContext | undefined;

	function observe(ctx: ExperienceContext | undefined, state: 'loading' | 'ready' | 'error', stage?: number) {
		experienceState(ctx, state, stage);
		// A shared progress controller has no component teardown contract.
		void experienceApplied(ctx, {});
	}

	function startTimer() {
		stopTimer();
		timerStart = performance.now() - elapsedSeconds * 1000;
		timerHandle = setInterval(() => {
			elapsedSeconds = Math.round((performance.now() - timerStart) / 100) / 10;
		}, 500);
	}

	function stopTimer() {
		if (timerHandle) { clearInterval(timerHandle); timerHandle = null; }
	}

	return {
		get mode() { return mode; },
		get visible() { return visible; },
		set visible(v: boolean) { visible = v; },
		get step() { return step; },
		get pct() { return pct; },
		get msg() { return msg; },
		get error() {
			const quota = refusalSummary?.quota;
			const summary = refusalSummary?.reason === 'security_group_quota_exceeded' && quota
				? tp('progress.quotaExceeded', { resource: tp(quota.resource === 'security_group' ? 'progress.quotaGroups' : 'progress.quotaRules'), required: quota.required, available: quota.available })
				: refusalSummary?.reason === 'security_group_quota_unavailable' ? tp('progress.quotaUnavailable') : '';
			return summary ? `${summary}${error ? ` ${error}` : ''}` : error || (step === 'failed' ? t('progress.unknownError') : '');
		},
		get refusalSummary() { return refusalSummary; },
		get createdClusterId() { return createdClusterId; },
		get elapsedSeconds() { return elapsedSeconds; },
		get stepTimings() { return stepTimings; },
		get lastStepSeen() { return lastStepSeen; },
		get operationId() { return operationId; },
		get sequence() { return sequence; },
		get uncertain() { return uncertain; },
		setObserver(fn: () => void) { observer = fn; },
		get isTerminal() { return step === 'completed' || step === 'failed'; },

		begin(m: K3sProgressMode, initialMsg = '', ctx?: ExperienceContext) {
			context = ctx ?? beginExperienceAction('k3s', m, 'shared.stream');
			mode = m; visible = true;
			step = ''; pct = NaN; msg = initialMsg; error = '';
			createdClusterId = null; elapsedSeconds = 0;
			stepTimings = {}; lastStepSeen = '';
			operationId = null; sequence = 0; uncertain = false;
			refusalSummary = null;
			startTimer();
			observer?.();
			experienceState(context, 'loading', 0);
		},

		apply(message: K3sSseProgressMessage, ctx = context) {
			if (step === 'completed' || step === 'failed') return;
			if (message.sequence != null && message.sequence <= sequence) return;
			if (message.sequence != null) sequence = message.sequence;
			if (message.operation_id) operationId = message.operation_id;
			const previousStep = step;
			step = message.step;
			// Native event percentages are independent of the number of displayed stages.
			pct = Number.isFinite(message.progress) ? message.progress : NaN;
			msg = message.message;
			error = '';
			refusalSummary = null;
			uncertain = false;
			if (message.elapsed_seconds != null) elapsedSeconds = Math.max(elapsedSeconds, message.elapsed_seconds);
			if (step !== lastStepSeen && stepTimings[step] == null) {
				stepTimings = { ...stepTimings, [step]: elapsedSeconds };
				lastStepSeen = step;
			}
			if (message.cluster_id) createdClusterId = message.cluster_id;
			if (step === 'failed') error = message.error || t('progress.unknownError');
			const stages = mode === 'create' ? K3S_CREATE_STEPS : K3S_DELETE_STEPS;
			const index = stages.findIndex(stage => stage.id === step);
			if (step !== previousStep) {
				if (step === 'failed') observe(ctx, 'error');
				else if (index >= 0) observe(ctx, step === 'completed' ? 'ready' : 'loading', index + 1);
			}
			if (step === 'completed' || step === 'failed') stopTimer();
			observer?.();
		},

		failWith(err: string, ctx = context, summary?: K3sRefusalSummary) {
			step = 'failed'; error = err; refusalSummary = summary ?? null; uncertain = false;
			observe(ctx, 'error');
			stopTimer();
			observer?.();
		},

		disconnect(reason = '') {
			if (step === 'completed' || step === 'failed') return;
			uncertain = true;
			if (reason) error = reason;
			stopTimer();
			observer?.();
		},

		confirmRunning() {
			if (step === 'completed' || step === 'failed') return;
			uncertain = false;
			error = '';
			if (!timerHandle) startTimer();
			observer?.();
		},

		restore(snapshot: { mode: K3sProgressMode; step: string; pct: number | null; clusterId: string | null; operationId: string | null; sequence: number; elapsed: number; timings: Record<string, number>; refusalSummary?: K3sRefusalSummary }) {
			stopTimer();
			mode = snapshot.mode; step = snapshot.step; pct = snapshot.pct ?? NaN;
			createdClusterId = snapshot.clusterId; operationId = snapshot.operationId; sequence = snapshot.sequence;
			elapsedSeconds = snapshot.elapsed; stepTimings = snapshot.timings;
			visible = false; uncertain = step !== 'completed' && step !== 'failed'; error = ''; refusalSummary = null;
			const saved = snapshot.refusalSummary;
			if (step === 'failed' && saved && ['security_group_quota_exceeded', 'security_group_quota_unavailable'].includes(saved.reason)) {
				refusalSummary = { reason: saved.reason };
				const quota = saved.quota;
				if (quota && ['security_group', 'security_group_rule'].includes(quota.resource)
					&& Number.isInteger(quota.required) && quota.required >= 0 && Number.isInteger(quota.available) && quota.available >= 0) {
					refusalSummary.quota = { resource: quota.resource, required: quota.required, available: quota.available };
				}
			}
		},

		end(ctx = context, isCurrent: () => boolean = () => true) {
			stopTimer();
			if (ctx !== context || !isCurrent()) experienceDiscarded(ctx, 'stale');
			// A clean create EOF may intentionally hand off at waiting_callback.
			else if (mode === 'delete' && step !== 'completed' && step !== 'failed') recordExperience(ctx, 'telemetry.gap', { reason: 'transport_failed' });
		},
	};
}

export type K3sProgressController = ReturnType<typeof createK3sProgress>;
