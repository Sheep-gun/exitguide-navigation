import { Component, type ErrorInfo, type PropsWithChildren } from "react";
import { StyleSheet, Text, View } from "react-native";

import { colors, radii } from "../styles/theme";
import { ActionButton } from "./ActionButton";

type AppErrorBoundaryState = {
  errorMessage: string | null;
};

export class AppErrorBoundary extends Component<PropsWithChildren, AppErrorBoundaryState> {
  state: AppErrorBoundaryState = {
    errorMessage: null,
  };

  static getDerivedStateFromError(error: Error): AppErrorBoundaryState {
    return {
      errorMessage: error.message,
    };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.warn("ExitGuide UI error", error, errorInfo.componentStack);
  }

  render() {
    if (this.state.errorMessage) {
      return (
        <View style={styles.screen}>
          <View style={styles.card}>
            <Text style={styles.title}>Something needs a quick reset</Text>
            <Text style={styles.message}>{this.state.errorMessage}</Text>
            <ActionButton onPress={() => this.setState({ errorMessage: null })}>Try again</ActionButton>
          </View>
        </View>
      );
    }

    return this.props.children;
  }
}

const styles = StyleSheet.create({
  screen: {
    backgroundColor: colors.background,
    flex: 1,
    justifyContent: "center",
    padding: 20,
  },
  card: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: radii.card,
    borderWidth: 1,
    gap: 12,
    padding: 18,
  },
  title: {
    color: colors.ink,
    fontSize: 20,
    fontWeight: "800",
  },
  message: {
    color: colors.muted,
    fontSize: 14,
    lineHeight: 20,
  },
});
