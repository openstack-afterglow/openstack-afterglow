export interface AudioTranscriptSegment {
	start: number;
	end: number;
	text: string;
}

export interface AudioTranscript {
	text: string;
	segments: AudioTranscriptSegment[];
}

const MAX_TRANSCRIPT_LENGTH = 65_536;
const MAX_SEGMENTS = 4_096;
const MAX_SECONDS = 30 * 60;

/** Keep only provider time ranges; never estimate alignment from the transcript. */
export function parseAudioTranscript(value: unknown, requireTimestamps = false): AudioTranscript {
	if (!value || typeof value !== 'object' || Array.isArray(value) || !('text' in value) || typeof value.text !== 'string' || value.text.length > MAX_TRANSCRIPT_LENGTH) {
		throw new Error('음성 인식 결과가 유효하지 않습니다.');
	}
	const raw = 'segments' in value ? value.segments : undefined;
	if (raw !== undefined && (!Array.isArray(raw) || raw.length > MAX_SEGMENTS)) {
		throw new Error('음성 인식 타임스탬프가 유효하지 않습니다.');
	}
	const segments: AudioTranscriptSegment[] = [];
	let previousEnd = 0;
	let textLength = 0;
	for (const item of raw ?? []) {
		if (!item || typeof item !== 'object' || Array.isArray(item) ||
			typeof item.start !== 'number' || !Number.isFinite(item.start) || item.start < previousEnd ||
			typeof item.end !== 'number' || !Number.isFinite(item.end) || item.end < item.start || item.end > MAX_SECONDS ||
			typeof item.text !== 'string') {
			throw new Error('음성 인식 타임스탬프가 유효하지 않습니다.');
		}
		textLength += item.text.length;
		if (textLength > MAX_TRANSCRIPT_LENGTH) throw new Error('음성 인식 결과가 너무 깁니다.');
		segments.push({ start: item.start, end: item.end, text: item.text });
		previousEnd = item.end;
	}
	if (requireTimestamps && value.text.trim() && !segments.length) {
		throw new Error('음성 인식 응답에 요청한 타임스탬프가 없습니다.');
	}
	return { text: value.text, segments };
}

export function formatTranscriptTime(seconds: number): string {
	if (!Number.isFinite(seconds) || seconds < 0 || seconds > MAX_SECONDS) throw new Error('유효하지 않은 전사 시각입니다.');
	const total = Math.round(seconds * 1000);
	const hours = Math.floor(total / 3_600_000);
	const minutes = Math.floor(total / 60_000) % 60;
	const wholeSeconds = Math.floor(total / 1000) % 60;
	return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(wholeSeconds).padStart(2, '0')}.${String(total % 1000).padStart(3, '0')}`;
}

export function transcriptText(result: AudioTranscript): string {
	if (!result.segments.length) return result.text;
	return result.segments.map((segment) => `[${formatTranscriptTime(segment.start)} → ${formatTranscriptTime(segment.end)}]\n${segment.text.trim()}`).join('\n\n') + '\n';
}

export function transcriptSrt(result: AudioTranscript): string {
	if (!result.segments.length) throw new Error('이 전사 결과에는 자막 시각이 없습니다.');
	return result.segments.map((segment, index) => `${index + 1}\n${formatTranscriptTime(segment.start).replace('.', ',')} --> ${formatTranscriptTime(segment.end).replace('.', ',')}\n${segment.text.trim().replace(/\r\n?/g, '\n').replace(/\n{2,}/g, '\n')}`).join('\n\n') + '\n';
}
