// One-shot in-memory transfer. Never persist audio bytes or transcript to browser storage.
let pending: { userId: string; projectId: string; text: string } | null = null;

export function offerAudioTranscript(userId: string, projectId: string, text: string): void {
	pending = { userId, projectId, text };
}

export function takeAudioTranscript(userId: string, projectId: string): string | null {
	const value = pending;
	pending = null;
	return value?.userId === userId && value.projectId === projectId ? value.text : null;
}
