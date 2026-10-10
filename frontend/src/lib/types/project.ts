export interface Project {
	id: string;
	name: string;
	description: string;
	enabled: boolean;
	domain_id: string | null;
	created_at: string | null;
}

export interface ProjectMember {
	user_id: string;
	user_name: string;
	role_id: string;
	role_name: string;
	type?: 'user' | 'group';
	group_id?: string;
}

export interface ProjectAccessMember {
	user_id: string;
	username: string;
	email: string;
	is_owner: boolean;
	is_manager: boolean;
	roles: string[];
	direct_role_ids: string[];
	effective_role_ids: string[];
	source?: 'direct' | 'group' | 'mixed' | 'inherited';
	group_name?: string;
}

export interface AssignableProjectRole {
	id: string;
	name: string;
	description?: string;
	area: string | null;
	grade: string | null;
}

export interface AssignableProjectRoles {
	roles: AssignableProjectRole[];
	is_owner: boolean;
}

export interface ProjectInvitation {
	id: number;
	project_id: string;
	invited_email: string;
	invited_by_name: string;
	status: string;
	keystone_role: string;
	expires_at: string;
	accepted_at: string | null;
	created_at: string;
}

export interface InvitationInfo {
	project_id: string;
	project_name: string;
	inviter_name: string;
	invited_email: string;
	status: string;
	expires_at: string;
}
