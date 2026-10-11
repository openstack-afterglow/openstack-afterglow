export interface DocLink {
	label: string;
	href: string;
	description?: string;
}

export interface DocCommand {
	label: string;
	code: string;
}

/** Public full-resolution local asset; alt/caption are localized, dimensions are intrinsic pixels. */
export interface DocScreenshot {
	src: string;
	alt: string;
	caption: string;
	width: number;
	height: number;
}

export interface DocStep {
	title: string;
	text: string[];
	command?: DocCommand;
	links?: DocLink[];
	screenshots?: DocScreenshot[];
}

export interface DocSection {
	id: string;
	title: string;
	paragraphs?: string[];
	bullets?: string[];
	steps?: DocStep[];
	commands?: DocCommand[];
	callout?: {
		tone: 'info' | 'warning' | 'neutral';
		title: string;
		text: string;
	};
	links?: DocLink[];
	screenshots?: DocScreenshot[];
}

export interface DocGuide {
	slug: string;
	name: string;
	title: string;
	summary: string;
	category: 'start' | 'openstack' | 'afterglow';
	keywords: string[];
	prerequisites: string[];
	sections: DocSection[];
	related: string[];
	consoleLinks: (DocLink & { service?: string })[];
	externalLinks?: DocLink[];
}
