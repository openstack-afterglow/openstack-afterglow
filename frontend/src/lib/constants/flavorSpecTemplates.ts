// Flavor extra spec 템플릿 카탈로그.
// FlavorExtraSpecsTab의 "템플릿에서 선택" UI가 사용한다.
// valueType:
//  - enum: options 중 선택
//  - number: 숫자 입력
//  - text: 자유 입력
//  - gpu_alias: GPU alias 드롭다운 + 개수 → "ALIAS:N" 값 생성 (pci_passthrough:alias 전용)

import { t } from '$lib/i18n/ns/admin-compute';

export interface FlavorSpecTemplate {
	key: string;
	category: string;
	label: string;
	description: string;
	valueType: 'enum' | 'number' | 'text' | 'gpu_alias';
	options?: string[];
	placeholder?: string;
	defaultValue?: string;
}

export const FLAVOR_SPEC_TEMPLATES: FlavorSpecTemplate[] = [
	// === GPU ===
	{
		key: 'pci_passthrough:alias',
		category: 'GPU',
		get label() { return t('flavorTemplates.gpuPassthrough.label'); },
		get description() { return t('flavorTemplates.gpuPassthrough.description'); },
		valueType: 'gpu_alias',
	},
	{
		key: 'hw:hide_hypervisor_id',
		category: 'GPU',
		get label() { return t('flavorTemplates.hideHypervisor.label'); },
		get description() { return t('flavorTemplates.hideHypervisor.description'); },
		valueType: 'enum',
		options: ['true'],
		defaultValue: 'true',
	},
	// === CPU ===
	{
		key: 'hw:numa_nodes',
		category: 'CPU',
		get label() { return t('flavorTemplates.numaNodes.label'); },
		get description() { return t('flavorTemplates.numaNodes.description'); },
		valueType: 'number',
		get placeholder() { return t('flavorTemplates.exampleTwo'); },
	},
	{
		key: 'hw:cpu_policy',
		category: 'CPU',
		get label() { return t('flavorTemplates.cpuPolicy.label'); },
		get description() { return t('flavorTemplates.cpuPolicy.description'); },
		valueType: 'enum',
		options: ['shared', 'dedicated'],
	},
	{
		key: 'hw:cpu_thread_policy',
		category: 'CPU',
		get label() { return t('flavorTemplates.cpuThreadPolicy.label'); },
		get description() { return t('flavorTemplates.cpuThreadPolicy.description'); },
		valueType: 'enum',
		options: ['prefer', 'isolate', 'require'],
	},
	{
		key: 'hw:cpu_sockets',
		category: 'CPU',
		get label() { return t('flavorTemplates.cpuSockets.label'); },
		get description() { return t('flavorTemplates.cpuSockets.description'); },
		valueType: 'number',
		get placeholder() { return t('flavorTemplates.exampleOne'); },
	},
	{
		key: 'hw:cpu_cores',
		category: 'CPU',
		get label() { return t('flavorTemplates.cpuCores.label'); },
		get description() { return t('flavorTemplates.cpuCores.description'); },
		valueType: 'number',
		get placeholder() { return t('flavorTemplates.exampleEight'); },
	},
	{
		key: 'hw:cpu_threads',
		category: 'CPU',
		get label() { return t('flavorTemplates.cpuThreads.label'); },
		get description() { return t('flavorTemplates.cpuThreads.description'); },
		valueType: 'number',
		get placeholder() { return t('flavorTemplates.exampleTwo'); },
	},
	// === 메모리 ===
	{
		key: 'hw:mem_page_size',
		category: 'memory',
		get label() { return t('flavorTemplates.memoryPageSize.label'); },
		get description() { return t('flavorTemplates.memoryPageSize.description'); },
		valueType: 'enum',
		options: ['small', 'large', '2MB', '1GB'],
	},
	// === QoS ===
	{
		key: 'quota:cpu_shares',
		category: 'QoS',
		get label() { return t('flavorTemplates.cpuShares.label'); },
		get description() { return t('flavorTemplates.cpuShares.description'); },
		valueType: 'number',
		get placeholder() { return t('flavorTemplates.exampleShares'); },
	},
	{
		key: 'quota:disk_read_bytes_sec',
		category: 'QoS',
		get label() { return t('flavorTemplates.diskRead.label'); },
		get description() { return t('flavorTemplates.diskRead.description'); },
		valueType: 'number',
		get placeholder() { return t('flavorTemplates.exampleDiskRate'); },
	},
	{
		key: 'quota:disk_write_bytes_sec',
		category: 'QoS',
		get label() { return t('flavorTemplates.diskWrite.label'); },
		get description() { return t('flavorTemplates.diskWrite.description'); },
		valueType: 'number',
		get placeholder() { return t('flavorTemplates.exampleDiskRate'); },
	},
];

export const FLAVOR_SPEC_CATEGORIES = [...new Set(FLAVOR_SPEC_TEMPLATES.map((t) => t.category))];

export function flavorSpecCategoryLabel(category: string): string {
	switch (category) {
		case 'GPU': return t('flavorTemplates.categories.gpu');
		case 'CPU': return t('flavorTemplates.categories.cpu');
		case 'memory': return t('flavorTemplates.categories.memory');
		case 'QoS': return t('flavorTemplates.categories.qos');
		default: return category;
	}
}
