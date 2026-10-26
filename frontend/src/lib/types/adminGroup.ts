export interface Group {
	id: string;
	name: string;
	description: string;
	domain_id: string | null;
	created_at: string | null;
}

export interface User {
	id: string;
	name: string;
	email: string;
	enabled: boolean;
	domain_id: string;
}

export interface GroupCandidates {
	domain_id: string;
	user_domain_id: string;
	items: User[];
}

export interface GroupMember extends Omit<User, 'domain_id'> {
	domain_id: string | null;
	identity_read_only: boolean;
}
