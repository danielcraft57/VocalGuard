/**
 * Notifications locales (MVP LAN-first, pas de push cloud).
 */

export interface LocalNotificationPayload {
  title: string;
  body: string;
  data?: Record<string, string>;
}

let scheduleImpl: ((payload: LocalNotificationPayload) => Promise<void>) | null = null;

/**
 * Injecte l implementation (expo-notifications en runtime, mock en test).
 *
 * @param fn Planificateur de notification.
 */
export function setLocalNotificationScheduler(
  fn: (payload: LocalNotificationPayload) => Promise<void>,
): void {
  scheduleImpl = fn;
}

/**
 * Declenche une notification locale immediate.
 *
 * @param payload Titre et corps.
 */
export async function scheduleLocalNotification(payload: LocalNotificationPayload): Promise<void> {
  if (scheduleImpl) {
    await scheduleImpl(payload);
    return;
  }
  /* Runtime sans expo : no-op silencieux */
}

/**
 * Mappe un evenement WS vers une notification utilisateur.
 *
 * @param type Type evenement backend.
 * @param payload Donnees evenement.
 */
export function notificationFromWsEvent(
  type: string,
  payload: Record<string, unknown>,
): LocalNotificationPayload | null {
  if (type === "call.incoming") {
    const phone = String(payload.phone_number ?? payload.caller_number ?? "inconnu");
    return { title: "Appel entrant", body: `Appel de ${phone}`, data: { type } };
  }
  if (type === "voicemail.recorded") {
    const phone = String(payload.phone_number ?? payload.caller_number ?? "inconnu");
    const vmId = payload.voicemail_id != null ? String(payload.voicemail_id) : undefined;
    return {
      title: "Nouveau message vocal",
      body: `Message de ${phone}`,
      data: { type, ...(vmId ? { voicemail_id: vmId } : {}) },
    };
  }
  if (type === "call.missed") {
    const phone = String(payload.phone_number ?? payload.caller_number ?? "inconnu");
    return { title: "Appel manque", body: `Appel de ${phone}`, data: { type } };
  }
  return null;
}
