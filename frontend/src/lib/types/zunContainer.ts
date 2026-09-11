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
