import { api } from '$lib/api/client';
import type { RecoveryAnalysis, RecoveryRequest, RecoveryResult } from '$lib/types/adminInstance';

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
	execute(serverId: string, request: RecoveryRequest, { token, projectId, signal }: RecoveryScope) {
		return api.post<RecoveryResult>(`${instancePath(serverId)}/recover`, request, token, projectId, {
			signal, replayOnUnauthorized: false, timeoutMs: 120_000,
		});
	},
};
