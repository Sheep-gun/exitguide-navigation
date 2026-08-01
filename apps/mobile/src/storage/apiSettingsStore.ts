import AsyncStorage from "@react-native-async-storage/async-storage";

const API_BASE_URL_KEY = "exitguide.apiBaseUrl.v1";

export async function loadApiBaseUrl(): Promise<string | null> {
  const value = await AsyncStorage.getItem(API_BASE_URL_KEY);
  return value?.trim() || null;
}

export async function saveApiBaseUrl(apiBaseUrl: string): Promise<void> {
  await AsyncStorage.setItem(API_BASE_URL_KEY, apiBaseUrl.trim());
}
