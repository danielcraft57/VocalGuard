import React, { useEffect } from "react";
import { Tabs, useRouter } from "expo-router";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import { colors } from "../../src/theme/colors";
import { icons } from "../../src/theme/icons";
import { bindNotificationResponses, startRealtime, stopRealtime } from "../../src/services/realtime";

/**
 * Tab bar principale : Appels, Messages, Composer, Reglages.
 */
export default function TabsLayout() {
  const router = useRouter();

  useEffect(() => {
    void startRealtime();
    const unbind = bindNotificationResponses(router);
    return () => {
      unbind();
      stopRealtime();
    };
  }, [router]);

  return (
    <Tabs
      screenOptions={{
        tabBarActiveTintColor: colors.primary,
        tabBarInactiveTintColor: colors.neutral400,
        tabBarStyle: { backgroundColor: colors.slateLight },
        headerStyle: { backgroundColor: colors.slate },
        headerTintColor: colors.text,
      }}
    >
      <Tabs.Screen
        name="calls"
        options={{
          title: "Appels",
          tabBarIcon: ({ color, size }) => (
            <MaterialCommunityIcons name={icons.tabCalls} color={color} size={size} />
          ),
        }}
      />
      <Tabs.Screen
        name="messages"
        options={{
          title: "Messages",
          tabBarIcon: ({ color, size }) => (
            <MaterialCommunityIcons name={icons.tabMessages} color={color} size={size} />
          ),
        }}
      />
      <Tabs.Screen
        name="dialer"
        options={{
          title: "Composer",
          tabBarIcon: ({ color, size }) => (
            <MaterialCommunityIcons name={icons.tabDialer} color={color} size={size} />
          ),
        }}
      />
      <Tabs.Screen
        name="settings"
        options={{
          title: "Reglages",
          tabBarIcon: ({ color, size }) => (
            <MaterialCommunityIcons name={icons.tabSettings} color={color} size={size} />
          ),
        }}
      />
    </Tabs>
  );
}
