/**
 * Detection entrant / sortant pour la liste appels mobile.
 */

export type CallDirection = "in" | "out";

/**
 * Detecte si l appel est entrant ou sortant (heuristique alignee web).
 *
 * @param call Champs utiles (caller_name, audio_file, extra_data).
 * @returns "in" ou "out".
 */
export function getCallDirection(call: {
  caller_name?: string | null;
  audio_file?: string | null;
  extra_data?: Record<string, unknown> | null;
}): CallDirection {
  const name = (call.caller_name || "").trim().toLowerCase();
  if (name === "sortant") return "out";
  const audio = (call.audio_file || "").toLowerCase();
  if (audio.includes("call_out_") || audio.includes("/call_out")) return "out";
  const ex = call.extra_data;
  if (ex && typeof ex === "object") {
    const dir = String((ex as { direction?: string }).direction || "").toLowerCase();
    if (dir === "out" || dir === "outgoing" || dir === "sortant") return "out";
    if (dir === "in" || dir === "incoming" || dir === "entrant") return "in";
  }
  return "in";
}
