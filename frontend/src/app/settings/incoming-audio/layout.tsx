import { PAGE_TITLES, pageMetadata } from "../../../lib/pageMetadata";

export const metadata = pageMetadata(
  PAGE_TITLES.settingsIncomingAudio.title,
  PAGE_TITLES.settingsIncomingAudio.description,
);

export default function IncomingAudioLayout({ children }: { children: React.ReactNode }) {
  return children;
}
