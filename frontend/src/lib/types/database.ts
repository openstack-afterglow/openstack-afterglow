export interface DbFlavor {
  id: string | number;
  name: string;
  vcpus: number;
  ram: number;
}

export interface DbInstance {
  id: string;
  name: string;
  status: string;
  datastore: { type?: string; version?: string };
  flavor_id: string;
  flavor_ram?: number;
  flavor_vcpus?: number;
  size: number;
  created_at: string;
  hostname?: string;
  ip?: string;
  ips?: string[];
  address_map?: Record<string, string[]>;
  volume_used?: number;
  project_id?: string;
}

export interface DbDatabase {
  name: string;
  character_set: string;
  collate: string;
}

export interface DbUser {
  name: string;
  host?: string;
  databases: { name: string }[];
}

export interface DbBackup {
  id: string;
  name: string;
  status: string;
  size: number;
  created_at: string;
  instance_id?: string;
  datastore?: { type?: string; version?: string };
  description?: string;
}
