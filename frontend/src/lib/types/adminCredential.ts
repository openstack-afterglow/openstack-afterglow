export interface CredentialRole { id: string; name: string }
export interface ApplicationCredential {
  id: string; domain_id: string; user_id: string; name: string; description: string;
  project_id: string | null; expires_at: string | null; unrestricted: boolean;
  roles: CredentialRole[];
}
export interface ApplicationCredentialIssued extends ApplicationCredential { secret: string }
export interface UserCredential { id: string; domain_id: string; user_id: string; project_id: string | null; type: string }
export interface UserCredentialDetail extends UserCredential { blob?: string }
export interface CredentialCreationContext { domain_id: string; user_id: string; project_id: string; roles: CredentialRole[] }
export interface CredentialUser { id: string; domain_id: string; name: string }
export interface CredentialAuthority { token?: string; userId?: string; projectId?: string; admin: boolean; ready: boolean }
export interface ApplicationCredentialInput { name: string; description: string; role_ids: string[]; expires_at?: string }
export interface UserCredentialInput { user_id: string; project_id: string | null; type: string; blob: string }
