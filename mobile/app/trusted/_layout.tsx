import { Stack } from "expo-router";
import { colors } from "../../src/theme/colors";

/**
 * Stack navigation pour les ecrans personnes de confiance.
 */
export default function TrustedLayout() {
  return (
    <Stack
      screenOptions={{
        headerStyle: { backgroundColor: colors.slate },
        headerTintColor: colors.text,
        contentStyle: { backgroundColor: colors.slate },
      }}
    >
      <Stack.Screen name="index" options={{ title: "Personnes de confiance" }} />
      <Stack.Screen name="import" options={{ title: "Importer des contacts" }} />
    </Stack>
  );
}
