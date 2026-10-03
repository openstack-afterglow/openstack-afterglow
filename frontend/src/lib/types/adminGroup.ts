export interface Group {
	id: string;
	name: string;
	description: string;
	domain_id: string | null;
	created_at: string | null;
}

export interface GroupMember {
	id: string;
	name: string;
	email: string;
	enabled: boolean;
}

export interface User {
	id: string;
	name: string;
}
