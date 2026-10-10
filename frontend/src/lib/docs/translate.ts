import type { DocCommand, DocGuide, DocSection } from './types';

/** Structural IDs, URLs, service gates and executable code always come from the source guide. */
export function translateDocGuide(guide: DocGuide, translations: Readonly<Record<string, string>>): DocGuide {
	function text(source: string): string {
		const translated = translations[source];
		if (typeof translated !== 'string' || translated.trim() === '') {
			throw new Error(`Missing documentation translation: ${guide.slug}: ${source}`);
		}
		return translated;
	}
	const texts = (items: string[]) => items.map(text);
	const link = (item: DocGuide['consoleLinks'][number]) => ({
		...item,
		label: text(item.label),
		description: item.description === undefined ? undefined : text(item.description),
	});
	const command = (item: DocCommand) => ({ ...item, label: text(item.label) });
	const section = (item: DocSection): DocSection => ({
		...item,
		title: text(item.title),
		paragraphs: item.paragraphs?.map(text),
		bullets: item.bullets?.map(text),
		steps: item.steps?.map((step) => ({
			...step,
			title: text(step.title),
			text: texts(step.text),
			command: step.command && command(step.command),
			links: step.links?.map(link),
		})),
		commands: item.commands?.map(command),
		callout: item.callout && { ...item.callout, title: text(item.callout.title), text: text(item.callout.text) },
		links: item.links?.map(link),
	});
	return {
		...guide,
		name: text(guide.name),
		title: text(guide.title),
		summary: text(guide.summary),
		keywords: texts(guide.keywords),
		prerequisites: texts(guide.prerequisites),
		sections: guide.sections.map(section),
		consoleLinks: guide.consoleLinks.map(link),
		externalLinks: guide.externalLinks?.map(link),
	};
}
