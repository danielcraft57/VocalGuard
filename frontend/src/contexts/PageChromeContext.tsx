/**
 * Meta chrome de page (titre topbar / header) pour le shell persistant.
 */

"use client";

import React, {
  createContext,
  useCallback,
  useContext,
  useLayoutEffect,
  useMemo,
  useState
} from "react";

export type PageChromeMeta = {
  title: string;
  subtitle?: string;
  hidePageHeader?: boolean;
};

type PageChromeContextValue = {
  meta: PageChromeMeta;
  setMeta: (meta: PageChromeMeta) => void;
};

const DEFAULT_META: PageChromeMeta = {
  title: "VocalGuard",
  subtitle: undefined,
  hidePageHeader: false
};

const PageChromeContext = createContext<PageChromeContextValue | null>(null);

/**
 * Provider du chrome (utilise par AppShell).
 *
 * @param props children.
 */
export function PageChromeProvider({
  children
}: {
  children: React.ReactNode;
}): React.ReactElement {
  const [meta, setMetaState] = useState<PageChromeMeta>(DEFAULT_META);
  const setMeta = useCallback((next: PageChromeMeta) => {
    setMetaState((prev) => {
      if (
        prev.title === next.title &&
        prev.subtitle === next.subtitle &&
        Boolean(prev.hidePageHeader) === Boolean(next.hidePageHeader)
      ) {
        return prev;
      }
      return {
        title: next.title,
        subtitle: next.subtitle,
        hidePageHeader: Boolean(next.hidePageHeader)
      };
    });
  }, []);

  const value = useMemo(() => ({ meta, setMeta }), [meta, setMeta]);
  return (
    <PageChromeContext.Provider value={value}>{children}</PageChromeContext.Provider>
  );
}

/**
 * Met a jour le titre / sous-titre du shell (sans remonter Sidebar).
 *
 * @param meta Titre page.
 */
export function usePageChrome(meta: PageChromeMeta): void {
  const ctx = useContext(PageChromeContext);
  useLayoutEffect(() => {
    if (!ctx) return;
    ctx.setMeta(meta);
  }, [ctx, meta.title, meta.subtitle, meta.hidePageHeader]);
}

/**
 * Lit le meta courant (shell).
 *
 * @returns Meta.
 */
export function usePageChromeMeta(): PageChromeMeta {
  const ctx = useContext(PageChromeContext);
  return ctx?.meta ?? DEFAULT_META;
}
