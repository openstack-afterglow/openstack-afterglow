import { fetchWithAuth, getBaseUrl } from '$lib/api/client';

export function downloadBlobAs(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function firstPartyApiPath(url: string): string | null {
	const base = new URL(getBaseUrl());
	const request = new URL(url, base);
	if (request.origin !== base.origin || !request.pathname.startsWith('/api/v1/')) return null;
	return `${request.pathname}${request.search}`;
}

export async function downloadAuthenticated(
  url: string,
  filename: string,
  token: string | undefined,
  projectId: string | undefined,
): Promise<void> {
  const path = firstPartyApiPath(url);
  const res = path
    ? await fetchWithAuth(path, {}, token, projectId)
    : await fetch(url);
  if (!res.ok) throw new Error(`다운로드 실패 (${res.status})`);
  downloadBlobAs(await res.blob(), filename);
}
