import { describe, expect, it } from 'vitest';
import { classify, listMigrations, pending, type Migration } from './migrations.js';

const migration = (sql: string, version = '20260101000000'): Migration => ({ version, name: 'x', file: 'x.sql', sql });

describe('migration safety classification', () => {
  it('treats every committed migration as expand-only', () => {
    const all = listMigrations();
    expect(all.length).toBeGreaterThan(0);
    for (const m of all) expect(classify(m), m.file).toBe('expand');
  });
  it('flags destructive statements that lack the contract marker', () => {
    for (const sql of [
      'drop table public.cards;',
      'alter table public.cards drop column front;',
      'ALTER TABLE public.cards RENAME TO old_cards;',
      'alter table public.cards alter column n type bigint;',
      'truncate public.cards;',
    ])
      expect(classify(migration(sql)), sql).toBe('unmarked-contract');
  });
  it('accepts an explicit contract marker and ignores keywords in comments and strings', () => {
    expect(classify(migration('-- @contract: remove cards.front after M6\nalter table t drop column front;'))).toBe(
      'contract',
    );
    expect(
      classify(migration("-- drop table x\ncomment on table t is 'drop table y';\n/* truncate t */ select 1;")),
    ).toBe('expand');
    expect(
      classify(
        migration('create function f() returns void as $$ begin drop table if exists t; end $$ language plpgsql;'),
      ),
    ).toBe('expand');
  });
  it('computes pending migrations and refuses when the database is ahead of this checkout', () => {
    const all = [migration('select 1', '20260101000001'), migration('select 2', '20260101000002')];
    expect(pending(all, new Set(['20260101000001'])).map((m) => m.version)).toEqual(['20260101000002']);
    expect(() => pending(all, new Set(['20260101000009']))).toThrow();
  });
});
