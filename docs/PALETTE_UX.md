# Palette et UX/UI - VocalGuard

## Principes appliqués

- **Base verte** : le vert est la couleur principale (marque, CTA, succes). Une echelle 50-900 permet fonds legers (50-100), teinte principale (500), et etats actifs/hover (600-700).
- **Regle 60-30-10** : environ 60 % de neutres (fonds, texte), 30 % de surfaces (cartes), 10 % de couleur (boutons, accents, etats).
- **Harmonie** : bleu-cyan (accent) cote froid pour info et liens ; rouge (danger) pour erreur/suppression ; ambre (warning) pour avertissements. Pas de melange de teintes chaudes/froides incoherent.
- **Neutres froids (slate)** : gris avec une legere dominante bleue pour rester coherent avec le vert et le bleu-cyan, et eviter un rendu jaunatre.
- **Contraste** : variables `--vg-on-primary`, `--vg-on-danger`, etc. pour le texte sur fond colore (blanc sur vert/rouge) et respect du contraste WCAG.
- **Focus** : `--vg-focus-ring` base sur le primary pour les etats focus clavier (accessibilite).

## Variables principales

| Role | Variables |
|------|-----------|
| Primary (vert) | `--vg-primary-50` a `--vg-primary-900`, `--vg-on-primary` |
| Accent (bleu-cyan) | `--vg-accent-50` a `--vg-accent-900`, `--vg-on-accent` |
| Danger (rouge) | `--vg-danger-50` a `--vg-danger-900`, `--vg-on-danger` |
| Warning (ambre) | `--vg-warn-50` a `--vg-warn-900`, `--vg-on-warn` |
| Neutres | `--vg-neutral-50` a `--vg-neutral-900` |
| Semantiques | `--vg-color-primary`, `--vg-color-danger`, `--vg-color-text`, `--vg-color-text-muted`, etc. |

## Usage dans les composants

- Boutons principaux : `--vg-color-primary` + `--vg-on-primary` ; hover `--vg-color-primary-hover`.
- Erreurs / destructif : `--vg-color-danger` et `--vg-danger-100` pour fonds legers.
- Infos / liens secondaires : `--vg-color-accent` et `--vg-color-accent-soft`.
- Avertissements : `--vg-color-warn` et `--vg-color-warn-soft`.
- Texte : `--vg-color-text` (principal), `--vg-color-text-muted` (secondaire).

Fichier des variables : `frontend/src/styles/globals.css` (bloc `:root`).
