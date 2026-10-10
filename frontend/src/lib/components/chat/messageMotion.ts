/** Runtime-only ticket, created by local sends, never inferred from ids/timestamps or persisted. */
export interface MessageEntrance {
	pending: boolean;
}

export function freshMessageEntrance(): MessageEntrance {
	return { pending: true };
}

/** Consume at mount, not per token. Copies of a draft share its ticket, so remounts cannot replay. */
export function messageEntrance(node: HTMLElement, { ticket, suppressed = false }: {
	ticket?: MessageEntrance;
	suppressed?: boolean;
}): { destroy: () => void } {
	if (ticket?.pending) {
		ticket.pending = false;
		if (!suppressed) node.classList.add('motion-enter');
	}
	const finish = (event: AnimationEvent) => {
		if (event.target === node) node.classList.remove('motion-enter');
	};
	node.addEventListener('animationend', finish);
	return { destroy: () => node.removeEventListener('animationend', finish) };
}
