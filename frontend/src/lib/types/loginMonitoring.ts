export type LoginWindow = '24h' | '7d' | '30d';
export type SourceState = 'ready' | 'partial' | 'unknown' | 'unavailable';
export interface MonitoringAuthority { token?: string; userId?: string; projectId?: string; admin: boolean; ready: boolean }
export interface MonitoringUser { id: string; name: string }
export interface LoginBucket { at: string; successes: number; recorded_failures: number }
export interface LoginHour { hour: number; successes: number; recorded_failures: number }
export interface LoginEvent { at: string; project_id: string; resource_type: string; action: string; status: string; auth_method: 'password' | 'federated' | null }
export interface MonitoredSession {
  started_at: string; last_seen: string | null; expires_at: string; refresh_expires_at: string;
  project_id: string | null; device_type: 'desktop' | 'mobile' | 'tablet' | 'unknown' | null;
  os: string | null; auth_method: 'password' | 'federated' | null; observed_recently: boolean;
}
export interface LoginMonitoring {
  user: MonitoringUser; window: LoginWindow; as_of: string; from_at: string; observed_interval_seconds: number;
  history: { state: SourceState; events: LoginEvent[] | null; timeline: LoginBucket[] | null; hour_distribution: LoginHour[] | null;
    login_successes: number | null; recorded_login_failures: number | null; failure_history: 'not_collected'; event_limit?: number; recent_limit?: number };
  sessions: { state: SourceState; items: MonitoredSession[] | null; valid_count: number | null; observed_recent_count: number | null };
}
