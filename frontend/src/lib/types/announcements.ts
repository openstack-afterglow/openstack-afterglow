import type { MailOperation } from '$lib/api/email';

export type AnnouncementSeverity = 'info' | 'warning' | 'danger';
export type AnnouncementTargetType = 'all' | 'project' | 'user';

/** 사용자 수신 뷰 — 서버가 token_info 기준으로 이미 타겟팅을 판별해 반환한다. */
export interface AnnouncementUser {
	id: number;
	created_at: string;
	created_by_username: string;
	title: string;
	body: string;
	severity: AnnouncementSeverity;
	starts_at: string | null;
	ends_at: string | null;
	is_read: boolean;
}

/** 관리자 CRUD 뷰 — 발송 이력·타겟·활성 상태 포함. */
export interface AnnouncementAdmin {
	id: number;
	created_at: string;
	updated_at: string;
	created_by_user_id: string;
	created_by_username: string;
	title: string;
	body: string;
	severity: AnnouncementSeverity;
	target_type: AnnouncementTargetType;
	target_id: string | null;
	starts_at: string | null;
	ends_at: string | null;
	is_active: boolean;
	email_operation?: MailOperation | null;
}

export interface AnnouncementCreatePayload {
	title: string;
	body: string;
	severity: AnnouncementSeverity;
	target_type: AnnouncementTargetType;
	target_id?: string | null;
	starts_at?: string | null;
	ends_at?: string | null;
	send_email?: boolean;
	email_operation_id?: string;
}

export interface AnnouncementUpdatePayload {
	title?: string;
	body?: string;
	severity?: AnnouncementSeverity;
	target_type?: AnnouncementTargetType;
	target_id?: string | null;
	starts_at?: string | null;
	ends_at?: string | null;
	is_active?: boolean;
}

export interface AnnouncementOptions {
	severities: AnnouncementSeverity[];
	target_types: AnnouncementTargetType[];
}

export interface UnreadCountResponse {
	unread_count: number;
}
