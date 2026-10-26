export interface Project {
  id: string;
  name: string;
  description?: string;
}

export interface AvailableDomain {
  id: string;
  name: string;
  kind?: 'personal' | 'organization' | 'legacy';
}

export interface CreatedDomain extends AvailableDomain {
  description: string;
  enabled: boolean;
  default_project_id: string;
}

/** Immutable identity namespace and explicit working-domain session context. */
export interface DomainSessionFields {
  domain_id?: string | null;
  domain_name?: string | null;
  identity_domain_id?: string | null;
  identity_domain_name?: string | null;
  available_domains?: AvailableDomain[];
  can_create_domain?: boolean;
  is_domain_manager?: boolean | null;
}

export interface LoginResponse extends DomainSessionFields {
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
  initial_workspace?: { kind: 'personal' | 'remembered'; domain_id: string; project_id: string } | null;
}

/** Verified provider attachment only; a fresh sign-in issues the login session. */
export interface ProviderLinkResponse {
  linked: true;
  domain_id: string;
  domain_name: string;
  provider_id: string;
}

/** Refresh, project rescope and explicit domain-switch response. */
export type SessionTokenResponse = LoginResponse;

export interface AuthMeResponse extends DomainSessionFields {
  user_id: string;
  username: string;
  project_id: string | null;
  project_name: string | null;
  roles?: string[];
  is_system_admin?: boolean;
  can_write?: boolean;
  auth_method?: string;
}

export type DomainLoginProviderKind = 'oidc' | 'github';

export interface DomainLoginProvider {
  id: string;
  name: string;
  kind: DomainLoginProviderKind | string;
}

/** Public provider registration handle; domain_id is origin, not the session's working domain. */
export interface LoginProviderOption extends DomainLoginProvider {
  domain_id: string;
  domain_name: string;
}

/** GET /api/v1/auth/login-options: safe global inventory, without account lookup or provider config. */
export interface LoginOptions {
  providers: LoginProviderOption[];
}

/** GET /api/v1/auth/invitations/{token} */
export interface DomainInvitationInfo {
  domain_id: string;
  domain_name: string;
  email: string;
  account_exists: boolean;
  identity_domain_id?: string;
  identity_domain_name?: string;
  expires_at: string;
  project_name: string | null;
  projects?: { project_id: string; project_name: string; role_ids: string[] }[];
}

/** Invitation/registration acceptance result. */
export interface DomainAccountResult {
  user_id: string;
  domain_id: string;
  domain_name: string;
  identity_domain_id: string;
  identity_domain_name: string;
  personal_project_id: string | null;
  personal_project_name: string | null;
  personal_domain_id: string | null;
  personal_project_deferred?: boolean;
}
