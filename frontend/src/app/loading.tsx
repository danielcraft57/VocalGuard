import { PageLoader } from "../components/PageLoader";

/**
 * Affiche pendant le chargement / la navigation entre pages (App Router).
 */
export default function Loading() {
  return <PageLoader variant="page" label="Chargement de la page…" />;
}
