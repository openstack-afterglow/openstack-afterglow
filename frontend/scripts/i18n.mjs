#!/usr/bin/env node
// @ts-check
/**
 * Translation catalog workflow for developers and translators.
 *
 *   node scripts/i18n.mjs check [--namespace ns]          validate every catalog (CI gate)
 *   node scripts/i18n.mjs report [--locale ja] [--by-namespace]
 *   node scripts/i18n.mjs export --locale ja [--namespace ns] [--status draft,outdated] [--out file.csv]
 *   node scripts/i18n.mjs import --locale ja --file file.csv [--reviewed]
 *   node scripts/i18n.mjs review --locale ja --namespace ns [--key a.b ...]
 *   node scripts/i18n.mjs format                           rewrite catalogs in Korean key order
 *   node scripts/i18n.mjs scan [--file src/...]            list Korean text still hard-coded in source
 */
import path from 'node:path';
import { readFile, writeFile } from 'node:fs/promises';
import {
	TRANSLATION_LOCALES,
	exportCsv,
	importCsv,
	loadCatalogs,
	loadReviews,
	markReviewed,
	reviewReport,
	validateCatalogs,
	writeCatalogs,
} from './i18n-core.mjs';
import { FRONTEND_DIR, collectSourceFiles, loadAllowlist, scanHardcodedText } from './i18n-scan.mjs';

/** @param {string[]} argv */
function parseArgs(argv) {
	/** @type {Record<string, string[]>} */
	const options = {};
	const positional = [];
	for (let i = 0; i < argv.length; i += 1) {
		const arg = argv[i];
		if (!arg.startsWith('--')) {
			positional.push(arg);
			continue;
		}
		const name = arg.slice(2);
		const next = argv[i + 1];
		const value = next === undefined || next.startsWith('--') ? 'true' : (i += 1, next);
		(options[name] ??= []).push(...value.split(',').map((part) => part.trim()).filter(Boolean));
	}
	return { command: positional[0] ?? 'help', options };
}

/** @param {Record<string, string[]>} options @param {string} name */
function requireLocale(options, name = 'locale') {
	const locale = options[name]?.[0];
	if (!locale || !TRANSLATION_LOCALES.includes(locale)) {
		throw new Error(`--${name} must be one of ${TRANSLATION_LOCALES.join(', ')}`);
	}
	return locale;
}

async function main() {
	const { command, options } = parseArgs(process.argv.slice(2));

	if (command === 'scan') {
		const files = options.file?.map((file) => path.resolve(FRONTEND_DIR, file)) ?? (await collectSourceFiles());
		const findings = await scanHardcodedText(files, await loadAllowlist());
		for (const finding of findings) console.log(`${finding.file}:${finding.line}: ${finding.text}`);
		console.log(`${findings.length} hard-coded Korean lines in ${files.length} files`);
		process.exitCode = findings.length ? 1 : 0;
		return;
	}

	const catalogs = await loadCatalogs();
	const reviews = await loadReviews();

	if (command === 'check') {
		const scope = options.namespace;
		const findings = validateCatalogs(catalogs).filter((finding) => !scope || !finding.namespace || scope.includes(finding.namespace));
		for (const namespace of scope ?? []) {
			if (!catalogs.namespaces.includes(namespace)) findings.push({ level: 'error', code: 'unknown-namespace', namespace, detail: 'namespace does not exist' });
		}
		for (const finding of findings) {
			const where = [finding.locale, finding.namespace && `${finding.namespace}${finding.key ? `:${finding.key}` : ''}`].filter(Boolean).join(' ');
			console.log(`${finding.level.toUpperCase()} ${finding.code} ${where} — ${finding.detail}`);
		}
		const errors = findings.filter((finding) => finding.level === 'error').length;
		const keys = Object.values(catalogs.messages.ko).reduce((sum, messages) => sum + Object.keys(messages).length, 0);
		console.log(`${errors} errors, ${findings.length - errors} warnings · ${catalogs.namespaces.length} namespaces · ${keys} source messages`);
		process.exitCode = errors ? 1 : 0;
		return;
	}

	if (command === 'report') {
		const locales = options.locale ?? TRANSLATION_LOCALES;
		const rows = reviewReport(catalogs, reviews).filter((row) => locales.includes(row.locale));
		const header = ['locale', 'namespace', 'total', 'reviewed', 'outdated', 'draft', 'missing'];
		/** @type {Array<Record<string, string | number>>} */
		let table = rows;
		if (!options['by-namespace']) {
			table = locales.map((locale) => {
				const totals = { locale, namespace: '(all)', total: 0, reviewed: 0, outdated: 0, draft: 0, missing: 0 };
				for (const row of rows.filter((candidate) => candidate.locale === locale)) {
					for (const field of /** @type {const} */ (['total', 'reviewed', 'outdated', 'draft', 'missing'])) totals[field] += row[field];
				}
				return totals;
			});
		}
		console.log(header.join('\t'));
		for (const row of table) console.log(header.map((field) => row[field]).join('\t'));
		return;
	}

	if (command === 'export') {
		const locale = requireLocale(options);
		const csv = exportCsv(catalogs, reviews, locale, {
			namespaces: options.namespace,
			states: /** @type {import('./i18n-core.mjs').ReviewState[] | undefined} */ (options.status),
		});
		const out = options.out?.[0];
		if (out) {
			await writeFile(out, csv);
			console.log(`wrote ${csv.split('\r\n').length - 2} rows to ${out}`);
		} else {
			process.stdout.write(csv);
		}
		return;
	}

	if (command === 'import') {
		const locale = requireLocale(options);
		const file = options.file?.[0];
		if (!file) throw new Error('--file is required');
		const result = importCsv(catalogs, reviews, locale, await readFile(file, 'utf8'), { markReviewed: Boolean(options.reviewed) });
		if (result.errors.length) {
			for (const error of result.errors) console.error(error);
			console.error(`import aborted: ${result.errors.length} problems, nothing was written`);
			process.exitCode = 1;
			return;
		}
		await writeCatalogs(catalogs, reviews);
		console.log(`updated ${result.updated} ${locale} messages${options.reviewed ? ' and marked them reviewed' : ''}`);
		return;
	}

	if (command === 'review') {
		const locale = requireLocale(options);
		const namespaces = options.namespace;
		if (!namespaces?.length) throw new Error('--namespace is required');
		let marked = 0;
		for (const namespace of namespaces) marked += markReviewed(catalogs, reviews, locale, namespace, options.key);
		await writeCatalogs(catalogs, reviews);
		console.log(`marked ${marked} ${locale} messages as reviewed`);
		return;
	}

	if (command === 'format') {
		await writeCatalogs(catalogs, reviews);
		console.log('catalogs rewritten in Korean key order');
		return;
	}

	console.log('usage: node scripts/i18n.mjs <check|report|export|import|review|format> [options] — see the header of this file');
	process.exitCode = command === 'help' ? 0 : 1;
}

main().catch((error) => {
	console.error(error instanceof Error ? error.message : error);
	process.exitCode = 1;
});
