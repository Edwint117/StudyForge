import { readFileSync } from 'node:fs';
import { runCli } from '../env/cli.js';
import { ConfigError } from '../../packages/config/src/index.js';

const TYPES = ['feat', 'fix', 'docs', 'style', 'refactor', 'perf', 'test', 'build', 'ci', 'chore', 'revert', 'merge'];
const VAGUE = /^(wip|update|updates|updated|fix|fixes|fixed|change|changes|changed|stuff|misc|tweaks?|cleanup)$/i;
const HEADER = new RegExp(`^(${TYPES.join('|')})(\\([a-z0-9][a-z0-9._/-]*\\))?!?: \\S.{0,99}$`);

/** Conventional Commits header check (doc 02 section 6). Git-generated merge/revert headers pass untouched. */
export function conventionalHeader(message: string): boolean {
  const header = message.split(/\r?\n/, 1)[0] ?? '';
  if (/^(Merge|Revert|fixup!|squash!) /.test(header)) return true;
  // The summary is the purpose (docs/setup/COMMIT_STYLE.md): no full stop, and not a vague filler word on its own.
  const summary = header.replace(/^[^:]*: /, '');
  return HEADER.test(header) && !header.endsWith('.') && !VAGUE.test(summary);
}

runCli(import.meta.url, () => {
  const path = process.argv[2];
  if (process.argv.length !== 3 || !path) throw new ConfigError(['CLI_OPTIONS']);
  if (!conventionalHeader(readFileSync(path, 'utf8')))
    throw new ConfigError(
      ['COMMIT_MESSAGE'],
      `commit_message_must_be_conventional: <type>(<scope>): <summary>; types: ${TYPES.join(', ')}`,
    );
});
