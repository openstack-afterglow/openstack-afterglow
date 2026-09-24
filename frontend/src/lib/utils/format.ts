/** ISO 날짜 문자열을 짧은 날짜 형식으로 포맷 (예: "2024. 03. 15.") */
export function formatDate(iso: string): string {
	if (!iso) return '-';
	const d = new Date(iso);
	if (isNaN(d.getTime())) return '-';
	return d.toLocaleDateString('ko-KR', { year: 'numeric', month: '2-digit', day: '2-digit' });
}

/** 천단위 쉼표 포맷 */
export function formatNumber(n: number): string {
	return n.toLocaleString();
}

/** GB 단위를 TB/PB로 자동 변환 (1,000 GB → 1 TB) */
export function formatStorage(gb: number): string {
	if (gb >= 1_000_000)
		return `${(gb / 1_000_000).toLocaleString(undefined, { maximumFractionDigits: 1 })} PB`;
	if (gb >= 1_000)
		return `${(gb / 1_000).toLocaleString(undefined, { maximumFractionDigits: 1 })} TB`;
	return `${gb.toLocaleString()} GB`;
}

/** 오브젝트 바이트를 GB/MB/KB 로 포맷 (오브젝트 목록·그리드 공용) */
export function formatObjectSize(bytes: number): string {
	if (bytes >= 1073741824) return formatStorage(Math.round(bytes / 1073741824));
	if (bytes >= 1048576) return `${(bytes / 1048576).toFixed(1)} MB`;
	return `${(bytes / 1024).toFixed(1)} KB`;
}

/** 긴 MIME 타입을 짧은 라벨로 변환 (예: application/vnd.openxmlformats-...presentation → PPTX) */
const MIME_SHORT: Record<string, string> = {
	'application/pdf': 'PDF',
	'application/zip': 'ZIP',
	'application/x-zip-compressed': 'ZIP',
	'application/x-tar': 'TAR',
	'application/x-xz': 'XZ',
	'application/gzip': 'GZ',
	'application/x-bzip2': 'BZ2',
	'application/x-7z-compressed': '7Z',
	'application/x-rar-compressed': 'RAR',
	'application/octet-stream': 'BIN',
	'application/json': 'JSON',
	'application/xml': 'XML',
	'application/javascript': 'JS',
	'application/wasm': 'WASM',
	'application/sql': 'SQL',
	'application/yaml': 'YAML',
	'application/x-yaml': 'YAML',
	'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'DOCX',
	'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'XLSX',
	'application/vnd.openxmlformats-officedocument.presentationml.presentation': 'PPTX',
	'application/msword': 'DOC',
	'application/vnd.ms-excel': 'XLS',
	'application/vnd.ms-powerpoint': 'PPT',
	'application/vnd.oasis.opendocument.text': 'ODT',
	'application/vnd.oasis.opendocument.spreadsheet': 'ODS',
	'application/directory': '폴더',
	'image/png': 'PNG',
	'image/jpeg': 'JPG',
	'image/gif': 'GIF',
	'image/svg+xml': 'SVG',
	'image/webp': 'WEBP',
	'image/x-icon': 'ICO',
	'image/bmp': 'BMP',
	'image/tiff': 'TIFF',
	'video/mp4': 'MP4',
	'video/webm': 'WEBM',
	'video/quicktime': 'MOV',
	'video/x-msvideo': 'AVI',
	'audio/mpeg': 'MP3',
	'audio/wav': 'WAV',
	'audio/ogg': 'OGG',
	'audio/flac': 'FLAC',
	'text/plain': 'TXT',
	'text/html': 'HTML',
	'text/css': 'CSS',
	'text/javascript': 'JS',
	'text/csv': 'CSV',
	'text/markdown': 'MD',
	'text/yaml': 'YAML'
};

/** 바이트를 GB/MB로 포맷 (이미지 크기 표시용) */
export function formatSize(bytes: number | null): string {
	if (!bytes) return '-';
	const gb = bytes / 1024 / 1024 / 1024;
	return gb >= 1 ? `${Math.round(gb * 10) / 10} GB` : `${Math.round(bytes / 1024 / 1024)} MB`;
}

/** ISO 날짜시간 문자열을 "YYYY-MM-DD HH:mm:ss" 형식으로 표시 */
export function formatIsoDateTime(s: string | null): string {
	if (!s) return '-';
	return s.replace('T', ' ').slice(0, 19);
}

/** 이미지 공개 범위에 따른 배지 CSS 클래스 */
export function visibilityBadge(v: string | null): string {
	switch (v) {
		case 'public':    return 'text-green-400 bg-green-900/30';
		case 'shared':    return 'text-blue-400 bg-blue-900/30';
		case 'community': return 'text-cyan-400 bg-cyan-900/30';
		default:          return 'text-gray-400 bg-gray-800';
	}
}

/** 이미지 공개 범위 한글 레이블 */
export function visibilityLabel(v: string | null): string {
	switch (v) {
		case 'public':    return '공개';
		case 'shared':    return '공유';
		case 'community': return '커뮤니티';
		case 'private':   return '비공개';
		default:          return v ?? '-';
	}
}

export function shortContentType(ct: string | null | undefined): string {
	if (!ct) return '-';
	const exact = MIME_SHORT[ct];
	if (exact) return exact;
	// fallback: subtype 의 마지막 마침표 뒤 토큰을 대문자로 (최대 8자)
	const slash = ct.indexOf('/');
	if (slash === -1) return ct.length > 12 ? ct.slice(0, 12) : ct;
	let sub = ct.slice(slash + 1);
	if (sub.startsWith('x-')) sub = sub.slice(2);
	const dot = sub.lastIndexOf('.');
	if (dot !== -1) sub = sub.slice(dot + 1);
	const semi = sub.indexOf(';');
	if (semi !== -1) sub = sub.slice(0, semi).trim();
	return sub.toUpperCase().slice(0, 8) || '-';
}
