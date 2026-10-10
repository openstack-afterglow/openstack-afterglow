export interface Project {
  id: string;
  name: string;
  description?: string;
}

export interface LoginResponse {
  token: string;
  user_id: string;
  username: string;
  project_id: string;
  project_name: string;
  expires_at: string | null;
  roles?: string[];
  default_project_id?: string;
  is_system_admin?: boolean;
  can_write?: boolean;
  refresh_token?: string;
}
