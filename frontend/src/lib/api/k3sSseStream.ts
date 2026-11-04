import { beginMutationCacheFence, fetchWithAuth } from './client';
import { maybeMockK3sStream } from '$lib/mockup/transport';
import type { ExperienceContext } from '$lib/utils/experience';
import { ApiError } from './errors';

export interface K3sQuotaBudget {
  project_id: string;
  resource: 'security_group' | 'security_group_rule';
  required: number;
  available: number;
  limit: number;
  used: number;
  reserved: number;
}

/** Native quota preflight explicitly proves that no operation was admitted. */
export class K3sAdmissionRefused extends ApiError {
  reason?: string;
  quota?: K3sQuotaBudget;
  constructor(status: number, message: string, detail: { reason?: string; quota?: K3sQuotaBudget }) {
    super(status, message, 'drover_pre_admission_refused');
    this.reason = detail.reason;
    const quota = detail.quota;
    if (quota && typeof quota.project_id === 'string' && ['security_group', 'security_group_rule'].includes(quota.resource)
      && [quota.required, quota.available, quota.limit, quota.used, quota.reserved].every(value => Number.isInteger(value) && value >= 0)) this.quota = quota;
  }
}


export interface K3sSseProgressMessage {
  step: string;
  progress: number;
  message: string;
  cluster_id?: string;
  error?: string;
  elapsed_seconds?: number;
  operation_id?: string;
  sequence?: number;
}

export async function* streamK3sProgress(
  path: string,
  init: { method: 'POST'; body?: unknown; token?: string; projectId?: string; experience?: ExperienceContext },
): AsyncGenerator<K3sSseProgressMessage> {
  const fence = beginMutationCacheFence(init.token, init.projectId);
  try {
    const mockStream = maybeMockK3sStream(path, init.body, init.token, init.projectId);
    if (mockStream) {
      yield* mockStream;
      return;
    }
    const res = await fetchWithAuth(path, {
      method: init.method,
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
      },
      body: init.body != null ? JSON.stringify(init.body) : undefined,
    }, init.token, init.projectId, { baseUrl: fence.baseUrl, experience: init.experience });

    if (!res.ok || !res.body) {
      const text = await res.text().catch(() => '');
      let refusal: K3sAdmissionRefused | undefined;
      try {
        const body = JSON.parse(text);
        if (body?.detail?.code === 'drover_pre_admission_refused' && typeof body.detail.message === 'string' && body.detail.message.trim()) {
          refusal = new K3sAdmissionRefused(res.status, body.detail.message, body.detail);
        }
      } catch { /* Untyped proxy/provider errors do not prove whether dispatch occurred. */ }
      throw refusal ?? new ApiError(res.status, `HTTP ${res.status}: ${text}`);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const lines = buf.split('\n');
      buf = lines.pop() ?? '';
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        try {
          yield JSON.parse(line.slice(6)) as K3sSseProgressMessage;
        } catch {
          // 파싱 실패한 라인은 무시
        }
      }
    }
  } finally {
    fence.finish();
  }
}
