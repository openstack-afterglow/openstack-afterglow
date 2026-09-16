import { api, fetchWithAuth } from './client';

export interface SecretInfo {
	id: string;
	name: string | null;
	secret_type: string;
	status: string | null;
	algorithm: string | null;
	bit_length: number | null;
	mode: string | null;
	created: string | null;
	expires: string | null;
	content_types: Record<string, string> | null;
	system_managed: boolean;
}

export interface ContainerInfo {
	id: string;
	name: string | null;
	type: string;
	status: string | null;
	created: string | null;
	secret_refs: { name: string; secret_ref: string }[];
}

export interface OrderInfo {
	id: string;
	type: string;
	status: string | null;
	created: string | null;
	secret_ref: string | null;
	container_ref: string | null;
	meta: Record<string, unknown>;
	error_reason: string | null;
}

export interface QuotaInfo {
	secrets: number;
	orders: number;
	containers: number;
	consumers: number;
	cas: number;
}

export const secretsApi = {
	listSecrets: (token?: string, projectId?: string) =>
		api.get<SecretInfo[]>('/api/v1/secrets', token, projectId),

	createSecret: (body: object, token?: string, projectId?: string) =>
		api.post<SecretInfo>('/api/v1/secrets', body, token, projectId),

	deleteSecret: (id: string, token?: string, projectId?: string) =>
		api.delete<void>(`/api/v1/secrets/${id}`, token, projectId),

	getPayload: async (id: string, token?: string, projectId?: string): Promise<string> => {
		const res = await fetchWithAuth(`/api/v1/secrets/${id}/payload`, {}, token, projectId);
		if (!res.ok) throw new Error('payload 조회 실패');
		const buf = await res.arrayBuffer();
		return new TextDecoder().decode(buf);
	},

	getAcl: (id: string, token?: string, projectId?: string) =>
		api.get<object>(`/api/v1/secrets/${id}/acl`, token, projectId),

	setAcl: (id: string, body: object, token?: string, projectId?: string) =>
		api.put<object>(`/api/v1/secrets/${id}/acl`, body, token, projectId),

	listConsumers: (id: string, token?: string, projectId?: string) =>
		api.get<object[]>(`/api/v1/secrets/${id}/consumers`, token, projectId),

	getEffectiveQuota: (token?: string, projectId?: string) =>
		api.get<QuotaInfo>('/api/v1/secrets/quota/effective', token, projectId),

	listContainers: (token?: string, projectId?: string) =>
		api.get<ContainerInfo[]>('/api/v1/secret-containers', token, projectId),

	createContainer: (body: object, token?: string, projectId?: string) =>
		api.post<ContainerInfo>('/api/v1/secret-containers', body, token, projectId),

	deleteContainer: (id: string, token?: string, projectId?: string) =>
		api.delete<void>(`/api/v1/secret-containers/${id}`, token, projectId),

	listOrders: (token?: string, projectId?: string) =>
		api.get<OrderInfo[]>('/api/v1/secret-orders', token, projectId),

	createOrder: (body: object, token?: string, projectId?: string) =>
		api.post<OrderInfo>('/api/v1/secret-orders', body, token, projectId),

	getOrder: (id: string, token?: string, projectId?: string) =>
		api.get<OrderInfo>(`/api/v1/secret-orders/${id}`, token, projectId),

	// Admin
	listProjectQuotas: (token?: string, projectId?: string) =>
		api.get<object[]>('/api/v1/admin/key-manager/project-quotas', token, projectId),

	setProjectQuota: (pid: string, body: object, token?: string, projectId?: string) =>
		api.put<object>(`/api/v1/admin/key-manager/project-quotas/${pid}`, body, token, projectId),

	deleteProjectQuota: (pid: string, token?: string, projectId?: string) =>
		api.delete<void>(`/api/v1/admin/key-manager/project-quotas/${pid}`, token, projectId),
};
