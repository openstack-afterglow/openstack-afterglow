import { api } from '$lib/api/client';
import type { RecoveryAnalysis, RecoveryObservation, RecoveryRequest, RecoveryResult, UnconfirmedRecoveryAction } from '$lib/types/adminInstance';

interface RecoveryScope {
	token: string;
	projectId?: string;
	signal: AbortSignal;
}

function instancePath(serverId: string) {
	return `/api/v1/admin/instances/${encodeURIComponent(serverId)}`;
}

export const instanceRecoveryApi = {
	analyze(serverId: string, { token, projectId, signal }: RecoveryScope) {
		return api.get<RecoveryAnalysis>(`${instancePath(serverId)}/recovery-analysis`, token, projectId, {
			signal, cache: 'no-store', replayOnUnauthorized: true,
		});
	},
	status(serverId: string, requestedAt: string, { token, projectId, signal }: RecoveryScope, {
		unconfirmedAction, mayRecover,
	}: { unconfirmedAction: UnconfirmedRecoveryAction | null; mayRecover: boolean }) {
		const query = new URLSearchParams({ requested_at: requestedAt });
		if (unconfirmedAction) query.set('unconfirmed_action', unconfirmedAction);
		if (unconfirmedAction || !mayRecover) query.set('observation_may_recover', String(mayRecover));
		return api.get<RecoveryObservation>(`${instancePath(serverId)}/recovery-status?${query}`, token, projectId, {
			signal, cache: 'no-store', suppressAuthRedirect: true, timeoutMs: 10_000,
		});
	},
	execute(serverId: string, request: RecoveryRequest, { token, projectId, signal }: RecoveryScope) {
		return api.post<RecoveryResult>(`${instancePath(serverId)}/recover`, request, token, projectId, {
			signal, replayOnUnauthorized: false, timeoutMs: 120_000,
		});
	},
};
