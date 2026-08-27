"use client";

import React from "react";

export type PageLoaderProps = {
  /** Message sous le spinner (optionnel). */
  label?: string;
  /** Mode plein ecran (overlay) ou inline dans le contenu. */
  variant?: "overlay" | "inline" | "page";
};

/**
 * Indicateur de chargement Material (spinner + libelle).
 * Utilise pour les transitions de pages et les Suspense boundaries.
 */
export function PageLoader({
  label = "Chargement…",
  variant = "page"
}: PageLoaderProps): React.ReactElement {
  return (
    <div
      className={`vg-page-loader vg-page-loader--${variant}`}
      role="status"
      aria-live="polite"
      aria-busy="true"
    >
      <span className="vg-page-loader-spinner" aria-hidden />
      <span className="vg-page-loader-label">{label}</span>
    </div>
  );
}
