/**
 * Telechargement audio authentifie (natif file://, web blob:).
 */
import { Platform } from "react-native";
import { File, Paths } from "expo-file-system";
import type { ApiConfig } from "./api";

/**
 * Telecharge un WAV avec Bearer et retourne une URI jouable.
 *
 * @param config API mobile.
 * @param url URL complete.
 * @param cacheName Nom fichier cache (natif).
 * @returns URI file:// ou blob:.
 */
export async function downloadAuthAudio(
  config: ApiConfig,
  url: string,
  cacheName: string,
): Promise<string> {
  const response = await fetch(url, {
    headers: { Authorization: `Bearer ${config.token}` },
  });
  if (!response.ok) {
    throw new Error(`Telechargement audio echoue (${response.status})`);
  }
  const bytes = new Uint8Array(await response.arrayBuffer());

  if (Platform.OS === "web") {
    const blob = new Blob([bytes.buffer], { type: "audio/wav" });
    return URL.createObjectURL(blob);
  }

  const file = new File(Paths.cache, cacheName);
  const writer = file.writableStream().getWriter();
  await writer.write(bytes);
  await writer.close();
  const raw = (file as unknown as { uri: string }).uri;
  if (!raw) {
    throw new Error("Chemin audio local invalide");
  }
  return raw.startsWith("file://") ? raw : `file://${raw}`;
}
