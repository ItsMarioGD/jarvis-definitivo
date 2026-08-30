/**
 * /api/media — read media_history table from jarvis_memory.db (SQLite).
 * Falls back to an empty array when the DB is missing so the HUD keeps working.
 */
import { Router } from "express";
import path from "node:path";
import fs from "node:fs";
import Database from "better-sqlite3";

let db: Database.Database | null = null;
function open() {
  if (db) return db;
  const candidates = [
    process.env.JARVIS_MEMORY_DB,
    path.resolve(process.cwd(), "jarvis_memory.db"),
    path.resolve(process.cwd(), "../jarvis_memory.db"),
    path.resolve(process.cwd(), "../../jarvis_memory.db"),
  ].filter(Boolean) as string[];

  for (const p of candidates) {
    if (fs.existsSync(p)) {
      try {
        db = new Database(p, { readonly: true });
        return db;
      } catch { /* try next */ }
    }
  }
  return null;
}

export const mediaRouter = Router();

mediaRouter.get("/", (_req, res) => {
  const conn = open();
  if (!conn) return res.json([]);
  try {
    const rows = conn
      .prepare(`SELECT id, media_type as type, prompt, path,
                       strftime('%s', timestamp) * 1000 as ts
                FROM media_history ORDER BY id DESC LIMIT 60`)
      .all() as any[];
    res.json(rows.map((r) => ({ id: String(r.id), ...r, ts: Number(r.ts) })));
  } catch {
    res.json([]);
  }
});
