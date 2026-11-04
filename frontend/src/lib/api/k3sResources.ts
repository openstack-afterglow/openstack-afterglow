import { api } from './client';
import type { ExperienceContext } from '$lib/utils/experience';
import type { ConfigMapInfo, SecretInfo, CloudShellTicket } from '$lib/types/k3s';

export async function listNamespaces(
	clusterId: string,
	token: string | undefined,
	projectId: string | undefined,
	experience?: ExperienceContext
): Promise<string[]> {
	return api.withExperience(experience).get<string[]>(`/api/v1/k3s/clusters/${clusterId}/namespaces`, token, projectId);
}

export async function listConfigMaps(
	clusterId: string,
	namespace: string,
	token: string | undefined,
	projectId: string | undefined,
	experience?: ExperienceContext
): Promise<ConfigMapInfo[]> {
	return api.withExperience(experience).get<ConfigMapInfo[]>(
		`/api/v1/k3s/clusters/${clusterId}/configmaps?namespace=${encodeURIComponent(namespace)}`,
		token,
		projectId
	);
}

export async function getConfigMap(
	clusterId: string,
	namespace: string,
	name: string,
	token: string | undefined,
	projectId: string | undefined
): Promise<ConfigMapInfo> {
	return api.get<ConfigMapInfo>(
		`/api/v1/k3s/clusters/${clusterId}/namespaces/${namespace}/configmaps/${name}`,
		token,
		projectId
	);
}

export async function createConfigMap(
	clusterId: string,
	namespace: string,
	payload: { name: string; data: Record<string, string> },
	token: string | undefined,
	projectId: string | undefined,
	experience?: ExperienceContext
): Promise<ConfigMapInfo> {
	return api.withExperience(experience).post<ConfigMapInfo>(
		`/api/v1/k3s/clusters/${clusterId}/namespaces/${namespace}/configmaps`,
		payload,
		token,
		projectId
	);
}

export async function updateConfigMap(
	clusterId: string,
	namespace: string,
	name: string,
	payload: { data: Record<string, string> },
	token: string | undefined,
	projectId: string | undefined,
	experience?: ExperienceContext
): Promise<ConfigMapInfo> {
	return api.withExperience(experience).put<ConfigMapInfo>(
		`/api/v1/k3s/clusters/${clusterId}/namespaces/${namespace}/configmaps/${name}`,
		payload,
		token,
		projectId
	);
}

export async function deleteConfigMap(
	clusterId: string,
	namespace: string,
	name: string,
	token: string | undefined,
	projectId: string | undefined,
	experience?: ExperienceContext
): Promise<void> {
	return api.withExperience(experience).delete<void>(
		`/api/v1/k3s/clusters/${clusterId}/namespaces/${namespace}/configmaps/${name}`,
		token,
		projectId
	);
}

export async function listSecrets(
	clusterId: string,
	namespace: string,
	token: string | undefined,
	projectId: string | undefined,
	experience?: ExperienceContext
): Promise<SecretInfo[]> {
	return api.withExperience(experience).get<SecretInfo[]>(
		`/api/v1/k3s/clusters/${clusterId}/secrets?namespace=${encodeURIComponent(namespace)}`,
		token,
		projectId
	);
}

export async function getSecret(
	clusterId: string,
	namespace: string,
	name: string,
	token: string | undefined,
	projectId: string | undefined
): Promise<SecretInfo> {
	return api.get<SecretInfo>(
		`/api/v1/k3s/clusters/${clusterId}/namespaces/${namespace}/secrets/${name}`,
		token,
		projectId
	);
}

export async function createSecret(
	clusterId: string,
	namespace: string,
	payload: { name: string; type: string; data: Record<string, string> },
	token: string | undefined,
	projectId: string | undefined,
	experience?: ExperienceContext
): Promise<SecretInfo> {
	return api.withExperience(experience).post<SecretInfo>(
		`/api/v1/k3s/clusters/${clusterId}/namespaces/${namespace}/secrets`,
		payload,
		token,
		projectId
	);
}

export async function updateSecret(
	clusterId: string,
	namespace: string,
	name: string,
	payload: { type: string; data: Record<string, string> },
	token: string | undefined,
	projectId: string | undefined,
	experience?: ExperienceContext
): Promise<SecretInfo> {
	return api.withExperience(experience).put<SecretInfo>(
		`/api/v1/k3s/clusters/${clusterId}/namespaces/${namespace}/secrets/${name}`,
		payload,
		token,
		projectId
	);
}

export async function deleteSecret(
	clusterId: string,
	namespace: string,
	name: string,
	token: string | undefined,
	projectId: string | undefined,
	experience?: ExperienceContext
): Promise<void> {
	return api.withExperience(experience).delete<void>(
		`/api/v1/k3s/clusters/${clusterId}/namespaces/${namespace}/secrets/${name}`,
		token,
		projectId
	);
}

export async function createShellTicket(
	clusterId: string,
	token: string | undefined,
	projectId: string | undefined,
	experience?: ExperienceContext
): Promise<CloudShellTicket> {
	return api.withExperience(experience).post<CloudShellTicket>(
		`/api/v1/k3s/clusters/${clusterId}/shell-ticket`,
		{},
		token,
		projectId
	);
}
