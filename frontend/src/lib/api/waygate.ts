import { api } from './client';
import type { ExperienceContext } from '$lib/utils/experience';
import type {
	WaygateServer,
	WaygateServerCreateRequest,
	WaygateServerUpdateRequest,
	WaygateClient,
	WaygateClientCreateResult,
	WaygateClientCreateRequest,
	WaygateClientUpdateRequest,
	WaygateNetworkAttachment,
	WaygateNetworkAttachRequest,
	WaygateNetworkAttachmentUpdateRequest,
	WaygateImportResult,
	WaygateExportResult,
	WaygateServerDiagnostics,
} from '$lib/types/waygate';

const BASE = '/api/v1/waygate/servers';
// Provisioning writes (Trust, VM, ports) take 25-33s; the default 30s client deadline reported success as failure.
const WRITE_OPTIONS = { timeoutMs: 58_000 } as const;

export async function listServers(
	token: string | undefined,
	projectId: string | undefined,
	experience?: ExperienceContext
): Promise<WaygateServer[]> {
	const request = experience ? api.withExperience(experience) : api;
	return request.get<WaygateServer[]>(BASE, token, projectId);
}

export async function createServer(
	body: WaygateServerCreateRequest,
	token: string | undefined,
	projectId: string | undefined
): Promise<WaygateServer> {
	return api.post<WaygateServer>(BASE, body, token, projectId, WRITE_OPTIONS);
}

export async function getServer(
	serverId: string,
	token: string | undefined,
	projectId: string | undefined
): Promise<WaygateServer> {
	return api.get<WaygateServer>(`${BASE}/${serverId}`, token, projectId, { refresh: true });
}

export async function getServerDiagnostics(
	serverId: string,
	token: string | undefined,
	projectId: string | undefined
): Promise<WaygateServerDiagnostics> {
	return api.get<WaygateServerDiagnostics>(`${BASE}/${serverId}/diagnostics`, token, projectId, { refresh: true });
}

/** Gateway VM serial console tail through the existing project-scoped Nova console-log endpoint. */
export async function getGatewayConsoleLog(
	serverVmId: string,
	length: number,
	token: string | undefined,
	projectId: string | undefined
): Promise<string> {
	const data = await api.get<{ output: string | null }>(
		`/api/v1/instances/${encodeURIComponent(serverVmId)}/log?length=${length}`, token, projectId, { refresh: true }
	);
	return data.output ?? '';
}

export async function updateServer(
	serverId: string,
	body: WaygateServerUpdateRequest,
	token: string | undefined,
	projectId: string | undefined
): Promise<WaygateServer> {
	return api.patch<WaygateServer>(`${BASE}/${serverId}`, body, token, projectId, WRITE_OPTIONS);
}

export async function deleteServer(
	serverId: string,
	token: string | undefined,
	projectId: string | undefined
): Promise<void> {
	return api.delete<void>(`${BASE}/${serverId}`, token, projectId, WRITE_OPTIONS);
}

export async function listClients(
	serverId: string,
	token: string | undefined,
	projectId: string | undefined
): Promise<WaygateClient[]> {
	return api.get<WaygateClient[]>(`${BASE}/${serverId}/clients`, token, projectId, { refresh: true });
}

export async function createClient(
	serverId: string,
	body: WaygateClientCreateRequest,
	token: string | undefined,
	projectId: string | undefined
): Promise<WaygateClientCreateResult> {
	return api.post<WaygateClientCreateResult>(`${BASE}/${serverId}/clients`, body, token, projectId);
}

export async function updateClient(
	serverId: string,
	clientId: string,
	body: WaygateClientUpdateRequest,
	token: string | undefined,
	projectId: string | undefined
): Promise<WaygateClient> {
	return api.patch<WaygateClient>(`${BASE}/${serverId}/clients/${clientId}`, body, token, projectId);
}

export async function deleteClient(
	serverId: string,
	clientId: string,
	token: string | undefined,
	projectId: string | undefined
): Promise<void> {
	return api.delete<void>(`${BASE}/${serverId}/clients/${clientId}`, token, projectId);
}

export async function downloadClientConfig(
	serverId: string,
	clientId: string,
	token: string | undefined,
	projectId: string | undefined
): Promise<{ blob: Blob; filename: string }> {
	return api.downloadBlob(`${BASE}/${serverId}/clients/${clientId}/config`, token, projectId);
}

/**
 * 클라이언트 `.conf` 원문을 텍스트로 가져온다 (QR 코드 생성용).
 * 백엔드는 QR 을 생성하지 않고 `.conf` 텍스트만 제공하므로(OpenSpec 결정), QR 은
 * 이 텍스트로 프론트엔드에서 생성한다. downloadClientConfig 와 동일 엔드포인트를 재사용.
 */
export async function getClientConfigText(
	serverId: string,
	clientId: string,
	token: string | undefined,
	projectId: string | undefined
): Promise<string> {
	const { blob } = await downloadClientConfig(serverId, clientId, token, projectId);
	return blob.text();
}

// 네트워크 연결 (Phase 2)
export async function listAttachments(
	serverId: string,
	token: string | undefined,
	projectId: string | undefined
): Promise<WaygateNetworkAttachment[]> {
	return api.get<WaygateNetworkAttachment[]>(`${BASE}/${serverId}/networks`, token, projectId);
}

export async function attachNetwork(
	serverId: string,
	body: WaygateNetworkAttachRequest,
	token: string | undefined,
	projectId: string | undefined
): Promise<WaygateNetworkAttachment> {
	return api.post<WaygateNetworkAttachment>(`${BASE}/${serverId}/networks`, body, token, projectId, WRITE_OPTIONS);
}

/** Replaces one ACTIVE attachment's client routing list; the physical interface is unchanged. */
export async function updateAttachment(
	serverId: string,
	attachmentId: number,
	body: WaygateNetworkAttachmentUpdateRequest,
	token: string | undefined,
	projectId: string | undefined
): Promise<WaygateNetworkAttachment> {
	return api.patch<WaygateNetworkAttachment>(`${BASE}/${serverId}/networks/${attachmentId}`, body, token, projectId);
}

export async function detachNetwork(
	serverId: string,
	attachmentId: number,
	token: string | undefined,
	projectId: string | undefined
): Promise<void> {
	return api.delete<void>(`${BASE}/${serverId}/networks/${attachmentId}`, token, projectId, WRITE_OPTIONS);
}

// 백업 / 마이그레이션 (Phase 3) — export/import 은 패스프레이즈를 담으므로 POST
export async function exportServer(
	serverId: string,
	passphrase: string,
	token: string | undefined,
	projectId: string | undefined
): Promise<WaygateExportResult> {
	return api.post<WaygateExportResult>(`${BASE}/${serverId}/export`, { passphrase }, token, projectId);
}

export async function importServer(
	serverId: string,
	passphrase: string,
	bundle: unknown,
	token: string | undefined,
	projectId: string | undefined
): Promise<WaygateImportResult> {
	return api.post<WaygateImportResult>(
		`${BASE}/${serverId}/import`,
		{ passphrase, bundle },
		token,
		projectId
	);
}
