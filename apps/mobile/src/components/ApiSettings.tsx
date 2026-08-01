import { StyleSheet, Text, TextInput, TouchableOpacity, View } from "react-native";

import { API_PORT, DEFAULT_API_BASE_URL, normalizeApiBaseUrl } from "../api/exitguideApi";
import { colors, radii } from "../styles/theme";

type ApiSettingsProps = {
  apiBaseUrl: string;
  onChange: (value: string) => void;
};

export function ApiSettings({ apiBaseUrl, onChange }: ApiSettingsProps) {
  function commitApiBaseUrl(value: string) {
    if (!value.trim()) {
      onChange("");
      return;
    }
    onChange(normalizeApiBaseUrl(value));
  }

  return (
    <View style={styles.wrap}>
      <TextInput
        autoCapitalize="none"
        autoCorrect={false}
        inputMode="url"
        onChangeText={onChange}
        onEndEditing={(event) => commitApiBaseUrl(event.nativeEvent.text)}
        placeholder={`http://<this-pc-ip>:${API_PORT}`}
        style={styles.input}
        value={apiBaseUrl}
      />
      <TouchableOpacity accessibilityRole="button" onPress={() => onChange(DEFAULT_API_BASE_URL)} style={styles.resetButton}>
        <Text style={styles.resetText}>감지된 주소로 되돌리기</Text>
      </TouchableOpacity>
      <Text style={styles.helper}>Expo 호스트 기준으로 자동 입력되고 이 기기에 저장됩니다. 노트북 IP가 바뀐 경우에만 수정하세요.</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    gap: 8,
  },
  input: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: radii.control,
    borderWidth: 1,
    color: colors.ink,
    fontSize: 15,
    paddingHorizontal: 14,
    paddingVertical: 12,
  },
  helper: {
    color: colors.muted,
    fontSize: 13,
    lineHeight: 18,
  },
  resetButton: {
    alignSelf: "flex-start",
    borderColor: colors.border,
    borderRadius: radii.pill,
    borderWidth: 1,
    paddingHorizontal: 10,
    paddingVertical: 7,
  },
  resetText: {
    color: colors.primary,
    fontSize: 12,
    fontWeight: "800",
  },
});
