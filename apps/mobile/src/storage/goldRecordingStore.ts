import AsyncStorage from "@react-native-async-storage/async-storage";

const GOLD_RECORDING_KEY = "exitguide.navigation.gold-recording.v1";

export type StoredGoldRecording = {
  apiBaseUrl: string;
  recordingId: string;
};

export async function loadGoldRecording(): Promise<StoredGoldRecording | null> {
  const raw = await AsyncStorage.getItem(GOLD_RECORDING_KEY);
  if (!raw) {
    return null;
  }
  try {
    const value = JSON.parse(raw) as Partial<StoredGoldRecording>;
    if (typeof value.apiBaseUrl === "string" && typeof value.recordingId === "string") {
      return { apiBaseUrl: value.apiBaseUrl, recordingId: value.recordingId };
    }
  } catch {
    // An invalid local pointer must never manufacture or promote Gold data.
  }
  await AsyncStorage.removeItem(GOLD_RECORDING_KEY);
  return null;
}

export async function saveGoldRecording(recording: StoredGoldRecording): Promise<void> {
  await AsyncStorage.setItem(GOLD_RECORDING_KEY, JSON.stringify(recording));
}

export async function clearGoldRecording(): Promise<void> {
  await AsyncStorage.removeItem(GOLD_RECORDING_KEY);
}
