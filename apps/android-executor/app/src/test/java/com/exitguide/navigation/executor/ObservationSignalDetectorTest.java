package com.exitguide.navigation.executor;

import static org.junit.Assert.assertEquals;

import org.junit.Test;

public final class ObservationSignalDetectorTest {
    @Test
    public void executorFailureWinsOverSemanticHeuristics() {
        assertEquals(
                "blocked",
                ObservationSignalDetector.detect("blocked", "app.a", "app.b", "네트워크 오류")
        );
    }

    @Test
    public void externalPackageIsSeparatedFromUiFailure() {
        assertEquals(
                "external_app",
                ObservationSignalDetector.detect("none", "app.a", "browser.b", "")
        );
    }

    @Test
    public void detectsLoginAndNetworkBoundaries() {
        assertEquals(
                "login_required",
                ObservationSignalDetector.detect("none", "app.a", "app.a", "계속하려면 로그인이 필요합니다")
        );
        assertEquals(
                "network_error",
                ObservationSignalDetector.detect("none", "app.a", "app.a", "네트워크 오류. 다시 시도")
        );
    }

    @Test
    public void biometricBoundaryWinsOverExternalPackageDetection() {
        assertEquals(
                "blocked",
                ObservationSignalDetector.detect(
                        "none",
                        "app.a",
                        "android.systemui",
                        "생체 인증 보안 지문을 입력하세요"
                )
        );
    }
}
