export interface SystemAccountIdentity {
  system_account?: { kind: 'auto_backup' } | null;
}

export interface PagedResponse<T> {
  items: T[];
  next_marker: string | null;
  count: number;
}

export interface TsPoint {
  ts: number;
  [key: string]: number | undefined;
}

export interface SwiftContainer {
  name: string;
  count: number;
  bytes: number;
  project_id?: string;
  project_name?: string;
  is_quarantine?: boolean;
  is_trash?: boolean;
  is_deleted?: boolean;
  deleted_at?: number;
}

export interface User extends SystemAccountIdentity {
  id: string;
  name: string;
  email: string;
  enabled: boolean;
  domain_id: string | null;
  default_project_id: string | null;
  created_at: string | null;
  first_seen?: string | null;
  last_seen?: string | null;
}
