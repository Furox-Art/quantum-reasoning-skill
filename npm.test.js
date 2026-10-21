'use strict';

const assert = require('assert');
const path = require('path');
const { spawnSync } = require('child_process');

const cli = path.join(__dirname, 'index.js');

const validate = spawnSync(process.execPath, [cli, '--validate'], { encoding: 'utf8' });
assert.strictEqual(validate.status, 0, validate.stderr);

const unsupported = spawnSync(process.execPath, [cli, '--bogus'], { encoding: 'utf8' });
assert.strictEqual(unsupported.status, 2, 'an unsupported flag must exit 2');
assert.match(unsupported.stderr, /unsupported flag/);

const skill = require('./index.js');
assert.strictEqual(skill.loadSkill().valid, true);

console.log('npm CLI contract OK');
