export interface ChatRevealBuffer {
	append(delta: string, receivedAtMs?: number): void;
	reconcile(text: string): void;
	frame(nowMs?: number): { text: string; pending: boolean };
	drain(): string;
	clear(): void;
}

const REVEAL_DEADLINE_MS = 100;

function codePointLength(text: string): number {
	return Array.from(text).length;
}

/** Return a prefix ending on a Unicode code-point boundary. */
function safePrefix(text: string, codePoints: number): string {
	if (codePoints <= 0) return '';
	if (codePoints >= codePointLength(text)) return text;
	const units = Array.from(text).slice(0, codePoints).join('');
	return units;
}

function commonPrefix(left: string, right: string): string {
	const leftPoints = Array.from(left);
	const rightPoints = Array.from(right);
	let count = 0;
	while (count < leftPoints.length && leftPoints[count] === rightPoints[count]) count += 1;
	return leftPoints.slice(0, count).join('');
}

/**
 * Smooths authoritative SSE text for display only. The browser receipt clock
 * starts one bounded interpolation target; server cadence is deliberately not
 * replayed, and drain always returns the exact authoritative text.
 */
export function createChatRevealBuffer(options: { reducedMotion: boolean }): ChatRevealBuffer {
	let authoritativeText = '';
	let displayed = '';
	let pendingSinceMs: number | null = null;
	let pendingBaseCodePoints = 0;
	let lastFrameMs = Number.NEGATIVE_INFINITY;

	function setTarget(receivedAtMs: number, resetWindow = false) {
		if (displayed === authoritativeText) {
			pendingSinceMs = null;
			pendingBaseCodePoints = 0;
			return;
		}
		if (pendingSinceMs === null || resetWindow) {
			pendingSinceMs = receivedAtMs;
			pendingBaseCodePoints = codePointLength(displayed);
		}
	}

	return {
		append(delta, receivedAtMs = performance.now()) {
			if (!delta) return;
			authoritativeText += delta;
			setTarget(receivedAtMs);
		},
		reconcile(text) {
			authoritativeText = text;
			if (!text.startsWith(displayed)) displayed = commonPrefix(displayed, text);
			// A correction starts a new authoritative baseline; reset the frame
			// clock so synthetic receipt timestamps cannot leave it in the future.
			const correctionAt = performance.now();
			lastFrameMs = correctionAt;
			setTarget(correctionAt, true);
		},
		frame(nowMs = performance.now()) {
			const clock = Math.max(nowMs, lastFrameMs);
			lastFrameMs = clock;
			if (options.reducedMotion) {
				displayed = authoritativeText;
				pendingSinceMs = null;
				pendingBaseCodePoints = 0;
			} else if (pendingSinceMs !== null) {
				const elapsed = Math.max(0, clock - pendingSinceMs);
				const progress = Math.min(1, elapsed / REVEAL_DEADLINE_MS);
				const targetLength = codePointLength(authoritativeText);
				const baseLength = Math.min(pendingBaseCodePoints, targetLength);
				const remaining = targetLength - baseLength;
				const revealCount =
					baseLength +
					(elapsed > 0 && remaining > 0 ? Math.max(1, Math.floor(remaining * progress)) : 0);
				const next = safePrefix(authoritativeText, revealCount);
				// A late/out-of-order browser frame must not roll a completed
				// deadline (or a newer correction baseline) backwards.
				if (authoritativeText.startsWith(displayed) && next.length >= displayed.length) {
					displayed = next;
				}
				if (progress >= 1) {
					displayed = authoritativeText;
					pendingSinceMs = null;
					pendingBaseCodePoints = 0;
				}
			}
			return {
				text: displayed,
				pending: pendingSinceMs !== null
			};
		},
		drain() {
			displayed = authoritativeText;
			pendingSinceMs = null;
			pendingBaseCodePoints = 0;
			return displayed;
		},
		clear() {
			authoritativeText = '';
			displayed = '';
			pendingSinceMs = null;
			pendingBaseCodePoints = 0;
			lastFrameMs = Number.NEGATIVE_INFINITY;
		}
	};
}
