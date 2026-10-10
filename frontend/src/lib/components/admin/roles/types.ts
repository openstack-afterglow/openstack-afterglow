export interface ManagedRole {
	id: string;
	name: string;
	description: string;
	domain_id: string | null;
	protected: boolean;
	system_only: boolean;
	implied_role_ids: string[];
	inherited_role_ids: string[];
	parent_role_ids: string[];
}

export interface RoleMetadata {
	name?: string;
	description: string;
	domain_id?: string | null;
}

export type RoleSort = 'name' | 'id' | 'inheritance';
export type SortDirection = 'asc' | 'desc';
