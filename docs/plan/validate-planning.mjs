// Documentation-only audit; reads tracked planning/spec files, never environment files.
import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const read = (file) => readFileSync(resolve(root, file), 'utf8');
const checklistPath = 'docs/checklist/ENGINEERING_CHECKLIST.md';
// Initial repository snapshot before this planning slice, fixed for reproducibility.
const original = execFileSync('git', ['show', 'f1544f9:' + checklistPath], { cwd: root, encoding: 'utf8' });
const checklist = read(checklistPath);
const plan = read('docs/plan/M0-M11-task-breakdown.md');
const triage = read('docs/plan/checklist-triage.md');
const items = (text) => [...text.matchAll(/^- \[[ x]\] (.+)$/gm)].map((m) => m[1].replace(/^DEFERRED /, '').replace(/ — DEFERRED until .*$/, '').trim());
assert.deepEqual(items(checklist), items(original), 'Original item text/order changed');
assert.equal(items(checklist).length, 1147);
const notes = [...checklist.matchAll(/^\*\*(.+?)\*\* — priority:/gm)].map((m) => m[1]);
assert.equal(notes.length, 183);
const triageRows = [...triage.matchAll(/^\| <a id="n(\d{3})"><\/a>\[N\d{3} — (.+?)\]\(/gm)];
assert.deepEqual(triageRows.map((m) => m[2]), notes, 'Triage note coverage/order differs');
const taskRows = [...plan.matchAll(/^\| <a id="(m\d+-\d+)"><\/a>(M\d+-\d+) \|/gm)];
assert.equal(taskRows.length, 145);
assert.equal(new Set(taskRows.map((m) => m[1])).size, 145);
const stories = [...read('docs/spec/01 - Product Requirements (PRD).md').matchAll(/\*\*([A-Z]+-\d{2})\*\*/g)].map((m) => m[1]);
for (const story of stories) assert(plan.includes('[' + story + ']'), 'Missing PRD story ' + story);
for (const row of triage.split('\n').filter((line) => line.startsWith('| <a id='))) {
  assert(row.includes('**DEFERRED**') || /\[M\d+-\d+\]/.test(row), 'Active note without task owner');
}
let linkCount = 0;
for (const file of ['docs/plan/M0-M11-task-breakdown.md', 'docs/plan/checklist-triage.md', 'PROGRESS.md']) {
  for (const match of read(file).matchAll(/\[[^\]]+\]\(([^)]+)\)/g)) {
    const [encoded, anchor] = match[1].split('#');
    if (/^[a-z]+:/i.test(encoded)) continue;
    const target = resolve(root, dirname(file), decodeURIComponent(encoded));
    assert(existsSync(target), 'Missing local link: ' + match[1]);
    if (anchor) assert(readFileSync(target, 'utf8').includes('id="' + anchor + '"'), 'Missing explicit anchor: ' + match[1]);
    linkCount++;
  }
}
assert.equal((checklist.match(/^- \[ \] DEFERRED /gm) || []).length, 176);
assert.equal((checklist.match(/^- \[x\]/gm) || []).length, 0);
assert.equal((checklist.match(/^- \[ \] (?!DEFERRED )/gm) || []).length, 971);
console.log(JSON.stringify({ notes: notes.length, originalItemsPreserved: 1147, tasks: taskRows.length, prdStoriesCovered: stories.length, localLinksChecked: linkCount, deferred: 176, open: 971, verifiedImplementationItems: 0 }, null, 2));
