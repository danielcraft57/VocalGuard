import React from "react";

export interface TopbarProps {
  /** Titre de la page courante. */
  title: string;
}

/**
 * Bandeau superieur affichant le titre de la page et
 * un indicateur simple de statut de la ligne.
 */
export const Topbar: React.FC<TopbarProps> = ({ title }) => {
  return (
    <header className="vg-topbar">
      <div className="vg-topbar-title">{title}</div>
      <div className="vg-topbar-status">Ligne DanielCraftFr: en service</div>
    </header>
  );
};

