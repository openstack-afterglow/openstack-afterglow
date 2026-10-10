import { api } from './client';
import type {
	K3sClusterAuthorization,
	K3sClusterReauthorization,
	K3sCredentialRetirement,
	K3sInterfaceInfo,
} from '$lib/types/k3s';

export async function listNodeInterfaces(
	clusterId: string,
	vmId: string,
	token: string | undefined,
	projectId: string | undefined
): Promise<K3sInterfaceInfo[]> {
	return api.get<K3sInterfaceInfo[]>(
		`/api/v1/k3s/clusters/${clusterId}/nodes/${vmId}/interfaces`,
		token,
		projectId
	);
}

export async function attachNodeInterface(
	clusterId: string,
	vmId: string,
	netId: string,
	token: string | undefined,
	projectId: string | undefined
): Promise<K3sInterfaceInfo> {
	return api.post<K3sInterfaceInfo>(
		`/api/v1/k3s/clusters/${clusterId}/nodes/${vmId}/interfaces`,
		{ net_id: netId },
		token,
		projectId
	);
}

export async function detachNodeInterface(
	clusterId: string,
	vmId: string,
	portId: string,
	token: string | undefined,
	projectId: string | undefined
): Promise<void> {
	return api.delete<void>(
		`/api/v1/k3s/clusters/${clusterId}/nodes/${vmId}/interfaces/${portId}`,
		token,
		projectId
	);
}

export async function getClusterAuthorization(
	clusterId: string,
	token: string | undefined,
	projectId: string | undefined,
	signal?: AbortSignal
): Promise<K3sClusterAuthorization> {
	return api.get<K3sClusterAuthorization>(
		`/api/v1/k3s/clusters/${clusterId}/authorization`,
		token,
		projectId,
		{ refresh: true, signal }
	);
}

/** Stage the caller's own restricted credentials; Drover rolls them into the guest before activation. */
export async function reauthorizeCluster(
	clusterId: string,
	token: string | undefined,
	projectId: string | undefined
): Promise<K3sClusterReauthorization> {
	return api.post<K3sClusterReauthorization>(
		`/api/v1/k3s/clusters/${clusterId}/authorization`,
		{},
		token,
		projectId
	);
}

/** Delete only the caller's own superseded credentials with the caller's token. */
export async function retireClusterCredentials(
	clusterId: string,
	token: string | undefined,
	projectId: string | undefined
): Promise<K3sCredentialRetirement> {
	return api.post<K3sCredentialRetirement>(
		`/api/v1/k3s/clusters/${clusterId}/authorization/retire`,
		{},
		token,
		projectId
	);
}
