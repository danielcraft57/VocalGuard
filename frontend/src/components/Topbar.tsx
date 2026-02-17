import React from "react";

export interface TopbarProps {
  /** Titre de la page courante. */
  title: string;
  /** Callback pour le bouton menu (mobile). */
  onMenuClick?: () => void;
}

/**
 * Bandeau superieur affichant le titre de la page et
 * un indicateur simple de statut de la ligne.
 */
export const Topbar: React.FC<TopbarProps> = ({ title, onMenuClick }) => {
  return (
    <header className="vg-topbar">
      <div style={{ display: "flex", alignItems: "center" }}>
        {onMenuClick ? (
          <button
            type="button"
            className="vg-topbar-menu-button"
            onClick={onMenuClick}
            aria-label="Ouvrir le menu"
          >
            <span className="material-icons">menu</span>
          </button>
        ) : null}
        <div className="vg-topbar-title">{title}</div>
      </div>
      <div className="vg-topbar-status">
        <span className="material-icons" style={{ fontSize: "16px", marginRight: "0.35rem", verticalAlign: "middle" }}>
          wifi_calling_3
        </span>
        Ligne DanielCraftFr: en service
      </div>
    </header>
  );
};

