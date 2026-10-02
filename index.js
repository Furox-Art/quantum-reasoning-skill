#!/usr/bin/env node
'use strict';

/**
 * quantum-reasoning-skill
 *
 * A real, executable entry point for the Node/MCP host ecosystem. It reads the
 * skill contract that ships with this package and exposes it programmatically
 * and from the command line.
 *
 * The previous implementation did `require('./SKILL.md')`, which made Node
 * parse Markdown as JavaScript and throw a SyntaxError on every import.
 * SKILL.md is now read as text via fs.readFileSync.
 */

const fs = require('fs');
const path = require('path');

const REQUIRED_FIELDS = ['name', 'description'];

const SKILL_FILE = path.join(__dirname, 'SKILL.md');
const VERSION_FILE = path.join(__dirname, 'VERSION');

/**
 * Parse leading `---` delimited front matter from the skill document.
 * Deliberately dependency-free: the contract only uses `key: value` pairs.
 *
 * @param {string} text
 * @returns {{fields: Record<string,string>, fenceEnd: number}}
 */
function parseFrontMatter(text) {
  const lines = text.split(/\r?\n/);
  if (lines.length === 0 || lines[0].trim() !== '---') {
    throw new Error('SKILL.md must start with a `---` front matter fence');
  }
  let fenceEnd = -1;
  for (let i = 1; i < lines.length; i += 1) {
    if (lines[i].trim() === '---') {
      fenceEnd = i;
      break;
    }
  }
  if (fenceEnd === -1) {
    throw new Error('SKILL.md front matter is not closed');
  }
  const fields = Object.create(null);
  for (const line of lines.slice(1, fenceEnd)) {
    const trimmed = line.trim();
    if (trimmed === '' || trimmed.startsWith('#')) continue;
    const idx = trimmed.indexOf(':');
    if (idx === -1) continue;
    const key = trimmed.slice(0, idx).trim();
    let value = trimmed.slice(idx + 1).trim();
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    fields[key] = value;
  }
  return { fields, fenceEnd };
}

/**
 * Read the packaged skill contract from disk.
 *
 * @returns {string}
 */
function readSkillDocument() {
  return fs.readFileSync(SKILL_FILE, 'utf8');
}

/**
 * Read the packaged VERSION file.
 *
 * @returns {string}
 */
function readVersion() {
  const raw = fs.readFileSync(VERSION_FILE, 'utf8').trim();
  return raw.startsWith('v') ? raw.slice(1) : raw;
}

/**
 * Validate the skill contract.
 *
 * @param {string} text
 * @returns {{name: string, description: string, descriptionLength: number,
 *            bodyLines: number, valid: boolean, problems: string[]}}
 */
function validateSkill(text) {
  const { fields, fenceEnd } = parseFrontMatter(text);
  const problems = [];
  for (const field of REQUIRED_FIELDS) {
    if (!fields[field]) {
      problems.push(`front matter must define a non-empty \`${field}\``);
    }
  }
  if (fields.name && fields.name !== 'quantum-reasoning') {
    problems.push('front matter `name` must be `quantum-reasoning`');
  }
  const bodyLines = text.split(/\r?\n/).slice(fenceEnd + 1).length;
  if (bodyLines < 20) {
    problems.push(`SKILL.md body is too short (${bodyLines} lines, expected >= 20)`);
  }
  return {
    name: fields.name || '',
    description: fields.description || '',
    descriptionLength: (fields.description || '').length,
    bodyLines,
    valid: problems.length === 0,
    problems,
  };
}

/**
 * Load and validate the packaged skill in one call.
 *
 * @returns {object} the parsed skill definition
 */
function loadSkill() {
  const document = readSkillDocument();
  const { fields } = parseFrontMatter(document);
  const report = validateSkill(document);
  return {
    name: report.name,
    description: report.description,
    version: readVersion(),
    document,
    valid: report.valid,
    problems: report.problems,
    metadata: fields,
  };
}

const USAGE = `quantum-reasoning — inspect the packaged skill contract

Usage:
  quantum-reasoning              Print the skill summary
  quantum-reasoning --json       Print the full report as JSON
  quantum-reasoning --validate   Exit non-zero if the contract is invalid
  quantum-reasoning --path       Print the absolute SKILL.md path
  quantum-reasoning --help       Show this message

Exit codes:
  0  success
  1  invalid skill contract (--validate)
  2  SKILL.md could not be read
`;

function main(argv) {
  const args = argv.slice(2);
  const wantsJson = args.includes('--json');
  const wantsValidate = args.includes('--validate');
  const wantsPath = args.includes('--path');

  if (args.includes('--help') || args.includes('-h')) {
    process.stdout.write(USAGE);
    return 0;
  }

  let report;
  try {
    report = validateSkill(readSkillDocument());
  } catch (error) {
    process.stderr.write(`error: ${error.message}\n`);
    return 2;
  }
  report.version = readVersion();
  report.path = SKILL_FILE;

  if (wantsPath) {
    process.stdout.write(`${SKILL_FILE}\n`);
    return 0;
  }
  if (wantsJson) {
    process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
  } else {
    process.stdout.write(`skill:   ${report.name || '<missing name>'}\n`);
    process.stdout.write(`status:  ${report.valid ? 'valid' : 'INVALID'}\n`);
    process.stdout.write(`file:    ${SKILL_FILE}\n`);
    process.stdout.write(`version: ${report.version}\n`);
    process.stdout.write(`body:    ${report.bodyLines} lines\n`);
    for (const problem of report.problems) {
      process.stdout.write(`  - ${problem}\n`);
    }
  }
  if (wantsValidate && !report.valid) {
    return 1;
  }
  return 0;
}

module.exports = {
  name: 'quantum-reasoning-skill',
  version: readVersion(),
  skillFile: SKILL_FILE,
  parseFrontMatter,
  readSkillDocument,
  readVersion,
  validateSkill,
  loadSkill,
};

if (require.main === module) {
  process.exitCode = main(process.argv);
}