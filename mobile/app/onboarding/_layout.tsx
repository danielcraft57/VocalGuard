import { Stack } from "expo-router";
import { colors } from "../../src/theme/colors";

/**
 * Stack navigation pour l appairage (accueil, scan, manuel, succes).
 * Requis pour qu Expo Router enregistre le groupe "onboarding".
 */
export default function OnboardingLayout() {
  return (
    <Stack
      screenOptions={{
        headerStyle: { backgroundColor: colors.slate },
        headerTintColor: colors.text,
        contentStyle: { backgroundColor: colors.slate },
      }}
    >
      <Stack.Screen name="index" options={{ title: "Appairage", headerShown: false }} />
      <Stack.Screen name="scan" options={{ title: "Scanner le QR" }} />
      <Stack.Screen name="manual" options={{ title: "Saisie manuelle" }} />
      <Stack.Screen name="success" options={{ title: "Connecte", headerShown: false }} />
    </Stack>
  );
}
