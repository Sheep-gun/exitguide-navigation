import { StyleSheet, Text, TouchableOpacity, View } from "react-native";

import { colors, radii } from "../styles/theme";

export type AppTab = "demo" | "screenshot" | "flow" | "history";

type SegmentedTabsProps = {
  activeTab: AppTab;
  onChange: (tab: AppTab) => void;
};

const tabs: Array<{ id: AppTab; label: string }> = [
  { id: "screenshot", label: "사진" },
  { id: "flow", label: "흐름" },
  { id: "history", label: "기록" },
  { id: "demo", label: "데모" },
];

export function SegmentedTabs({ activeTab, onChange }: SegmentedTabsProps) {
  return (
    <View style={styles.wrap}>
      {tabs.map((tab) => {
        const active = tab.id === activeTab;
        return (
          <TouchableOpacity
            accessibilityRole="button"
            accessibilityState={{ selected: active }}
            key={tab.id}
            onPress={() => onChange(tab.id)}
            style={[styles.tab, active && styles.activeTab]}
          >
            <Text style={[styles.label, active && styles.activeLabel]}>{tab.label}</Text>
          </TouchableOpacity>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    backgroundColor: "#E8ECF2",
    borderRadius: radii.control,
    flexDirection: "row",
    gap: 4,
    padding: 4,
  },
  tab: {
    alignItems: "center",
    borderRadius: 6,
    flex: 1,
    minHeight: 40,
    justifyContent: "center",
    paddingHorizontal: 8,
  },
  activeTab: {
    backgroundColor: colors.surface,
  },
  label: {
    color: colors.muted,
    fontSize: 13,
    fontWeight: "800",
    textAlign: "center",
  },
  activeLabel: {
    color: colors.ink,
  },
});
