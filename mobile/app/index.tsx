import { Redirect } from "expo-router";

/**
 * Entree racine : redirection immediate vers onboarding (garde layout prend le relais).
 */
export default function Index() {
  return <Redirect href="/onboarding" />;
}
