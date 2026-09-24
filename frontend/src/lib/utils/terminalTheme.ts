import type { ITheme } from '@xterm/xterm';

function token(style: CSSStyleDeclaration, name: string): string {
	const value = style.getPropertyValue(name).trim();
	if (!value) throw new Error(`Missing terminal color token: ${name}`);
	return value;
}

/** Resolve the active design tokens to concrete canvas colors for xterm. */
export function getTerminalTheme(root: Element = document.documentElement): ITheme {
	const style = getComputedStyle(root);
	return {
		background: token(style, '--color-surface-canvas'),
		foreground: token(style, '--color-ink-1'),
		cursor: token(style, '--color-accent'),
		cursorAccent: token(style, '--color-surface-canvas'),
		selectionBackground: token(style, '--color-surface-selected'),
		black: token(style, '--color-surface-canvas'),
		red: token(style, '--color-state-danger'),
		green: token(style, '--color-state-success'),
		yellow: token(style, '--color-state-warning'),
		blue: token(style, '--color-accent'),
		magenta: token(style, '--color-accent-2'),
		cyan: token(style, '--color-state-info'),
		white: token(style, '--color-ink-1'),
		brightBlack: token(style, '--color-ink-3'),
		brightRed: token(style, '--color-state-danger-text'),
		brightGreen: token(style, '--color-state-success-text'),
		brightYellow: token(style, '--color-state-warning-text'),
		brightBlue: token(style, '--color-accent'),
		brightMagenta: token(style, '--color-accent-2'),
		brightCyan: token(style, '--color-state-info-text'),
		brightWhite: token(style, '--color-ink-0'),
	};
}
