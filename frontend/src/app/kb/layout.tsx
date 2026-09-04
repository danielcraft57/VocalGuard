import { PAGE_TITLES, pageMetadata } from "../../lib/pageMetadata";

export const metadata = pageMetadata(PAGE_TITLES.kb.title, PAGE_TITLES.kb.description);

export default function KbLayout({ children }: { children: React.ReactNode }) {
  return children;
}
