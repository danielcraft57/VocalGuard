import React, { useEffect, useRef } from "react";
import { Stack, useRouter, useSegments, type Href } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { resolveAuthRedirect } from "../src/services/authNav";
import { getStoredCredentials } from "../src/services/credentials";
import { log } from "../src/services/log";
import { colors } from "../src/theme/colors";

/** Re-export pour les ecrans onboarding (evite imports depuis _layout). */
export { saveCredentials } from "../src/services/credentials";

/**
 * Layout racine Expo Router avec garde onboarding.
 * Relit les credentials a chaque changement de route (apres appairage).
 */
export default function RootLayout() {
  const router = useRouter();
  const segments = useSegments();
  const guardRunning = useRef(false);

  useEffect(() => {
    if (guardRunning.current) return;
    guardRunning.current = true;

    let cancelled = false;
    void (async () => {
      try {
        const creds = await getStoredCredentials();
        if (cancelled) return;

        const first = segments[0] as string | undefined;
        const second = segments[1] as string | undefined;
        const onSuccess = first === "onboarding" && second === "success";
        const target = resolveAuthRedirect(creds.token, first);

        log.info("nav", "garde", {
          hasToken: Boolean(creds.token),
          first,
          second,
          target,
          onSuccess,
        });

        if (target && !onSuccess) {
          router.replace(target as Href);
        }
      } catch (err) {
        log.error("nav", "garde failed", err);
      } finally {
        guardRunning.current = false;
      }
    })();

    return () => {
      cancelled = true;
      guardRunning.current = false;
    };
  }, [segments, router]);

  return (
    <>
      <StatusBar style="light" />
      <Stack
        screenOptions={{
          headerStyle: { backgroundColor: colors.slate },
          headerTintColor: colors.text,
          contentStyle: { backgroundColor: colors.slate },
        }}
      />
    </>
  );
}
