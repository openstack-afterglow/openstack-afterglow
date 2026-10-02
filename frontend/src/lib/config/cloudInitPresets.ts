import { t } from '$lib/i18n/ns/vm-wizard';

export const CLOUD_INIT_PRESETS = [
	{ id: 'system-update', get label() { return t('presets.systemUpdate'); }, content: '#cloud-config\npackage_update: true\npackage_upgrade: true\n' },
	{ id: 'developer-tools', get label() { return t('presets.developerTools'); }, content: '#cloud-config\npackages:\n  - git\n  - curl\n  - htop\n  - jq\n' },
	{ id: 'docker-runtime', get label() { return t('presets.dockerRuntime'); }, content: '#cloud-config\npackages:\n  - docker.io\nruncmd:\n  - systemctl enable --now docker\n' },
] as const;
