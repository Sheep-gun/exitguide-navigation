import { StyleSheet, Text, TextInput, TouchableOpacity, View } from "react-native";

import { providerDefaults, providerLabels, withProviderDefaults } from "../data/providers";
import { colors, radii } from "../styles/theme";
import type { AiProviderId, AiProviderSettings } from "../types";

type ProviderSettingsProps = {
  settings: AiProviderSettings;
  onChange: (settings: AiProviderSettings) => void;
};

const providerIds: AiProviderId[] = ["server", "google", "gpt", "exaone"];

export function ProviderSettings({ settings, onChange }: ProviderSettingsProps) {
  const externalProvider = settings.providerId !== "server";

  function updateProvider(providerId: AiProviderId) {
    onChange(withProviderDefaults({ providerId, apiKey: "", model: "", baseUrl: "" }));
  }

  function updateField(field: Exclude<keyof AiProviderSettings, "providerId">, value: string) {
    onChange({ ...settings, [field]: value });
  }

  return (
    <View style={styles.wrap}>
      <View style={styles.tabRow}>
        {providerIds.map((providerId) => {
          const active = providerId === settings.providerId;
          return (
            <TouchableOpacity
              accessibilityRole="button"
              accessibilityState={{ selected: active }}
              key={providerId}
              onPress={() => updateProvider(providerId)}
              style={[styles.tab, active && styles.activeTab]}
            >
              <Text style={[styles.tabText, active && styles.activeTabText]}>{providerLabels[providerId]}</Text>
            </TouchableOpacity>
          );
        })}
      </View>

      {externalProvider ? (
        <View style={styles.fieldStack}>
          <TextInput
            autoCapitalize="none"
            autoCorrect={false}
            onChangeText={(value) => updateField("apiKey", value)}
            placeholder="API key"
            secureTextEntry
            style={styles.input}
            value={settings.apiKey}
          />
          <TextInput
            autoCapitalize="none"
            autoCorrect={false}
            onChangeText={(value) => updateField("model", value)}
            placeholder={providerDefaults[settings.providerId].model}
            style={styles.input}
            value={settings.model}
          />
          <TextInput
            autoCapitalize="none"
            autoCorrect={false}
            inputMode="url"
            onChangeText={(value) => updateField("baseUrl", value)}
            placeholder={providerDefaults[settings.providerId].baseUrl}
            style={styles.input}
            value={settings.baseUrl}
          />
          <Text style={styles.helper}>이 설정은 이 기기에 저장되고 분석 요청에만 함께 전송됩니다.</Text>
        </View>
      ) : (
        <Text style={styles.helper}>서버의 `.env` 설정을 그대로 사용합니다. 폰에서는 LAN 또는 공개 API 주소가 필요합니다.</Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    gap: 10,
  },
  tabRow: {
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
    justifyContent: "center",
    minHeight: 38,
    paddingHorizontal: 6,
  },
  activeTab: {
    backgroundColor: colors.surface,
  },
  tabText: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "900",
    textAlign: "center",
  },
  activeTabText: {
    color: colors.ink,
  },
  fieldStack: {
    gap: 8,
  },
  input: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: radii.control,
    borderWidth: 1,
    color: colors.ink,
    fontSize: 14,
    paddingHorizontal: 12,
    paddingVertical: 11,
  },
  helper: {
    color: colors.muted,
    fontSize: 13,
    lineHeight: 18,
  },
});
