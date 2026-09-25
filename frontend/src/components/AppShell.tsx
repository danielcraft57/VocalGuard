/**
 * Shell persistant : Sidebar + Topbar survivent aux navigations.
 */

"use client";

import React, { useState } from "react";
import { usePathname } from "next/navigation";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";
import { IncomingCallModal } from "./IncomingCallModal";
import { useIncomingCallLive } from "../hooks/useIncomingCallLive";
import {
  PageChromeProvider,
  usePageChromeMeta
} from "../contexts/PageChromeContext";

/**
 * Contenu du shell (doit etre sous PageChromeProvider).
 *
 * @param props children page.
 */
function AppShellInner({
  children
}: {
  children: React.ReactNode;
}): React.ReactElement {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const { live, dismiss } = useIncomingCallLive();
  const meta = usePageChromeMeta();

  return (
    <div className="vg-layout">
      <Sidebar
        isOpen={sidebarOpen}
        onNavigate={() => setSidebarOpen(false)}
      />
      <div className="vg-main">
        <Topbar
          title={meta.title}
          onMenuClick={() => setSidebarOpen((v) => !v)}
        />
        <main className="vg-content">
          {!meta.hidePageHeader ? (
            <header className="vg-page-header">
              <h1 className="vg-page-title">{meta.title}</h1>
              {meta.subtitle ? (
                <p className="vg-page-subtitle">{meta.subtitle}</p>
              ) : null}
            </header>
          ) : null}
          {children}
        </main>
        <footer className="vg-footer">
          <span className="vg-footer-brand">VocalGuard</span>
          <span className="vg-footer-sep">·</span>
          <span className="vg-footer-copy">DanielCraftFr</span>
        </footer>
      </div>
      {sidebarOpen ? (
        <div
          className="vg-sidebar-backdrop"
          onClick={() => setSidebarOpen(false)}
        />
      ) : null}
      <IncomingCallModal live={live} onDismiss={dismiss} />
    </div>
  );
}

/**
 * Gate : login sans shell, reste de l'app avec shell persistant.
 *
 * @param props children.
 */
export function AppShellGate({
  children
}: {
  children: React.ReactNode;
}): React.ReactElement {
  const pathname = usePathname() || "";
  const bare = pathname === "/login" || pathname.startsWith("/login/");

  if (bare) {
    return <>{children}</>;
  }

  return (
    <PageChromeProvider>
      <AppShellInner>{children}</AppShellInner>
    </PageChromeProvider>
  );
}
