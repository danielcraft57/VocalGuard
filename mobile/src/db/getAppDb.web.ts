/**
 * Singleton DB memoire pour le dev web (expo-sqlite/wasm non requis).
 */
import { log } from "../services/log";
import { createMemoryDb, migrateDb, type SqlDb } from "./client";

let appDb: SqlDb | null = null;

/**
 * Retourne la base app en memoire (navigateur).
 *
 * @returns DB prete (migree).
 */
export async function getAppDb(): Promise<SqlDb> {
  if (appDb) {
    log.debug("db", "reuse web memory");
    return appDb;
  }
  log.info("db", "open web memory db");
  appDb = createMemoryDb();
  await migrateDb(appDb);
  return appDb;
}

/**
 * Remet le singleton a zero.
 */
export function resetAppDbCache(): void {
  appDb = null;
}
