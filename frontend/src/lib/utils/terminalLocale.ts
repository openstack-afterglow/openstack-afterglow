import type { Terminal } from '@xterm/xterm';
import { t } from '$lib/i18n/ns/common';

/** Update xterm's shared announcements and the existing instance without resetting its buffer. */
export function localizeTerminal(terminal: Terminal): void {
	const strings = (terminal.constructor as typeof Terminal).strings;
	const inputLabel = t('terminal.inputAria');
	strings.promptLabel = inputLabel;
	strings.tooMuchOutput = t('terminal.tooMuchOutput');
	terminal.textarea?.setAttribute('aria-label', inputLabel);
}
