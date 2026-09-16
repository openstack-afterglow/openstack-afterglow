import { describe, expect, it, vi } from 'vitest';
import { createChatRevealBuffer } from '../chatRevealBuffer';

describe('createChatRevealBuffer', () => {
	it('reveals a burst by the bounded browser deadline instead of replaying server cadence', () => {
		const buffer = createChatRevealBuffer({ reducedMotion: false });
		for (let index = 0; index < 500; index += 1) buffer.append('aaaa', index * 5);

		expect(buffer.frame(0)).toEqual({ text: '', pending: true });
		expect(buffer.frame(99).text.length).toBeLessThan(2_000);
		expect(buffer.frame(100)).toEqual({ text: 'a'.repeat(2_000), pending: false });
	});
	it('does not regress after a deadline when a late frame is delivered out of order', () => {
		const buffer = createChatRevealBuffer({ reducedMotion: false });
		buffer.append('authoritative', 0);
		expect(buffer.frame(100)).toEqual({ text: 'authoritative', pending: false });
		expect(buffer.frame(0)).toEqual({ text: 'authoritative', pending: false });
	});

	it('uses receipt time and keeps a sustained stream bounded to one target', () => {
		const buffer = createChatRevealBuffer({ reducedMotion: false });
		buffer.append('one', 1_000);
		expect(buffer.frame(1_050).text).toBe('o');
		buffer.append('two', 1_055);
		buffer.append('three', 1_060);

		expect(buffer.frame(1_099).pending).toBe(true);
		expect(buffer.frame(1_100)).toEqual({ text: 'onetwothree', pending: false });
	});

	it('never cuts a surrogate pair while interpolating', () => {
		const buffer = createChatRevealBuffer({ reducedMotion: false });
		buffer.append('A🙂B', 0);

		expect(buffer.frame(50).text).toBe('A');
		expect(buffer.frame(100)).toEqual({ text: 'A🙂B', pending: false });
	});

	it('reconciles corrected authoritative text before the deadline', () => {
		const buffer = createChatRevealBuffer({ reducedMotion: false });
		buffer.append('wrong', 0);
		expect(buffer.frame(50).text).toBe('wr');
		const correctionAt = 500;
		const now = vi.spyOn(performance, 'now').mockReturnValue(correctionAt);
		buffer.reconcile('right');

		const correctionFrame = buffer.frame(correctionAt);
		expect('right'.startsWith(correctionFrame.text)).toBe(true);
		expect(buffer.frame(correctionAt + 100)).toEqual({ text: 'right', pending: false });
		now.mockRestore();
	});

	it('clears a prior assistant turn before revealing the next one', () => {
		const buffer = createChatRevealBuffer({ reducedMotion: true });
		buffer.append('previous turn', 0);
		expect(buffer.frame(0).text).toBe('previous turn');

		buffer.clear();
		buffer.append('next turn', 1);
		expect(buffer.frame(1).text).toBe('next turn');
	});

	it('drains immediately for terminal or visibility restoration', () => {
		const buffer = createChatRevealBuffer({ reducedMotion: false });
		buffer.append('accessible', 0);
		expect(buffer.drain()).toBe('accessible');
		expect(buffer.frame(0)).toEqual({ text: 'accessible', pending: false });
	});

	it('renders the authoritative value on the next render with reduced motion', () => {
		const buffer = createChatRevealBuffer({ reducedMotion: true });
		buffer.append('accessible', 0);

		expect(buffer.frame(0)).toEqual({ text: 'accessible', pending: false });
	});
});
