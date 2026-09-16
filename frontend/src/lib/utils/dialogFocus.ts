export interface DialogFocusOptions {
	enabled: boolean;
	onEscape: () => void;
	initialFocus?: string;
}

interface DialogRecord {
	node: HTMLElement;
	options: DialogFocusOptions;
	opener: HTMLElement | null;
	enabled: boolean;
}

const stack: DialogRecord[] = [];
const inertWrites = new Map<HTMLElement, boolean>();
const FOCUSABLE_SELECTOR = [
	'a[href]',
	'button:not([disabled])',
	'input:not([disabled])',
	'select:not([disabled])',
	'textarea:not([disabled])',
	'[tabindex]:not([tabindex="-1"])',
].join(',');

function isUsable(element: HTMLElement): boolean {
	if (!element.isConnected || element.hidden || element.inert) return false;
	if (element.getAttribute('aria-hidden') === 'true') return false;
	const style = getComputedStyle(element);
	return style.display !== 'none' && style.visibility !== 'hidden';
}

function focusableElements(node: HTMLElement): HTMLElement[] {
	return [...node.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)].filter(isUsable);
}

function restoreIsolation(): void {
	for (const [element, previous] of inertWrites) element.inert = previous;
	inertWrites.clear();
}

function isolateTopDialog(): void {
	restoreIsolation();
	const active = stack.at(-1);
	if (!active?.enabled || !active.node.isConnected) return;

	let branch: HTMLElement = active.node;
	while (branch.parentElement) {
		const parent = branch.parentElement;
		for (const sibling of parent.children) {
			if (!(sibling instanceof HTMLElement) || sibling === branch) continue;
			if (!inertWrites.has(sibling)) inertWrites.set(sibling, sibling.inert);
			sibling.inert = true;
		}
		if (parent === document.body) break;
		branch = parent;
	}
}

function focusInitial(record: DialogRecord): void {
	queueMicrotask(() => {
		if (stack.at(-1) !== record || !record.enabled || !record.node.isConnected) return;
		const requested = record.options.initialFocus
			? record.node.querySelector<HTMLElement>(record.options.initialFocus)
			: null;
		const target = requested && isUsable(requested)
			? requested
			: focusableElements(record.node)[0] ?? record.node;
		target.focus();
	});
}

function enable(record: DialogRecord): void {
	if (record.enabled) return;
	record.enabled = true;
	record.opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
	stack.push(record);
	isolateTopDialog();
	focusInitial(record);
}

function disable(record: DialogRecord, restoreFocus = true): void {
	if (!record.enabled) return;
	record.enabled = false;
	const index = stack.lastIndexOf(record);
	if (index >= 0) stack.splice(index, 1);
	isolateTopDialog();
	if (restoreFocus) {
		const opener = record.opener;
		queueMicrotask(() => {
			if (opener?.isConnected && !opener.inert) opener.focus();
		});
	}
}

function handleKeydown(event: KeyboardEvent): void {
	const record = stack.at(-1);
	if (!record?.enabled) return;

	if (event.key === 'Escape') {
		event.preventDefault();
		event.stopImmediatePropagation();
		record.options.onEscape();
		return;
	}
	if (event.key !== 'Tab') return;

	const focusable = focusableElements(record.node);
	event.preventDefault();
	event.stopImmediatePropagation();
	if (focusable.length === 0) {
		record.node.focus();
		return;
	}
	const current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
	const currentIndex = current ? focusable.indexOf(current) : -1;
	const nextIndex = event.shiftKey
		? (currentIndex <= 0 ? focusable.length - 1 : currentIndex - 1)
		: (currentIndex < 0 || currentIndex === focusable.length - 1 ? 0 : currentIndex + 1);
	focusable[nextIndex]?.focus();
}

if (typeof document !== 'undefined') document.addEventListener('keydown', handleKeydown, true);

export function dialogFocus(node: HTMLElement, options: DialogFocusOptions): {
	update: (options: DialogFocusOptions) => void;
	destroy: () => void;
} {
	const record: DialogRecord = { node, options, opener: null, enabled: false };
	if (options.enabled) enable(record);

	return {
		update(nextOptions) {
			const wasEnabled = record.enabled;
			record.options = nextOptions;
			if (nextOptions.enabled && !wasEnabled) enable(record);
			else if (!nextOptions.enabled && wasEnabled) disable(record);
			else if (record.enabled) isolateTopDialog();
		},
		destroy() {
			disable(record);
		},
	};
}
