export interface DocLink {
	label: string;
	href: string;
	description?: string;
}

export interface DocCommand {
	label: string;
	code: string;
}

export interface DocStep {
	title: string;
	text: string[];
	command?: DocCommand;
	links?: DocLink[];
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
