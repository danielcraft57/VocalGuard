/**
 * Logger simple pour le debug mobile (Metro / Logcat).
 * Prefixe [VG] pour filtrer facilement.
 */

type LogLevel = "debug" | "info" | "warn" | "error";

const PREFIX = "[VG]";

/**
 * Formate et envoie une ligne de log.
 *
 * @param level Niveau.
 * @param scope Module (ex. calls, sync, db).
 * @param message Message court.
 * @param data Payload optionnel.
 */
function write(level: LogLevel, scope: string, message: string, data?: unknown): void {
  const stamp = new Date().toISOString().slice(11, 23);
  const line = `${PREFIX} ${stamp} ${scope} ${message}`;
  if (data !== undefined) {
    if (level === "error") console.error(line, data);
    else if (level === "warn") console.warn(line, data);
    else console.log(line, data);
    return;
  }
  if (level === "error") console.error(line);
  else if (level === "warn") console.warn(line);
  else console.log(line);
}

/**
 * API de log VocalGuard mobile.
 */
export const log = {
  /**
   * @param scope Module.
   * @param message Message.
   * @param data Donnees optionnelles.
   */
  debug(scope: string, message: string, data?: unknown): void {
    write("debug", scope, message, data);
  },
  /**
   * @param scope Module.
   * @param message Message.
   * @param data Donnees optionnelles.
   */
  info(scope: string, message: string, data?: unknown): void {
    write("info", scope, message, data);
  },
  /**
   * @param scope Module.
   * @param message Message.
   * @param data Donnees optionnelles.
   */
  warn(scope: string, message: string, data?: unknown): void {
    write("warn", scope, message, data);
  },
  /**
   * @param scope Module.
   * @param message Message.
   * @param data Donnees optionnelles.
   */
  error(scope: string, message: string, data?: unknown): void {
    write("error", scope, message, data);
  },
};
