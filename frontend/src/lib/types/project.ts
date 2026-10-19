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
	external_role_ids: string[];
	source?: 'direct' | 'group' | 'mixed' | 'inherited';
	group_name?: string;
}

export interface AssignableProjectRole {
	id: string;
	name: string;
	description?: string;
	area: string | null;
	grade: string | null;
	implied_role_ids: string[];
	inherited_role_ids: string[];
}

export interface AssignableProjectRoles {
	roles: AssignableProjectRole[];
	is_owner: boolean;
	can_manage_owners: boolean;
}

export interface EligibleProjectUser {
	id: string;
	name: string;
	email: string;
	domain_id: string;
	enabled: boolean;
}

export interface ProjectOwnershipTransfer {
	id: string;
	project_id: string;
	domain_id: string;
	from_user_id: string;
	to_user_id: string;
	status: 'applying' | 'unknown' | 'settled' | 'completed';
	stage: string;
}

export interface ProjectOwnership {
	project_id: string;
	owner_user_id: string | null;
	status: 'unique' | 'missing' | 'conflict';
	owners: Array<{ user_id: string; name: string; source: 'direct' | 'group_or_inherited' }>;
	can_transfer: boolean;
	can_delete: boolean;
	transfer_operation: ProjectOwnershipTransfer | null;
}

export interface ProjectCreators {
	domain_id: string;
	role: { id: string; name: string } | null;
	users: Array<EligibleProjectUser & { source: 'direct' | 'inherited'; direct: boolean }>;
}


