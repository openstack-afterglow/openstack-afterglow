import { get } from 'svelte/store';
import { api } from '$lib/api/client';
import { siteConfig } from '$lib/config/site';
import { authDisplayContext } from '$lib/stores/authDisplayContext';
import { getMockupRevision } from '$lib/mockup/state';
import type { UsageScheduleInfo } from '$lib/types/instanceUsage';
import { recordExperience, type ExperienceContext } from '$lib/utils/experience';

export interface ScheduleError { instance_id: string; instance_name?: string; message: string }
export interface ScheduleList { schedules: UsageScheduleInfo[]; errors: ScheduleError[] }
interface PendingRead { controller: AbortController; promise: Promise<ScheduleList>; consumers: number }
const pendingReads = new Map<string, PendingRead>();

/** Share only concurrent, read-only inventory reads; never retain results or replay a 401. */
export function loadUsageSchedules(token: string, project: string, signal: AbortSignal, experience?: ExperienceContext): Promise<ScheduleList> {
	signal.throwIfAborted();
	const key = JSON.stringify([get(authDisplayContext).key, token, project,
		get(siteConfig).runtime?.api_base ?? null, getMockupRevision()]);
	let pending = pendingReads.get(key);
	const shared = pending !== undefined;
	if (!pending) {
		const controller = new AbortController();
		pending = {
			controller, consumers: 0,
			promise: api.withExperience(experience).get<ScheduleList>('/api/v1/instances/usage-schedules', token, project,
				{ signal: controller.signal, cache: 'no-store' }),
		};
		pendingReads.set(key, pending);
		const owner = pending;
		const release = () => { if (pendingReads.get(key) === owner) pendingReads.delete(key); };
		void pending.promise.then(release, release);
	}
	const owner = pending;
	owner.consumers += 1;
	const { promise, resolve, reject } = Promise.withResolvers<ScheduleList>();
	let settled = false;
	const finish = (deliver: () => void) => {
		if (settled) return;
		settled = true;
		signal.removeEventListener('abort', abort);
		owner.consumers -= 1;
		if (owner.consumers === 0 && pendingReads.get(key) === owner) {
			pendingReads.delete(key);
			owner.controller.abort();
		}
		deliver();
	};
	const abort = () => finish(() => reject(signal.reason));
	signal.addEventListener('abort', abort, { once: true });
	owner.promise.then(value => finish(() => {
		if (shared) recordExperience(experience, 'result.received', { transport: 'shared', stage: 'response' });
		resolve(value);
	}), error => finish(() => reject(error)));
	return promise;
}
