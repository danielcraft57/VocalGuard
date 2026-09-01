/**
 * Singleton SQLite natif (Android/iOS) via expo-sqlite.
 */
import * as SQLite from "expo-sqlite";
import { log } from "../services/log";
import { migrateDb, type SqlDb } from "./client";

const DB_NAME = "vocalguard.db";

let appDb: SqlDb | null = null;
let appDbPromise: Promise<SqlDb> | null = null;
let migrated = false;

/**
 * Indique si l erreur ressemble au NPE natif Android d expo-sqlite.
 *
 * @param err Erreur levee.
 * @returns True si NPE / handle mort.
 */
function isSqliteNativeNpe(err: unknown): boolean {
  const msg = err instanceof Error ? err.message : String(err);
  return msg.includes("NullPointerException") || msg.includes("NativeDatabase");
}

/**
 * Ouvre (ou reouvre) la base Expo avec une connexion neuve.
 *
 * @param forceNew Force useNewConnection (apres NPE).
 * @returns Handle SQLite.
 */
async function openExpoDb(forceNew: boolean): Promise<SqlDb> {
  const db = await SQLite.openDatabaseAsync(DB_NAME, {
    useNewConnection: forceNew,
  });
  return db as unknown as SqlDb;
}

/**
 * Retourne la base app (singleton). Evite les opens concurrents qui cassent Android.
 *
 * @returns DB prete (migree).
 */
export async function getAppDb(): Promise<SqlDb> {
  if (appDb && migrated) {
    log.debug("db", "reuse singleton");
    return appDb;
  }
  if (appDbPromise) {
    log.debug("db", "await open en cours");
    return appDbPromise;
  }

  log.info("db", "open + migrate (native)");
  appDbPromise = (async () => {
    let db = await openExpoDb(false);
    try {
      await migrateDb(db);
    } catch (err) {
      if (!isSqliteNativeNpe(err)) throw err;
      log.warn("db", "NPE natif, reopen useNewConnection", err);
      migrated = false;
      appDb = null;
      db = await openExpoDb(true);
      await migrateDb(db);
    }
    appDb = db;
    migrated = true;
    log.info("db", "ready");
    return db;
  })();

  try {
    return await appDbPromise;
  } catch (err) {
    appDbPromise = null;
    appDb = null;
    migrated = false;
    throw err;
  }
}

/**
 * Remet le singleton a zero (tests / reload).
 */
export function resetAppDbCache(): void {
  appDb = null;
  appDbPromise = null;
  migrated = false;
}
