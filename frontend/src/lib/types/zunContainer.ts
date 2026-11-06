export interface ZunContainer {
  uuid: string;
  name: string;
  status: string;
  status_reason: string | null;
  image: string | null;
  command: string | null;
  cpu: number | null;
  memory: string | null;
  created_at: string | null;
}

export interface ContainerListResponse {
  items: ZunContainer[];
  service_available: boolean;
  message: string;
}

/** Validate the native envelope before publishing it to reactive inventory consumers. */
export function parseContainerListResponse(value: unknown): ContainerListResponse {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new TypeError('invalid_container_list_response');
  const response = value as Record<string, unknown>;
  if (!Array.isArray(response.items) || typeof response.service_available !== 'boolean' || typeof response.message !== 'string') {
    throw new TypeError('invalid_container_list_response');
  }
  for (const item of response.items) {
    if (!item || typeof item !== 'object' || Array.isArray(item)) throw new TypeError('invalid_container_list_item');
    const row = item as Record<string, unknown>;
    if (typeof row.uuid !== 'string' || typeof row.name !== 'string' || typeof row.status !== 'string'
      || (row.cpu !== null && (typeof row.cpu !== 'number' || !Number.isFinite(row.cpu)))
      || ['status_reason', 'image', 'command', 'memory', 'created_at'].some(key => row[key] !== null && typeof row[key] !== 'string')) {
      throw new TypeError('invalid_container_list_item');
    }
  }
  return value as ContainerListResponse;
}

export interface EnvVar {
  key: string;
  value: string;
}

export interface PortMapping {
  container_port: number;
  host_port: number;
  protocol: string;
}

export interface ZunContainerDetail {
  uuid: string;
  name: string;
  status: string;
  status_reason: string | null;
  image: string | null;
  command: string | null;
  cpu: number | null;
  memory: string | null;
  created_at: string | null;
  addresses: Record<string, { addr: string }[]> | null;
  host?: string | null;
}

export const containerDetailStatusColor: Record<string, string> = {
  Running:  'text-green-400 bg-green-900/30',
  Stopped:  'text-gray-400 bg-gray-800',
  Created:  'text-blue-400 bg-blue-900/30',
  Error:    'text-red-400 bg-red-900/30',
  Deleting: 'text-orange-400 bg-orange-900/30',
};
