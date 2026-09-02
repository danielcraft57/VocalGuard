/**
 * Invalidation session mobile (token expire / 401).
 */
import { clearCredentials } from "./credentials";
import { log } from "./log";

let invalidating = false;
let expiredHandler: (() => void) | null = null;
let cleanupHandler: (() => void) | null = null;

/**
 * Branche la redirection apres expiration (layout racine).
 */
export function setSessionExpiredHandler(fn: () => void): void {
  expiredHandler = fn;
}

/**
 * Branche le nettoyage runtime (WS, etc.) avant redirection.
 */
export function setSessionCleanupHandler(fn: () => void): void {
  cleanupHandler = fn;
}

/**
 * Efface credentials et notifie l UI.
 */
export async function invalidateMobileSession(reason: string): Promise<void> {
  if (invalidating) return;
  invalidating = true;
  try {
    log.warn("session", "invalidate", { reason });
    cleanupHandler?.();
    await clearCredentials();
    expiredHandler?.();
  } finally {
    setTimeout(() => {
      invalidating = false;
    }, 3000);
  }
}
