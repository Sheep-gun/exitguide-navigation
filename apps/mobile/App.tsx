import { AppErrorBoundary } from "./src/components/AppErrorBoundary";
import { HomeScreen } from "./src/screens/HomeScreen";

export default function App() {
  return (
    <AppErrorBoundary>
      <HomeScreen />
    </AppErrorBoundary>
  );
}
