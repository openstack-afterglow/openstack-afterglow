import { t } from '$lib/i18n/ns/drover';
import type { K3sSseProgressMessage } from '$lib/api/k3sSseStream';
import { K3S_CREATE_STEPS, K3S_DELETE_STEPS } from '$lib/components/k3sSteps';
import { beginExperienceAction, experienceApplied, experienceDiscarded, experienceState, recordExperience, type ExperienceContext } from '$lib/utils/experience';

export type K3sProgressMode = 'create' | 'delete';

export function createK3sProgress() {
	let mode = $state<K3sProgressMode>('create');
	let visible = $state(false);
	let step = $state('');
	let pct = $state(0);
	let msg = $state('');
	let error = $state('');
	let createdClusterId = $state<string | null>(null);
	let elapsedSeconds = $state(0);
	let stepTimings = $state<Record<string, number>>({});
	let lastStepSeen = $state('');

	let timerHandle: ReturnType<typeof setInterval> | null = null;
	let timerStart = 0;
	let context: ExperienceContext | undefined;

	function observe(ctx: ExperienceContext | undefined, state: 'loading' | 'ready' | 'error', stage?: number) {
		experienceState(ctx, state, stage);
		// A shared progress controller has no component teardown contract.
		void experienceApplied(ctx, {});
	}

	function startTimer() {
		timerStart = performance.now();
		elapsedSeconds = 0;
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
		get error() { return error; },
		get createdClusterId() { return createdClusterId; },
		get elapsedSeconds() { return elapsedSeconds; },
		get stepTimings() { return stepTimings; },
		get lastStepSeen() { return lastStepSeen; },
		get isTerminal() { return step === 'completed' || step === 'failed'; },

		begin(m: K3sProgressMode, initialMsg = '', ctx?: ExperienceContext) {
			context = ctx ?? beginExperienceAction('k3s', m, 'shared.stream');
			mode = m; visible = true;
			step = ''; pct = 0; msg = initialMsg; error = '';
			createdClusterId = null; elapsedSeconds = 0;
			stepTimings = {}; lastStepSeen = '';
			startTimer();
			experienceState(context, 'loading', 0);
		},

		apply(message: K3sSseProgressMessage, ctx = context) {
			const previousStep = step;
			step = message.step;
			pct = message.progress;
			msg = message.message;
			if (message.elapsed_seconds != null) elapsedSeconds = message.elapsed_seconds;
			if (step !== lastStepSeen) {
				stepTimings = { ...stepTimings, [step]: message.elapsed_seconds ?? elapsedSeconds };
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
		},

		failWith(err: string, ctx = context) {
			step = 'failed'; error = err;
			observe(ctx, 'error');
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
