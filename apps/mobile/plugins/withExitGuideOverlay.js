const fs = require("fs");
const path = require("path");
const {
  AndroidConfig,
  withAndroidManifest,
  withAppBuildGradle,
  withDangerousMod,
  withMainApplication,
} = require("@expo/config-plugins");

const OVERLAY_PACKAGE = "com.exitguide.ai.overlay";
const OVERLAY_PACKAGE_IMPORT = `${OVERLAY_PACKAGE}.ExitGuideOverlayPackage`;

function withExitGuideOverlay(config) {
  config = withAndroidManifest(config, (pluginConfig) => {
    const manifest = pluginConfig.modResults.manifest;
    addPermission(manifest, "android.permission.INTERNET");
    addPermission(manifest, "android.permission.SYSTEM_ALERT_WINDOW");
    addPermission(manifest, "android.permission.FOREGROUND_SERVICE");
    addPermission(manifest, "android.permission.FOREGROUND_SERVICE_SPECIAL_USE");
    addPermission(manifest, "android.permission.FOREGROUND_SERVICE_MEDIA_PROJECTION");
    addPermission(manifest, "android.permission.POST_NOTIFICATIONS");
    // The accessibility service navigates apps outside ExitGuide. Android
    // 11+ hides arbitrary packages from PackageManager unless this sideloaded
    // build declares package visibility, which would otherwise erase the app
    // version and defeat version-scoped route safety.
    addPermission(manifest, "android.permission.QUERY_ALL_PACKAGES");

    const mainApplication = AndroidConfig.Manifest.getMainApplicationOrThrow(pluginConfig.modResults);
    // Accessibility trees can contain sensitive on-screen text. Keep release
    // traffic encrypted except for explicit loopback development tunnels.
    mainApplication.$["android:usesCleartextTraffic"] = "false";
    mainApplication.$["android:networkSecurityConfig"] = "@xml/exitguide_network_security_config";
    mainApplication.service = mainApplication.service || [];
    upsertManifestEntry(mainApplication.service, {
      $: {
        "android:name": ".overlay.ExitGuideOverlayService",
        "android:exported": "false",
        "android:foregroundServiceType": "specialUse|mediaProjection",
      },
      property: [
        {
          $: {
            "android:name": "android.app.PROPERTY_SPECIAL_USE_FGS_SUBTYPE",
            "android:value": "User-initiated persistent floating navigation guidance across Android apps",
          },
        },
      ],
    });
    upsertManifestEntry(mainApplication.service, {
      $: {
        "android:name": ".overlay.ExitGuideAccessibilityService",
        "android:permission": "android.permission.BIND_ACCESSIBILITY_SERVICE",
        "android:exported": "true",
        "android:label": "ExitGuide Navigation",
      },
      "intent-filter": [
        {
          action: [
            { $: { "android:name": "android.accessibilityservice.AccessibilityService" } },
          ],
        },
      ],
      "meta-data": [
        {
          $: {
            "android:name": "android.accessibilityservice",
            "android:resource": "@xml/exitguide_accessibility_service",
          },
        },
      ],
    });

    mainApplication.activity = mainApplication.activity || [];
    upsertManifestEntry(mainApplication.activity, {
      $: {
        "android:name": ".overlay.ExitGuideCaptureActivity",
        "android:exported": "false",
        "android:theme": "@android:style/Theme.Translucent.NoTitleBar",
      },
    });

    return pluginConfig;
  });

  config = withMainApplication(config, (pluginConfig) => {
    let contents = pluginConfig.modResults.contents;
    const language = pluginConfig.modResults.language;

    if (!contents.includes(OVERLAY_PACKAGE_IMPORT)) {
      contents = contents.replace(/(package\s+[^\n]+\n)/, `$1\nimport ${OVERLAY_PACKAGE_IMPORT}${language === "kt" ? "" : ";"}\n`);
    }

    if (!contents.includes("ExitGuideOverlayPackage()") && !contents.includes("new ExitGuideOverlayPackage()")) {
      if (language === "kt") {
        if (contents.includes("PackageList(this).packages.apply {")) {
          contents = contents.replace(
            /(PackageList\(this\)\.packages\.apply \{\n)/,
            "$1              add(ExitGuideOverlayPackage())\n",
          );
        } else {
          contents = contents.replace(
            /(\s*)return packages/,
            "$1packages.add(ExitGuideOverlayPackage())\n$1return packages",
          );
        }
      } else {
        contents = contents.replace(
          /(\s*)return packages;/,
          "$1packages.add(new ExitGuideOverlayPackage());\n$1return packages;",
        );
      }
    }

    pluginConfig.modResults.contents = contents;
    return pluginConfig;
  });

  config = withAppBuildGradle(config, (pluginConfig) => {
    const dependency = 'implementation "com.google.mlkit:text-recognition-korean:16.0.1"';
    if (!pluginConfig.modResults.contents.includes("com.google.mlkit:text-recognition-korean")) {
      pluginConfig.modResults.contents = pluginConfig.modResults.contents.replace(
        /dependencies\s*\{/,
        `dependencies {\n    ${dependency}`,
      );
    }
    return pluginConfig;
  });

  return withDangerousMod(config, [
    "android",
    (pluginConfig) => {
      const javaRoot = path.join(pluginConfig.modRequest.platformProjectRoot, "app/src/main/java/com/exitguide/ai/overlay");
      const xmlRoot = path.join(pluginConfig.modRequest.platformProjectRoot, "app/src/main/res/xml");
      fs.mkdirSync(javaRoot, { recursive: true });
      fs.mkdirSync(xmlRoot, { recursive: true });
      fs.writeFileSync(path.join(javaRoot, "ExitGuideOverlayPackage.java"), overlayPackageSource());
      fs.writeFileSync(path.join(javaRoot, "ExitGuideOverlayModule.java"), overlayModuleSource());
      fs.writeFileSync(path.join(javaRoot, "ExitGuideCaptureActivity.java"), captureActivitySource());
      fs.writeFileSync(path.join(javaRoot, "ExitGuideOverlayService.java"), overlayServiceSource());
      fs.writeFileSync(path.join(javaRoot, "ExitGuideAccessibilityService.java"), accessibilityServiceSource());
      fs.writeFileSync(path.join(xmlRoot, "exitguide_accessibility_service.xml"), accessibilityServiceConfigSource());
      fs.writeFileSync(path.join(xmlRoot, "exitguide_network_security_config.xml"), networkSecurityConfigSource());
      return pluginConfig;
    },
  ]);
}

function addPermission(manifest, permissionName) {
  manifest["uses-permission"] = manifest["uses-permission"] || [];
  if (!manifest["uses-permission"].some((item) => item.$["android:name"] === permissionName)) {
    manifest["uses-permission"].push({ $: { "android:name": permissionName } });
  }
}

function upsertManifestEntry(entries, entry) {
  const name = entry.$["android:name"];
  const existingIndex = entries.findIndex((item) => item.$["android:name"] === name);
  if (existingIndex >= 0) {
    entries[existingIndex] = entry;
    return;
  }
  entries.push(entry);
}

function overlayPackageSource() {
  return `package ${OVERLAY_PACKAGE};

import com.facebook.react.ReactPackage;
import com.facebook.react.bridge.NativeModule;
import com.facebook.react.bridge.ReactApplicationContext;
import com.facebook.react.uimanager.ViewManager;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class ExitGuideOverlayPackage implements ReactPackage {
  @Override
  public List<NativeModule> createNativeModules(ReactApplicationContext reactContext) {
    List<NativeModule> modules = new ArrayList<>();
    modules.add(new ExitGuideOverlayModule(reactContext));
    return modules;
  }

  @Override
  public List<ViewManager> createViewManagers(ReactApplicationContext reactContext) {
    return Collections.emptyList();
  }
}
`;
}

function overlayModuleSource() {
  return `package ${OVERLAY_PACKAGE};

import android.app.AppOpsManager;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ResolveInfo;
import android.accessibilityservice.AccessibilityServiceInfo;
import android.net.Uri;
import android.os.Build;
import android.provider.Settings;
import android.text.TextUtils;
import android.util.Log;
import android.view.accessibility.AccessibilityManager;
import com.facebook.react.bridge.Promise;
import com.facebook.react.bridge.ReactApplicationContext;
import com.facebook.react.bridge.ReactContextBaseJavaModule;
import com.facebook.react.bridge.ReactMethod;
import java.util.List;

public class ExitGuideOverlayModule extends ReactContextBaseJavaModule {
  private final ReactApplicationContext reactContext;

  public ExitGuideOverlayModule(ReactApplicationContext reactContext) {
    super(reactContext);
    this.reactContext = reactContext;
  }

  @Override
  public String getName() {
    return "ExitGuideOverlay";
  }

  @ReactMethod
  public void canDrawOverlays(Promise promise) {
    boolean allowed = canDrawOverlays(reactContext);
    Log.i("ExitGuideOverlay", "canDrawOverlays=" + allowed);
    promise.resolve(allowed);
  }

  @ReactMethod
  public void openOverlaySettings(Promise promise) {
    Intent intent = new Intent(
      Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
      Uri.parse("package:" + reactContext.getPackageName())
    );
    intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
    reactContext.startActivity(intent);
    promise.resolve(true);
  }

  @ReactMethod
  public void isAccessibilityEnabled(Promise promise) {
    ComponentName expectedComponent = new ComponentName(
      reactContext,
      ExitGuideAccessibilityService.class
    );
    AccessibilityManager manager =
      (AccessibilityManager) reactContext.getSystemService(Context.ACCESSIBILITY_SERVICE);
    if (manager != null) {
      List<AccessibilityServiceInfo> enabled = manager.getEnabledAccessibilityServiceList(
        AccessibilityServiceInfo.FEEDBACK_ALL_MASK
      );
      for (AccessibilityServiceInfo info : enabled) {
        ResolveInfo resolved = info.getResolveInfo();
        if (resolved == null || resolved.serviceInfo == null) {
          continue;
        }
        String packageName = resolved.serviceInfo.packageName;
        String serviceName = resolved.serviceInfo.name;
        if (serviceName != null && serviceName.startsWith(".")) {
          serviceName = packageName + serviceName;
        }
        if (expectedComponent.getPackageName().equals(packageName)
            && expectedComponent.getClassName().equals(serviceName)) {
          promise.resolve(true);
          return;
        }
      }
    }

    String configuredServices = Settings.Secure.getString(
      reactContext.getContentResolver(),
      Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES
    );
    if (!TextUtils.isEmpty(configuredServices)) {
      String fullComponent = expectedComponent.flattenToString();
      String shortComponent = expectedComponent.flattenToShortString();
      if (configuredServices.contains(fullComponent)
          || configuredServices.contains(shortComponent)
          || (configuredServices.contains(expectedComponent.getPackageName())
              && configuredServices.contains("ExitGuideAccessibilityService"))) {
        Log.i("ExitGuideOverlay", "accessibility enabled via secure settings");
        promise.resolve(true);
        return;
      }
      TextUtils.SimpleStringSplitter splitter = new TextUtils.SimpleStringSplitter(':');
      splitter.setString(configuredServices);
      while (splitter.hasNext()) {
        ComponentName configured = ComponentName.unflattenFromString(splitter.next());
        if (expectedComponent.equals(configured)) {
          promise.resolve(true);
          return;
        }
      }
    }
    Log.i("ExitGuideOverlay", "accessibility disabled; configured=" + configuredServices);
    promise.resolve(false);
  }

  @ReactMethod
  public void openAccessibilitySettings(Promise promise) {
    Intent intent = new Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS);
    intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
    reactContext.startActivity(intent);
    promise.resolve(true);
  }

  @ReactMethod
  public void startOverlay(
    String apiBaseUrl,
    String goalText,
    String operationMode,
    String providerId,
    String providerApiKey,
    String providerModel,
    String providerBaseUrl,
    Promise promise
  ) {
    Log.i(
      "ExitGuideOverlay",
      "startOverlay requested hasApiBaseUrl=" + (apiBaseUrl != null && apiBaseUrl.trim().length() > 0)
        + " hasGoal=" + (goalText != null && goalText.trim().length() > 0)
    );
    if (!canDrawOverlays(reactContext)) {
      promise.reject("overlay_permission_required", "화면 위 아이콘 권한이 필요합니다.");
      return;
    }

    Intent intent = new Intent(reactContext, ExitGuideOverlayService.class);
    intent.setAction(ExitGuideOverlayService.ACTION_START);
    intent.putExtra(ExitGuideOverlayService.EXTRA_API_BASE_URL, apiBaseUrl);
    intent.putExtra(ExitGuideOverlayService.EXTRA_GOAL_TEXT, goalText);
    intent.putExtra(ExitGuideOverlayService.EXTRA_OPERATION_MODE, operationMode);
    intent.putExtra(ExitGuideOverlayService.EXTRA_PROVIDER_ID, providerId);
    intent.putExtra(ExitGuideOverlayService.EXTRA_PROVIDER_API_KEY, providerApiKey);
    intent.putExtra(ExitGuideOverlayService.EXTRA_PROVIDER_MODEL, providerModel);
    intent.putExtra(ExitGuideOverlayService.EXTRA_PROVIDER_BASE_URL, providerBaseUrl);
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
      reactContext.startForegroundService(intent);
    } else {
      reactContext.startService(intent);
    }
    promise.resolve(true);
  }

  @ReactMethod
  public void stopOverlay(Promise promise) {
    Log.i("ExitGuideOverlay", "stopOverlay requested");
    Intent intent = new Intent(reactContext, ExitGuideOverlayService.class);
    intent.setAction(ExitGuideOverlayService.ACTION_STOP);
    reactContext.startService(intent);
    promise.resolve(true);
  }

  @ReactMethod
  public void clearOverlayStatus(Promise promise) {
    Log.i("ExitGuideOverlay", "clearOverlayStatus requested");
    reactContext
      .getSharedPreferences("exitguide_overlay", Context.MODE_PRIVATE)
      .edit()
      .remove("goalText")
      .remove("startNonce")
      .putBoolean("explorationActive", false)
      .apply();
    Intent intent = new Intent(reactContext, ExitGuideOverlayService.class);
    reactContext.stopService(intent);
    promise.resolve(true);
  }

  private static boolean canDrawOverlays(Context context) {
    if (Build.VERSION.SDK_INT < Build.VERSION_CODES.M || Settings.canDrawOverlays(context)) {
      return true;
    }
    AppOpsManager appOps = (AppOpsManager) context.getSystemService(Context.APP_OPS_SERVICE);
    if (appOps == null) {
      return false;
    }
    int mode;
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
      mode = appOps.unsafeCheckOpNoThrow(
        AppOpsManager.OPSTR_SYSTEM_ALERT_WINDOW,
        context.getApplicationInfo().uid,
        context.getPackageName()
      );
    } else {
      mode = appOps.checkOpNoThrow(
        AppOpsManager.OPSTR_SYSTEM_ALERT_WINDOW,
        context.getApplicationInfo().uid,
        context.getPackageName()
      );
    }
    boolean allowed = mode == AppOpsManager.MODE_ALLOWED;
    Log.i("ExitGuideOverlay", "overlay app-op mode=" + mode + ", allowed=" + allowed);
    return allowed;
  }
}
`;
}

function captureActivitySource() {
  return `package ${OVERLAY_PACKAGE};

import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.media.projection.MediaProjectionManager;
import android.os.Build;
import android.os.Bundle;

public class ExitGuideCaptureActivity extends Activity {
  private static final int REQUEST_CAPTURE = 7001;

  @Override
  protected void onCreate(Bundle savedInstanceState) {
    super.onCreate(savedInstanceState);
    MediaProjectionManager manager = (MediaProjectionManager) getSystemService(Context.MEDIA_PROJECTION_SERVICE);
    startActivityForResult(manager.createScreenCaptureIntent(), REQUEST_CAPTURE);
  }

  @Override
  protected void onActivityResult(int requestCode, int resultCode, Intent data) {
    super.onActivityResult(requestCode, resultCode, data);
    if (requestCode == REQUEST_CAPTURE && resultCode == RESULT_OK && data != null) {
      Intent intent = new Intent(this, ExitGuideOverlayService.class);
      intent.setAction(ExitGuideOverlayService.ACTION_CAPTURE_RESULT);
      intent.putExtra(ExitGuideOverlayService.EXTRA_RESULT_CODE, resultCode);
      intent.putExtra(ExitGuideOverlayService.EXTRA_RESULT_DATA, data);
      if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
        startForegroundService(intent);
      } else {
        startService(intent);
      }
    }
    finish();
  }
}
`;
}

function overlayServiceSource() {
  return `package ${OVERLAY_PACKAGE};

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.animation.ValueAnimator;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.SharedPreferences;
import android.content.pm.ServiceInfo;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.PixelFormat;
import android.graphics.Rect;
import android.graphics.drawable.Drawable;
import android.graphics.drawable.GradientDrawable;
import android.hardware.display.DisplayManager;
import android.hardware.display.VirtualDisplay;
import android.media.Image;
import android.media.ImageReader;
import android.media.projection.MediaProjection;
import android.media.projection.MediaProjectionManager;
import android.os.Build;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.IBinder;
import android.os.Looper;
import android.os.SystemClock;
import android.text.TextUtils;
import android.util.DisplayMetrics;
import android.util.Log;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.view.WindowManager;
import android.view.animation.LinearInterpolator;
import android.widget.TextView;
import android.widget.Toast;
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.ByteBuffer;

public class ExitGuideOverlayService extends Service {
  private static final long SPINNER_ROTATION_PERIOD_MS = 1800L;

  /** Twelve-spoke loader matching the supplied reference image. */
  private static final class SpinnerTextView extends TextView {
    private final Paint spinnerPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private boolean spinnerMode = true;
    private float spinnerRotation = 0f;

    SpinnerTextView(Context context) {
      super(context);
      setWillNotDraw(false);
      spinnerPaint.setStyle(Paint.Style.STROKE);
      spinnerPaint.setStrokeCap(Paint.Cap.ROUND);
    }

    void setSpinnerMode(boolean enabled) {
      spinnerMode = enabled;
      invalidate();
    }

    public void setSpinnerRotation(float rotation) {
      spinnerRotation = rotation;
      invalidate();
    }

    @Override
    protected void onDraw(Canvas canvas) {
      if (!spinnerMode) {
        super.onDraw(canvas);
        return;
      }
      float centerX = getWidth() / 2f;
      float centerY = getHeight() / 2f;
      float size = Math.min(getWidth(), getHeight());
      float innerRadius = size * 0.22f;
      float outerRadius = size * 0.39f;
      spinnerPaint.setStrokeWidth(Math.max(3f, size * 0.095f));
      canvas.save();
      canvas.rotate(spinnerRotation, centerX, centerY);
      for (int index = 0; index < 12; index += 1) {
        float radians = (float) Math.toRadians(-90 + index * 30);
        int brightness = Math.max(28, 245 - index * 19);
        spinnerPaint.setColor(Color.rgb(brightness, brightness, brightness));
        float startX = centerX + (float) Math.cos(radians) * innerRadius;
        float startY = centerY + (float) Math.sin(radians) * innerRadius;
        float endX = centerX + (float) Math.cos(radians) * outerRadius;
        float endY = centerY + (float) Math.sin(radians) * outerRadius;
        canvas.drawLine(startX, startY, endX, endY, spinnerPaint);
      }
      canvas.restore();
    }
  }

  private static final class SpinnerDrawable extends Drawable {
    private final Paint backgroundPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint spokePaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private float spinnerRotation = 0f;

    SpinnerDrawable() {
      backgroundPaint.setColor(Color.rgb(16, 16, 16));
      backgroundPaint.setStyle(Paint.Style.FILL);
      spokePaint.setStyle(Paint.Style.STROKE);
      spokePaint.setStrokeCap(Paint.Cap.ROUND);
    }

    public void setSpinnerRotation(float rotation) {
      spinnerRotation = rotation;
      invalidateSelf();
    }

    @Override
    public void draw(Canvas canvas) {
      Rect bounds = getBounds();
      float centerX = bounds.exactCenterX();
      float centerY = bounds.exactCenterY();
      float size = Math.min(bounds.width(), bounds.height());
      canvas.drawCircle(centerX, centerY, size * 0.5f, backgroundPaint);
      float innerRadius = size * 0.22f;
      float outerRadius = size * 0.39f;
      spokePaint.setStrokeWidth(Math.max(3f, size * 0.095f));
      float phase = (((spinnerRotation % 360f) + 360f) % 360f) / 30f;
      for (int index = 0; index < 12; index += 1) {
        float radians = (float) Math.toRadians(-90 + index * 30);
        float distance = Math.abs(index - phase);
        distance = Math.min(distance, 12f - distance);
        double pulse = (Math.cos(distance * Math.PI / 6d) + 1d) / 2d;
        int brightness = 28 + (int) Math.round(217d * Math.pow(pulse, 3.2d));
        spokePaint.setColor(Color.rgb(brightness, brightness, brightness));
        float startX = centerX + (float) Math.cos(radians) * innerRadius;
        float startY = centerY + (float) Math.sin(radians) * innerRadius;
        float endX = centerX + (float) Math.cos(radians) * outerRadius;
        float endY = centerY + (float) Math.sin(radians) * outerRadius;
        canvas.drawLine(startX, startY, endX, endY, spokePaint);
      }
    }

    @Override
    public void setAlpha(int alpha) {
      backgroundPaint.setAlpha(alpha);
      spokePaint.setAlpha(alpha);
      invalidateSelf();
    }

    @Override
    public void setColorFilter(android.graphics.ColorFilter colorFilter) {
      backgroundPaint.setColorFilter(colorFilter);
      spokePaint.setColorFilter(colorFilter);
      invalidateSelf();
    }

    @Override
    public int getOpacity() {
      return PixelFormat.TRANSLUCENT;
    }
  }

  public static final String ACTION_START = "com.exitguide.ai.overlay.START";
  public static final String ACTION_STOP = "com.exitguide.ai.overlay.STOP";
  public static final String ACTION_CAPTURE_RESULT = "com.exitguide.ai.overlay.CAPTURE_RESULT";
  public static final String FINISH_REASON_DESTINATION_REACHED = "destination_reached";
  public static final String FINISH_REASON_STOPPED_NOT_FOUND = "stopped_not_found";
  public static final String EXTRA_API_BASE_URL = "apiBaseUrl";
  public static final String EXTRA_GOAL_TEXT = "goalText";
  public static final String EXTRA_OPERATION_MODE = "operationMode";
  public static final String EXTRA_PROVIDER_ID = "providerId";
  public static final String EXTRA_PROVIDER_API_KEY = "providerApiKey";
  public static final String EXTRA_PROVIDER_MODEL = "providerModel";
  public static final String EXTRA_PROVIDER_BASE_URL = "providerBaseUrl";
  public static final String EXTRA_RESULT_CODE = "resultCode";
  public static final String EXTRA_RESULT_DATA = "resultData";

  private static final String CHANNEL_ID = "exitguide_overlay";
  private static final int NOTIFICATION_ID = 8410;
  private static final String PREFS_NAME = "exitguide_overlay";
  private static final String PREF_API_BASE_URL = "apiBaseUrl";
  private static final String PREF_GOAL_TEXT = "goalText";
  private static final String PREF_OPERATION_MODE = "operationMode";
  private static final String PREF_START_NONCE = "startNonce";
  private static final String PREF_EXPLORATION_ACTIVE = "explorationActive";
  private static final String PREF_PROVIDER_ID = "providerId";
  private static final String PREF_PROVIDER_API_KEY = "providerApiKey";
  private static final String PREF_PROVIDER_MODEL = "providerModel";
  private static final String PREF_PROVIDER_BASE_URL = "providerBaseUrl";

  private WindowManager windowManager;
  private SpinnerTextView bubbleView;
  private WindowManager.LayoutParams bubbleParams;
  private TextView readyMessageView;
  private WindowManager.LayoutParams readyMessageParams;
  private SpinnerDrawable spinnerDrawable;
  private ValueAnimator indicatorAnimator;
  private long spinnerAnimationStartedAtMs = 0L;
  private Handler mainHandler;
  private HandlerThread captureThread;
  private String apiBaseUrl = "";
  private String goalText = "";
  private String operationMode = "explore";
  private String startNonce = "";
  private String providerId = "server";
  private String providerApiKey = "";
  private String providerModel = "";
  private String providerBaseUrl = "";
  private boolean navigationActive = false;
  private boolean awaitingUserStart = true;
  private long lastStartAt = 0L;
  private final BroadcastReceiver guidanceReceiver = new BroadcastReceiver() {
    @Override
    public void onReceive(Context context, Intent intent) {
      if (!ExitGuideAccessibilityService.ACTION_GUIDANCE.equals(intent.getAction())) {
        return;
      }
      String message = intent.getStringExtra(ExitGuideAccessibilityService.EXTRA_GUIDANCE);
      boolean exploring = intent.getBooleanExtra(ExitGuideAccessibilityService.EXTRA_EXPLORING, false);
      boolean finished = intent.getBooleanExtra(ExitGuideAccessibilityService.EXTRA_FINISHED, false);
      if (finished) {
        String finishReason = intent.getStringExtra(ExitGuideAccessibilityService.EXTRA_FINISH_REASON);
        finishNavigation(
          message == null ? "" : message.trim(),
          finishReason == null ? "" : finishReason.trim()
        );
        return;
      }
      updateIndicator(exploring, message == null ? "" : message.trim());
    }
  };

  @Override
  public void onCreate() {
    super.onCreate();
    windowManager = (WindowManager) getSystemService(WINDOW_SERVICE);
    mainHandler = new Handler(Looper.getMainLooper());
    restorePrefs();
    createNotificationChannel();
    IntentFilter guidanceFilter = new IntentFilter(ExitGuideAccessibilityService.ACTION_GUIDANCE);
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
      registerReceiver(guidanceReceiver, guidanceFilter, Context.RECEIVER_NOT_EXPORTED);
    } else {
      registerReceiver(guidanceReceiver, guidanceFilter);
    }
  }

  @Override
  public int onStartCommand(Intent intent, int flags, int startId) {
    String action = intent != null ? intent.getAction() : null;
    if (ACTION_STOP.equals(action)) {
      long elapsedSinceStart = System.currentTimeMillis() - lastStartAt;
      if (lastStartAt > 0L && elapsedSinceStart < 1500L) {
        Log.w("ExitGuideOverlay", "ignored stop received during start guard window");
        return START_STICKY;
      }
      Log.i("ExitGuideOverlay", "stopping overlay by explicit request");
      navigationActive = false;
      awaitingUserStart = false;
      savePrefs();
      removeBubble();
      stopForeground(true);
      stopSelf();
      return START_NOT_STICKY;
    }

    if (ACTION_CAPTURE_RESULT.equals(action)) {
      // MediaProjection may only be added after the user grants the capture
      // consent returned by createScreenCaptureIntent(). The normal overlay
      // path deliberately starts only as specialUse.
      startCaptureForeground();
      int resultCode = intent.getIntExtra(EXTRA_RESULT_CODE, 0);
      Intent resultData = intent.getParcelableExtra(EXTRA_RESULT_DATA);
      if (resultCode != 0 && resultData != null) {
        captureAndAnalyze(resultCode, resultData);
      }
      return START_STICKY;
    }

    startOverlayForeground();
    lastStartAt = System.currentTimeMillis();
    Log.i("ExitGuideOverlay", "starting overlay service");

    if (intent != null && ACTION_START.equals(action)) {
      apiBaseUrl = intent.getStringExtra(EXTRA_API_BASE_URL) != null ? intent.getStringExtra(EXTRA_API_BASE_URL) : apiBaseUrl;
      goalText = intent.getStringExtra(EXTRA_GOAL_TEXT) != null ? intent.getStringExtra(EXTRA_GOAL_TEXT) : goalText;
      operationMode = intent.getStringExtra(EXTRA_OPERATION_MODE) != null
        ? intent.getStringExtra(EXTRA_OPERATION_MODE) : operationMode;
      providerId = intent.getStringExtra(EXTRA_PROVIDER_ID) != null ? intent.getStringExtra(EXTRA_PROVIDER_ID) : providerId;
      providerApiKey = intent.getStringExtra(EXTRA_PROVIDER_API_KEY) != null ? intent.getStringExtra(EXTRA_PROVIDER_API_KEY) : providerApiKey;
      providerModel = intent.getStringExtra(EXTRA_PROVIDER_MODEL) != null ? intent.getStringExtra(EXTRA_PROVIDER_MODEL) : providerModel;
      providerBaseUrl = intent.getStringExtra(EXTRA_PROVIDER_BASE_URL) != null ? intent.getStringExtra(EXTRA_PROVIDER_BASE_URL) : providerBaseUrl;
      startNonce = "";
      navigationActive = false;
      awaitingUserStart = true;
      savePrefs();
    }
    showBubble();
    if (navigationActive) {
      awaitingUserStart = false;
      updateIndicator(true, "");
      requestNavigationAnalysis(true);
    } else {
      awaitingUserStart = true;
      updateReadyIndicator();
    }
    return START_STICKY;
  }

  @Override
  public IBinder onBind(Intent intent) {
    return null;
  }

  @Override
  public void onDestroy() {
    removeBubble();
    try {
      unregisterReceiver(guidanceReceiver);
    } catch (IllegalArgumentException ignored) {
      // Receiver was not registered or was already removed.
    }
    if (captureThread != null) {
      captureThread.quitSafely();
    }
    super.onDestroy();
  }

  private void showBubble() {
    if (bubbleView != null) {
      return;
    }

    SpinnerTextView bubble = new SpinnerTextView(this);
    bubble.setText("");
    bubble.setTextColor(Color.WHITE);
    bubble.setTextSize(22);
    bubble.setGravity(Gravity.CENTER);
    bubble.setTypeface(null, 1);
    bubble.setSingleLine(true);
    bubble.setEllipsize(TextUtils.TruncateAt.END);
    bubble.setMaxWidth(dp(190));
    bubble.setSpinnerMode(false);
    spinnerDrawable = new SpinnerDrawable();
    bubble.setBackground(spinnerDrawable);
    bubble.setElevation(8f);

    int overlayType = Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
      ? WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
      : WindowManager.LayoutParams.TYPE_PHONE;
    bubbleParams = new WindowManager.LayoutParams(
      dp(48),
      dp(48),
      overlayType,
      WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,
      PixelFormat.TRANSLUCENT
    );
    bubbleParams.gravity = Gravity.TOP | Gravity.START;
    bubbleParams.x = dp(18);
    bubbleParams.y = dp(160);

    bubble.setOnClickListener(new View.OnClickListener() {
      @Override
      public void onClick(View view) {
        if (awaitingUserStart) {
          beginNavigationAnalysis();
          return;
        }
        openExitGuideApp();
      }
    });
    attachDragHandler(bubble);
    bubbleView = bubble;
    windowManager.addView(bubbleView, bubbleParams);
  }

  private void openExitGuideApp() {
    Intent launchIntent = getPackageManager().getLaunchIntentForPackage(getPackageName());
    if (launchIntent == null) {
      Log.w("ExitGuideOverlay", "ExitGuide launch intent was not found");
      return;
    }
    launchIntent.addFlags(
      Intent.FLAG_ACTIVITY_NEW_TASK
        | Intent.FLAG_ACTIVITY_REORDER_TO_FRONT
        | Intent.FLAG_ACTIVITY_SINGLE_TOP
    );
    try {
      startActivity(launchIntent);
    } catch (RuntimeException error) {
      Log.e("ExitGuideOverlay", "Failed to open ExitGuide", error);
    }
  }

  private void beginNavigationAnalysis() {
    if (navigationActive || !awaitingUserStart) {
      return;
    }
    awaitingUserStart = false;
    navigationActive = true;
    startNonce = Long.toString(System.currentTimeMillis());
    savePrefs();
    removeReadyMessage();
    updateIndicator(true, "");
    Log.i("ExitGuideOverlay", "navigation exploration started by overlay button");
    requestNavigationAnalysis(true);
  }

  private void finishNavigation(String label, String finishReason) {
    navigationActive = false;
    awaitingUserStart = false;
    startNonce = "";
    savePrefs();
    boolean destinationReached = FINISH_REASON_DESTINATION_REACHED.equals(finishReason);
    String normalizedReason = destinationReached
      ? FINISH_REASON_DESTINATION_REACHED
      : FINISH_REASON_STOPPED_NOT_FOUND;
    String toastMessage = destinationReached
      ? (label.length() == 0 ? "최종 목적지에 도달했습니다." : "최종 목적지 도달: " + label)
      : "탐색을 종료했습니다. 목적 경로를 찾지 못했습니다.";
    updateIndicator(false, destinationReached && label.length() > 0 ? label : "못 찾음");
    showToast(toastMessage);
    // Keep the compact result bubble visible after automation stops. The user
    // owns the final state-changing press, and tapping this result opens
    // ExitGuide instead of restarting exploration. Clearing or changing the
    // goal still resets/removes the overlay through the normal module API.
    Log.i("ExitGuideOverlay", "navigation exploration finished reason=" + normalizedReason);
  }

  private void attachDragHandler(View view) {
    view.setOnTouchListener(new View.OnTouchListener() {
      private int startX;
      private int startY;
      private float touchStartX;
      private float touchStartY;
      private long downAt;
      private boolean moved;

      @Override
      public boolean onTouch(View target, MotionEvent event) {
        if (bubbleParams == null) {
          return false;
        }
        switch (event.getAction()) {
          case MotionEvent.ACTION_DOWN:
            startX = bubbleParams.x;
            startY = bubbleParams.y;
            touchStartX = event.getRawX();
            touchStartY = event.getRawY();
            downAt = System.currentTimeMillis();
            moved = false;
            return true;
          case MotionEvent.ACTION_MOVE:
            int deltaX = (int) (event.getRawX() - touchStartX);
            int deltaY = (int) (event.getRawY() - touchStartY);
            if (Math.abs(deltaX) > 8 || Math.abs(deltaY) > 8) {
              moved = true;
            }
            bubbleParams.x = startX + deltaX;
            bubbleParams.y = startY + deltaY;
            windowManager.updateViewLayout(bubbleView, bubbleParams);
            if (readyMessageView != null && readyMessageParams != null) {
              readyMessageParams.x = bubbleParams.x + dp(60);
              readyMessageParams.y = bubbleParams.y - dp(6);
              windowManager.updateViewLayout(readyMessageView, readyMessageParams);
            }
            return true;
          case MotionEvent.ACTION_UP:
            if (!moved && System.currentTimeMillis() - downAt < 250) {
              target.performClick();
            }
            return true;
          default:
            return false;
        }
      }
    });
  }

  private void captureAndAnalyze(int resultCode, Intent resultData) {
    final MediaProjectionManager projectionManager =
      (MediaProjectionManager) getSystemService(Context.MEDIA_PROJECTION_SERVICE);
    final MediaProjection projection = projectionManager.getMediaProjection(resultCode, resultData);
    if (projection == null) {
      showToast("화면 캡처를 시작하지 못했습니다.");
      return;
    }

    if (captureThread == null || !captureThread.isAlive()) {
      captureThread = new HandlerThread("ExitGuideCapture");
      captureThread.start();
    }
    final Handler captureHandler = new Handler(captureThread.getLooper());
    final DisplayMetrics metrics = getResources().getDisplayMetrics();
    final ImageReader reader = ImageReader.newInstance(
      metrics.widthPixels,
      metrics.heightPixels,
      PixelFormat.RGBA_8888,
      2
    );
    final VirtualDisplay display = projection.createVirtualDisplay(
      "ExitGuideCapture",
      metrics.widthPixels,
      metrics.heightPixels,
      metrics.densityDpi,
      DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
      reader.getSurface(),
      null,
      captureHandler
    );

    reader.setOnImageAvailableListener(new ImageReader.OnImageAvailableListener() {
      @Override
      public void onImageAvailable(ImageReader imageReader) {
        Image image = null;
        try {
          image = imageReader.acquireLatestImage();
          if (image == null) {
            return;
          }
          byte[] png = imageToPng(image, metrics.widthPixels, metrics.heightPixels);
          postAnalysis(png);
        } catch (Exception error) {
          showToast("화면 분석에 실패했습니다.");
        } finally {
          if (image != null) {
            image.close();
          }
          display.release();
          reader.close();
          projection.stop();
        }
      }
    }, captureHandler);
  }

  private byte[] imageToPng(Image image, int width, int height) {
    Image.Plane[] planes = image.getPlanes();
    ByteBuffer buffer = planes[0].getBuffer();
    int pixelStride = planes[0].getPixelStride();
    int rowStride = planes[0].getRowStride();
    int rowPadding = rowStride - pixelStride * width;
    Bitmap bitmap = Bitmap.createBitmap(width + rowPadding / pixelStride, height, Bitmap.Config.ARGB_8888);
    bitmap.copyPixelsFromBuffer(buffer);
    Bitmap cropped = Bitmap.createBitmap(bitmap, 0, 0, width, height);
    ByteArrayOutputStream output = new ByteArrayOutputStream();
    cropped.compress(Bitmap.CompressFormat.PNG, 90, output);
    bitmap.recycle();
    cropped.recycle();
    return output.toByteArray();
  }

  private void postAnalysis(final byte[] png) {
    new Thread(new Runnable() {
      @Override
      public void run() {
        HttpURLConnection connection = null;
        try {
          String boundary = "ExitGuide" + System.currentTimeMillis();
          URL url = new URL(normalizeBaseUrl(apiBaseUrl) + "/v1/analyze");
          connection = (HttpURLConnection) url.openConnection();
          connection.setConnectTimeout(10000);
          connection.setReadTimeout(20000);
          connection.setDoOutput(true);
          connection.setRequestMethod("POST");
          connection.setRequestProperty("Content-Type", "multipart/form-data; boundary=" + boundary);

          DataOutputStream output = new DataOutputStream(connection.getOutputStream());
          String cleanedGoal = goalText != null ? goalText.trim() : "";
          if (cleanedGoal.length() > 0) {
            writeField(output, boundary, "goal_text", cleanedGoal);
          } else {
            writeField(output, boundary, "infer_goal", "true");
          }
          writeProviderFields(output, boundary);
          writeFile(output, boundary, "screenshot", "overlay-screen.png", "image/png", png);
          output.writeBytes("--" + boundary + "--\\r\\n");
          output.flush();
          output.close();

          int status = connection.getResponseCode();
          String body = readBody(status >= 200 && status < 300 ? connection.getInputStream() : connection.getErrorStream());
          if (status >= 200 && status < 300) {
            showToast("화면 분석 완료: " + riskLabel(body));
          } else {
            showToast("API 응답 오류 " + status);
          }
        } catch (Exception error) {
          showToast("API에 연결하지 못했습니다.");
        } finally {
          if (connection != null) {
            connection.disconnect();
          }
        }
      }
    }).start();
  }

  private void writeField(DataOutputStream output, String boundary, String name, String value) throws Exception {
    output.writeBytes("--" + boundary + "\\r\\n");
    output.writeBytes("Content-Disposition: form-data; name=\\"" + name + "\\"\\r\\n\\r\\n");
    output.write(value.getBytes("UTF-8"));
    output.writeBytes("\\r\\n");
  }

  private void writeFile(
    DataOutputStream output,
    String boundary,
    String name,
    String filename,
    String contentType,
    byte[] bytes
  ) throws Exception {
    output.writeBytes("--" + boundary + "\\r\\n");
    output.writeBytes("Content-Disposition: form-data; name=\\"" + name + "\\"; filename=\\"" + filename + "\\"\\r\\n");
    output.writeBytes("Content-Type: " + contentType + "\\r\\n\\r\\n");
    output.write(bytes);
    output.writeBytes("\\r\\n");
  }

  private void writeProviderFields(DataOutputStream output, String boundary) throws Exception {
    String cleanedProviderId = providerId != null ? providerId.trim() : "";
    if (cleanedProviderId.length() == 0 || "server".equals(cleanedProviderId)) {
      return;
    }
    writeField(output, boundary, "provider_id", cleanedProviderId);
    writeOptionalField(output, boundary, "provider_api_key", providerApiKey);
    writeOptionalField(output, boundary, "provider_model", providerModel);
    writeOptionalField(output, boundary, "provider_base_url", providerBaseUrl);
  }

  private void writeOptionalField(DataOutputStream output, String boundary, String name, String value) throws Exception {
    String cleaned = value != null ? value.trim() : "";
    if (cleaned.length() > 0) {
      writeField(output, boundary, name, cleaned);
    }
  }

  private String readBody(InputStream stream) throws Exception {
    if (stream == null) {
      return "";
    }
    ByteArrayOutputStream output = new ByteArrayOutputStream();
    byte[] buffer = new byte[4096];
    int read;
    while ((read = stream.read(buffer)) != -1) {
      output.write(buffer, 0, read);
    }
    stream.close();
    return output.toString("UTF-8");
  }

  private String riskLabel(String body) {
    if (body.contains("\\"overall_risk\\":\\"high\\"") || body.contains("\\"overall_risk\\": \\"high\\"")) {
      return "고위험";
    }
    if (body.contains("\\"overall_risk\\":\\"medium\\"") || body.contains("\\"overall_risk\\": \\"medium\\"")) {
      return "확인 필요";
    }
    return "낮은 위험";
  }

  private String normalizeBaseUrl(String value) {
    String base = value == null ? "" : value.trim();
    if (base.endsWith("/")) {
      base = base.substring(0, base.length() - 1);
    }
    return base;
  }

  private void restorePrefs() {
    SharedPreferences prefs = getSharedPreferences(PREFS_NAME, MODE_PRIVATE);
    apiBaseUrl = prefs.getString(PREF_API_BASE_URL, "");
    goalText = prefs.getString(PREF_GOAL_TEXT, "");
    operationMode = "explore";
    startNonce = prefs.getString(PREF_START_NONCE, "");
    navigationActive = prefs.getBoolean(PREF_EXPLORATION_ACTIVE, false);
    awaitingUserStart = !navigationActive;
    providerId = prefs.getString(PREF_PROVIDER_ID, "server");
    providerApiKey = prefs.getString(PREF_PROVIDER_API_KEY, "");
    providerModel = prefs.getString(PREF_PROVIDER_MODEL, "");
    providerBaseUrl = prefs.getString(PREF_PROVIDER_BASE_URL, "");
  }

  private void savePrefs() {
    getSharedPreferences(PREFS_NAME, MODE_PRIVATE)
      .edit()
      .putString(PREF_API_BASE_URL, apiBaseUrl)
      .putString(PREF_GOAL_TEXT, goalText)
      .putString(PREF_OPERATION_MODE, "explore")
      .putString(PREF_START_NONCE, startNonce)
      .putBoolean(PREF_EXPLORATION_ACTIVE, navigationActive)
      .putString(PREF_PROVIDER_ID, providerId)
      .putString(PREF_PROVIDER_API_KEY, providerApiKey)
      .putString(PREF_PROVIDER_MODEL, providerModel)
      .putString(PREF_PROVIDER_BASE_URL, providerBaseUrl)
      .apply();
  }

  private void requestNavigationAnalysis(boolean force) {
    Intent request = new Intent(ExitGuideAccessibilityService.ACTION_REQUEST_ANALYSIS);
    request.setPackage(getPackageName());
    request.putExtra(ExitGuideAccessibilityService.EXTRA_FORCE_ANALYSIS, force);
    sendBroadcast(request);
  }

  private void updateReadyIndicator() {
    mainHandler.post(new Runnable() {
      @Override
      public void run() {
        if (bubbleView == null || bubbleParams == null) {
          return;
        }
        if (indicatorAnimator != null) {
          indicatorAnimator.cancel();
          indicatorAnimator = null;
        }
        GradientDrawable background = new GradientDrawable();
        background.setColor(Color.rgb(45, 121, 112));
        background.setShape(GradientDrawable.OVAL);
        bubbleView.setSpinnerMode(false);
        bubbleView.setText("▶");
        bubbleView.setTextSize(20);
        bubbleView.setTextColor(Color.WHITE);
        bubbleView.setPadding(dp(3), 0, 0, 0);
        bubbleView.setBackground(background);
        bubbleParams.width = dp(48);
        bubbleParams.height = dp(48);
        windowManager.updateViewLayout(bubbleView, bubbleParams);
        showReadyMessage();
      }
    });
  }

  private void showReadyMessage() {
    if (readyMessageView != null || bubbleParams == null) {
      return;
    }
    TextView message = new TextView(this);
    message.setText("해당 어플을 열고,\\n시작을 눌러주세요");
    message.setTextColor(Color.rgb(24, 28, 33));
    message.setTextSize(13);
    message.setGravity(Gravity.CENTER_VERTICAL);
    message.setPadding(dp(13), dp(7), dp(13), dp(7));
    GradientDrawable messageBackground = new GradientDrawable();
    messageBackground.setColor(Color.WHITE);
    messageBackground.setShape(GradientDrawable.RECTANGLE);
    messageBackground.setCornerRadius(dp(14));
    message.setBackground(messageBackground);
    message.setElevation(8f);

    int overlayType = Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
      ? WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
      : WindowManager.LayoutParams.TYPE_PHONE;
    readyMessageParams = new WindowManager.LayoutParams(
      WindowManager.LayoutParams.WRAP_CONTENT,
      WindowManager.LayoutParams.WRAP_CONTENT,
      overlayType,
      WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE | WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE,
      PixelFormat.TRANSLUCENT
    );
    readyMessageParams.gravity = Gravity.TOP | Gravity.START;
    readyMessageParams.x = bubbleParams.x + dp(60);
    readyMessageParams.y = bubbleParams.y - dp(6);
    readyMessageView = message;
    windowManager.addView(readyMessageView, readyMessageParams);
  }

  private void removeReadyMessage() {
    if (readyMessageView != null) {
      windowManager.removeView(readyMessageView);
      readyMessageView = null;
      readyMessageParams = null;
    }
  }

  private void updateIndicator(boolean exploring, String label) {
    mainHandler.post(new Runnable() {
      @Override
      public void run() {
        if (bubbleView == null || bubbleParams == null) {
          return;
        }
        removeReadyMessage();
        if (indicatorAnimator != null) {
          indicatorAnimator.cancel();
          indicatorAnimator = null;
        }
        GradientDrawable background = new GradientDrawable();
        if (exploring) {
          bubbleView.setSpinnerMode(false);
          bubbleView.setText("");
          bubbleView.setPadding(0, 0, 0, 0);
          bubbleParams.width = dp(48);
          bubbleParams.height = dp(48);
          if (spinnerDrawable == null) {
            spinnerDrawable = new SpinnerDrawable();
          }
          spinnerDrawable.setSpinnerRotation(0f);
          bubbleView.setBackground(spinnerDrawable);
          spinnerAnimationStartedAtMs = SystemClock.uptimeMillis();
          indicatorAnimator = ValueAnimator.ofFloat(0f, 1f);
          indicatorAnimator.setDuration(SPINNER_ROTATION_PERIOD_MS);
          indicatorAnimator.setRepeatCount(ValueAnimator.INFINITE);
          indicatorAnimator.setRepeatMode(ValueAnimator.RESTART);
          indicatorAnimator.setInterpolator(new LinearInterpolator());
          indicatorAnimator.addUpdateListener(new ValueAnimator.AnimatorUpdateListener() {
            @Override
            public void onAnimationUpdate(ValueAnimator animation) {
              if (spinnerDrawable == null) {
                return;
              }
              long elapsedMs = SystemClock.uptimeMillis() - spinnerAnimationStartedAtMs;
              float rotation = (elapsedMs % SPINNER_ROTATION_PERIOD_MS)
                * 360f / (float) SPINNER_ROTATION_PERIOD_MS;
              spinnerDrawable.setSpinnerRotation(rotation);
            }
          });
          indicatorAnimator.start();
        } else {
          bubbleView.setSpinnerMode(false);
          background.setColor(Color.rgb(45, 121, 112));
          background.setShape(GradientDrawable.RECTANGLE);
          background.setCornerRadius(dp(21));
          String compactLabel = label.length() == 0 ? "못 찾음" : label;
          bubbleView.setText(compactLabel);
          bubbleView.setTextSize(14);
          bubbleView.setPadding(dp(14), 0, dp(14), 0);
          bubbleParams.width = WindowManager.LayoutParams.WRAP_CONTENT;
          bubbleParams.height = dp(42);
          bubbleView.setBackground(background);
        }
        windowManager.updateViewLayout(bubbleView, bubbleParams);
      }
    });
  }

  private void removeBubble() {
    removeReadyMessage();
    if (bubbleView != null) {
      windowManager.removeView(bubbleView);
      bubbleView = null;
    }
    if (indicatorAnimator != null) {
      indicatorAnimator.cancel();
      indicatorAnimator = null;
    }
  }

  private void showToast(final String message) {
    mainHandler.post(new Runnable() {
      @Override
      public void run() {
        Toast.makeText(ExitGuideOverlayService.this, message, Toast.LENGTH_LONG).show();
      }
    });
  }

  private Notification buildNotification() {
    Notification.Builder builder = Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
      ? new Notification.Builder(this, CHANNEL_ID)
      : new Notification.Builder(this);
    return builder
      .setContentTitle("ExitGuide AI")
      .setContentText("화면 위 아이콘이 켜져 있습니다.")
      .setSmallIcon(android.R.drawable.ic_dialog_info)
      .setOngoing(true)
      .build();
  }

  private void startOverlayForeground() {
    Notification notification = buildNotification();
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
      startForeground(
        NOTIFICATION_ID,
        notification,
        ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE
      );
      return;
    }
    startForeground(NOTIFICATION_ID, notification);
  }

  private void startCaptureForeground() {
    Notification notification = buildNotification();
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
      startForeground(
        NOTIFICATION_ID,
        notification,
        ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE
          | ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION
      );
      return;
    }
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
      startForeground(
        NOTIFICATION_ID,
        notification,
        ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION
      );
      return;
    }
    startForeground(NOTIFICATION_ID, notification);
  }

  private void createNotificationChannel() {
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
      NotificationChannel channel = new NotificationChannel(
        CHANNEL_ID,
        "ExitGuide overlay",
        NotificationManager.IMPORTANCE_LOW
      );
      NotificationManager manager = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
      manager.createNotificationChannel(channel);
    }
  }

  private int dp(int value) {
    return (int) (value * getResources().getDisplayMetrics().density + 0.5f);
  }
}
`;
}

function accessibilityServiceConfigSource() {
  return `<?xml version="1.0" encoding="utf-8"?>
<accessibility-service xmlns:android="http://schemas.android.com/apk/res/android"
  android:accessibilityEventTypes="typeWindowStateChanged|typeWindowContentChanged|typeViewClicked|typeViewScrolled"
  android:accessibilityFeedbackType="feedbackGeneric"
  android:accessibilityFlags="flagReportViewIds|flagRetrieveInteractiveWindows"
  android:canRetrieveWindowContent="true"
  android:canPerformGestures="true"
  android:canTakeScreenshot="true"
  android:description="@string/app_name"
  android:notificationTimeout="250" />
`;
}

function networkSecurityConfigSource() {
  return `<?xml version="1.0" encoding="utf-8"?>
<network-security-config>
  <base-config cleartextTrafficPermitted="false" />
  <domain-config cleartextTrafficPermitted="true">
    <domain includeSubdomains="false">localhost</domain>
    <domain includeSubdomains="false">127.0.0.1</domain>
    <domain includeSubdomains="false">10.0.2.2</domain>
  </domain-config>
</network-security-config>
`;
}

function accessibilityServiceSource() {
  return `package ${OVERLAY_PACKAGE};

import android.accessibilityservice.AccessibilityService;
import android.accessibilityservice.GestureDescription;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.SharedPreferences;
import android.content.pm.PackageInfo;
import android.graphics.Bitmap;
import android.graphics.ColorSpace;
import android.graphics.Rect;
import android.graphics.Path;
import android.hardware.HardwareBuffer;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.util.Log;
import android.view.Display;
import android.view.accessibility.AccessibilityEvent;
import android.view.accessibility.AccessibilityNodeInfo;
import com.google.mlkit.vision.common.InputImage;
import com.google.mlkit.vision.text.Text;
import com.google.mlkit.vision.text.TextRecognition;
import com.google.mlkit.vision.text.TextRecognizer;
import com.google.mlkit.vision.text.korean.KoreanTextRecognizerOptions;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import org.json.JSONArray;
import org.json.JSONObject;

public class ExitGuideAccessibilityService extends AccessibilityService {
  private static final String LOG_TAG = "ExitGuideNavigation";
  public static final String ACTION_REQUEST_ANALYSIS = "com.exitguide.ai.overlay.REQUEST_NAVIGATION_ANALYSIS";
  public static final String ACTION_GUIDANCE = "com.exitguide.ai.overlay.NAVIGATION_GUIDANCE";
  public static final String EXTRA_FORCE_ANALYSIS = "forceAnalysis";
  public static final String EXTRA_GUIDANCE = "guidance";
  public static final String EXTRA_EXPLORING = "exploring";
  public static final String EXTRA_FINISHED = "finished";
  public static final String EXTRA_FINISH_REASON = "finishReason";

  private static final String PREFS_NAME = "exitguide_overlay";
  private static final String PREF_API_BASE_URL = "apiBaseUrl";
  private static final String PREF_GOAL_TEXT = "goalText";
  private static final String PREF_OPERATION_MODE = "operationMode";
  private static final String PREF_START_NONCE = "startNonce";
  private static final String PREF_EXPLORATION_ACTIVE = "explorationActive";
  private static final long ANALYSIS_DEBOUNCE_MS = 650L;
  private static final int MAX_NODES = 500;
  private static final float PAGE_SCROLL_EDGE_MARGIN_RATIO = 0.08f;
  private static final float PAGE_SCROLL_MIN_VIEWPORT_RATIO = 0.30f;
  private static final long PAGE_SCROLL_DURATION_MS = 420L;
  private static final long REQUEST_FAILURE_RETRY_DELAY_MS = 2500L;
  private static final String SYSTEM_UI_PACKAGE = "com.android.systemui";

  private final Handler mainHandler = new Handler(Looper.getMainLooper());
  private String sessionId = UUID.randomUUID().toString();
  private String lastActivityName = "";
  private String lastEventType = "window_state_changed";
  private String lastTreeSignature = "";
  private String lastScreenFingerprint = "";
  private String lastRecommendationId = "";
  private String lastSelectedElementId = "";
  private String pendingFromScreen = "";
  private String pendingPerformedElementId = "";
  private String pendingRecommendationId = "";
  private String pendingTransitionOutcome = "navigated";
  private long transitionSequenceCounter = 0L;
  private long pendingTransitionSequence = 0L;
  private String activeGoal = "";
  private String activeOperationMode = "explore";
  private String activeStartNonce = "";
  private boolean forceNextAnalysis = false;
  private volatile boolean requestInFlight = false;
  private volatile boolean requestQueued = false;
  private volatile String inFlightPackageName = "";
  private volatile String lastFailedTreeSignature = "";
  private volatile long retryNotBeforeElapsedMs = 0L;
  private volatile long boundedReobserveNotBeforeElapsedMs = 0L;
  private long screenCaptureStartedElapsedMs = 0L;
  private long lastScreenCaptureMs = 0L;
  private long lastActionExecutionMs = 0L;
  private long lastActionCompletedElapsedMs = 0L;
  private int lastNoOpRescheduledActionCount = -1;
  private TextRecognizer ocrRecognizer;
  private final Map<String, String> lastClickableElementIds = new HashMap<>();
  private final Map<String, Rect> lastClickableBounds = new HashMap<>();
  private final Set<String> ambiguousClickableKeys = new HashSet<>();

  private final Runnable analysisRunnable = new Runnable() {
    @Override
    public void run() {
      analyzeCurrentWindow();
    }
  };

  private final BroadcastReceiver analysisReceiver = new BroadcastReceiver() {
    @Override
    public void onReceive(Context context, Intent intent) {
      if (ACTION_REQUEST_ANALYSIS.equals(intent.getAction())) {
        scheduleAnalysis(intent.getBooleanExtra(EXTRA_FORCE_ANALYSIS, true));
      }
    }
  };

  @Override
  protected void onServiceConnected() {
    super.onServiceConnected();
    ocrRecognizer = TextRecognition.getClient(new KoreanTextRecognizerOptions.Builder().build());
    IntentFilter filter = new IntentFilter(ACTION_REQUEST_ANALYSIS);
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
      registerReceiver(analysisReceiver, filter, Context.RECEIVER_NOT_EXPORTED);
    } else {
      registerReceiver(analysisReceiver, filter);
    }
    if (isExplorationActive()) {
      sendIndicator(true, "");
      scheduleAnalysis(true);
    }
  }

  @Override
  public void onAccessibilityEvent(AccessibilityEvent event) {
    if (event == null || event.getPackageName() == null) {
      return;
    }
    String packageName = event.getPackageName().toString();
    if (getPackageName().equals(packageName)) {
      return;
    }
    if (!isExplorationActive()) {
      return;
    }
    if (!isRelevantAccessibilityEventPackage(packageName)) {
      Log.d(LOG_TAG, "ignored accessibility event from non-active package");
      return;
    }
    if (event.getClassName() != null) {
      lastActivityName = event.getClassName().toString();
    }
    lastEventType = eventTypeName(event.getEventType());

    if (event.getEventType() == AccessibilityEvent.TYPE_VIEW_CLICKED) {
      AccessibilityNodeInfo source = event.getSource();
      String performedElementId = "";
      if (source != null) {
        performedElementId = stableNodeId(source);
        source.recycle();
      } else {
        performedElementId = elementIdForEvent(event);
      }
      if (performedElementId.length() > 0 && lastScreenFingerprint.length() > 0) {
        pendingFromScreen = lastScreenFingerprint;
        pendingPerformedElementId = performedElementId;
        pendingRecommendationId = pendingPerformedElementId.equals(lastSelectedElementId)
          ? lastRecommendationId
          : "";
        pendingTransitionOutcome = "navigated";
        pendingTransitionSequence = ++transitionSequenceCounter;
      }
      Log.i(
        LOG_TAG,
        "click captured source=" + (source != null)
          + " matched=" + (performedElementId.length() > 0)
          + " hasFromScreen=" + (lastScreenFingerprint.length() > 0)
          + " eventTextCount=" + event.getText().size()
          + " hasDescription=" + (event.getContentDescription() != null)
      );
    }
    scheduleAnalysis(false);
  }

  @Override
  public void onInterrupt() {
    sendIndicator(false, "중단됨");
  }

  @Override
  public void onDestroy() {
    mainHandler.removeCallbacks(analysisRunnable);
    try {
      unregisterReceiver(analysisReceiver);
    } catch (IllegalArgumentException ignored) {
      // Receiver was already removed.
    }
    if (ocrRecognizer != null) {
      ocrRecognizer.close();
      ocrRecognizer = null;
    }
    super.onDestroy();
  }

  private void scheduleAnalysis(boolean force) {
    forceNextAnalysis = forceNextAnalysis || force;
    mainHandler.removeCallbacks(analysisRunnable);
    mainHandler.postDelayed(analysisRunnable, force ? 80L : ANALYSIS_DEBOUNCE_MS);
  }

  private void analyzeCurrentWindow() {
    if (requestInFlight) {
      requestQueued = true;
      return;
    }
    long nowElapsedMs = SystemClock.elapsedRealtime();
    long boundedReobserveDelayMs = boundedReobserveNotBeforeElapsedMs - nowElapsedMs;
    if (boundedReobserveDelayMs > 0L) {
      // WebView accessibility events can arrive continuously while a paid
      // plan detail is still painting.  They must not bypass the one bounded
      // settle period requested by the API.
      mainHandler.removeCallbacks(analysisRunnable);
      mainHandler.postDelayed(analysisRunnable, boundedReobserveDelayMs);
      return;
    }
    boundedReobserveNotBeforeElapsedMs = 0L;
    long retryDelayMs = retryNotBeforeElapsedMs - nowElapsedMs;
    if (!forceNextAnalysis && retryDelayMs > 0L) {
      mainHandler.removeCallbacks(analysisRunnable);
      mainHandler.postDelayed(analysisRunnable, retryDelayMs);
      return;
    }
    SharedPreferences prefs = getSharedPreferences(PREFS_NAME, MODE_PRIVATE);
    String apiBaseUrl = clean(prefs.getString(PREF_API_BASE_URL, ""));
    String goalText = clean(prefs.getString(PREF_GOAL_TEXT, ""));
    String operationMode = "explore";
    String startNonce = clean(prefs.getString(PREF_START_NONCE, ""));
    if (!prefs.getBoolean(PREF_EXPLORATION_ACTIVE, false)) {
      return;
    }
    if (apiBaseUrl.length() == 0 || goalText.length() == 0) {
      Log.w(
        LOG_TAG,
        "navigation settings missing hasApiBaseUrl=" + (apiBaseUrl.length() > 0)
          + " hasGoal=" + (goalText.length() > 0)
      );
      sendIndicator(false, "설정 필요");
      return;
    }
    if (!goalText.equals(activeGoal) || !operationMode.equals(activeOperationMode)
        || !startNonce.equals(activeStartNonce)) {
      activeGoal = goalText;
      activeOperationMode = operationMode;
      activeStartNonce = startNonce;
      sessionId = UUID.randomUUID().toString();
      lastTreeSignature = "";
      lastScreenFingerprint = "";
      lastRecommendationId = "";
      lastSelectedElementId = "";
      screenCaptureStartedElapsedMs = 0L;
      lastScreenCaptureMs = 0L;
      lastActionExecutionMs = 0L;
      lastActionCompletedElapsedMs = 0L;
      lastNoOpRescheduledActionCount = -1;
      boundedReobserveNotBeforeElapsedMs = 0L;
      lastFailedTreeSignature = "";
      retryNotBeforeElapsedMs = 0L;
      clearPendingTransition();
    }

    AccessibilityNodeInfo root = getRootInActiveWindow();
    if (root == null || root.getPackageName() == null) {
      sendIndicator(false, "화면 확인");
      return;
    }
    String packageName = root.getPackageName().toString();
    if (getPackageName().equals(packageName)) {
      root.recycle();
      return;
    }

    try {
      JSONArray elements = new JSONArray();
      int[] counter = new int[] {0};
      appendNode(root, null, elements, counter);
      if (elements.length() == 0) {
        sendIndicator(false, "메뉴 없음");
        return;
      }
      requestInFlight = true;
      inFlightPackageName = packageName;
      captureOcrAndSubmit(apiBaseUrl, packageName, goalText, startNonce, elements);
    } catch (Exception error) {
      sendIndicator(false, "분석 오류");
      finishRequestCycle();
    } finally {
      root.recycle();
    }
  }

  private void captureOcrAndSubmit(
    final String apiBaseUrl,
    final String packageName,
    final String goalText,
    final String startNonce,
    final JSONArray elements
  ) {
    screenCaptureStartedElapsedMs = SystemClock.elapsedRealtime();
    if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R || ocrRecognizer == null) {
      finishScreenCaptureTiming();
      submitObservationElements(apiBaseUrl, packageName, goalText, startNonce, elements);
      return;
    }
    try {
      takeScreenshot(Display.DEFAULT_DISPLAY, getMainExecutor(), new AccessibilityService.TakeScreenshotCallback() {
        @Override
        public void onSuccess(AccessibilityService.ScreenshotResult screenshot) {
          HardwareBuffer buffer = screenshot.getHardwareBuffer();
          Bitmap hardwareBitmap = null;
          Bitmap bitmap = null;
          try {
            ColorSpace colorSpace = screenshot.getColorSpace();
            hardwareBitmap = Bitmap.wrapHardwareBuffer(buffer, colorSpace);
            if (hardwareBitmap != null) {
              bitmap = hardwareBitmap.copy(Bitmap.Config.ARGB_8888, false);
            }
          } finally {
            buffer.close();
          }
          if (bitmap == null || ocrRecognizer == null) {
            finishScreenCaptureTiming();
            submitObservationElements(apiBaseUrl, packageName, goalText, startNonce, elements);
            return;
          }
          final Bitmap analysisBitmap = bitmap;
          ocrRecognizer.process(InputImage.fromBitmap(analysisBitmap, 0))
            .addOnSuccessListener(result -> {
              try {
                appendOcrElements(elements, result);
              } catch (Exception error) {
                Log.w(LOG_TAG, "OCR element merge failed: " + error.getClass().getSimpleName());
              } finally {
                analysisBitmap.recycle();
              }
              finishScreenCaptureTiming();
              submitObservationElements(apiBaseUrl, packageName, goalText, startNonce, elements);
            })
            .addOnFailureListener(error -> {
              analysisBitmap.recycle();
              Log.w(LOG_TAG, "on-device OCR failed: " + error.getClass().getSimpleName());
              finishScreenCaptureTiming();
              submitObservationElements(apiBaseUrl, packageName, goalText, startNonce, elements);
            });
        }

        @Override
        public void onFailure(int errorCode) {
          Log.w(LOG_TAG, "accessibility screenshot failed code=" + errorCode);
          finishScreenCaptureTiming();
          submitObservationElements(apiBaseUrl, packageName, goalText, startNonce, elements);
        }
      });
    } catch (Exception error) {
      Log.w(LOG_TAG, "accessibility screenshot unavailable: " + error.getClass().getSimpleName());
      finishScreenCaptureTiming();
      submitObservationElements(apiBaseUrl, packageName, goalText, startNonce, elements);
    }
  }

  private void finishScreenCaptureTiming() {
    if (screenCaptureStartedElapsedMs <= 0L) {
      lastScreenCaptureMs = 0L;
      return;
    }
    lastScreenCaptureMs = Math.max(0L, SystemClock.elapsedRealtime() - screenCaptureStartedElapsedMs);
    screenCaptureStartedElapsedMs = 0L;
  }

  private void submitObservationElements(
    String apiBaseUrl,
    String packageName,
    String goalText,
    String startNonce,
    JSONArray elements
  ) {
    try {
      if (!isNavigationRequestCurrent(goalText, startNonce)) {
        finishRequestCycle();
        return;
      }
      indexClickableElements(elements);
      String treeSignature = sha256(packageName + "|" + goalText + "|" + lastActivityName + "|" + elements.toString());
      boolean force = forceNextAnalysis;
      forceNextAnalysis = false;
      if (!force && pendingPerformedElementId.length() == 0
          && treeSignature.equals(lastFailedTreeSignature)) {
        // Never replay a failed request just because the same window emitted
        // another content-change event. A forced request or genuinely changed
        // UI tree remains eligible for analysis.
        requestQueued = false;
        Log.i(LOG_TAG, "suppressed duplicate observation after request failure");
        finishRequestCycle();
        return;
      }
      if (!force && pendingPerformedElementId.length() == 0 && treeSignature.equals(lastTreeSignature)) {
        finishRequestCycle();
        return;
      }
      JSONObject request = buildRequest(packageName, goalText, elements);
      long submittedTransitionSequence = request.has("transition")
        ? pendingTransitionSequence
        : 0L;
      postObservation(
        apiBaseUrl,
        request,
        treeSignature,
        submittedTransitionSequence,
        goalText,
        startNonce
      );
    } catch (Exception error) {
      Log.e(LOG_TAG, "navigation request preparation failed: " + error.getClass().getSimpleName());
      sendIndicator(false, "분석 오류");
      finishRequestCycle();
    }
  }

  private void appendOcrElements(JSONArray elements, Text result) throws Exception {
    int appended = 0;
    for (Text.TextBlock block : result.getTextBlocks()) {
      for (Text.Line line : block.getLines()) {
        String label = clean(line.getText());
        Rect bounds = line.getBoundingBox();
        if (label.length() == 0 || bounds == null || bounds.isEmpty() || isSensitiveOcrRegion(elements, bounds)) {
          continue;
        }
        JSONObject element = new JSONObject();
        element.put("id", "ocr_" + sha256(label + "|" + bounds.flattenToString()).substring(0, 20));
        String parentId = nearestClickableParent(elements, bounds);
        boolean coordinateClickable = parentId.length() == 0
          || !isTightlyContainedByClickableParent(elements, parentId, bounds);
        if (parentId.length() > 0) {
          element.put("parent_id", parentId);
        }
        element.put("text", label);
        element.put("view_id", "exitguide:ocr");
        // Custom-rendered apps sometimes expose neither a clickable node nor
        // a useful accessibility label. In that case the OCR line itself is
        // a bounded coordinate candidate. The server still applies the
        // safe-navigation policy and never auto-clicks terminal/state-changing
        // controls.
        element.put("role", coordinateClickable ? "button" : "text");
        element.put("clickable", coordinateClickable);
        element.put("enabled", true);
        element.put("visible", true);
        element.put("scrollable", false);
        element.put("checkable", false);
        element.put("selected", false);
        element.put("password", false);
        JSONArray box = new JSONArray();
        box.put(bounds.left);
        box.put(bounds.top);
        box.put(bounds.right);
        box.put(bounds.bottom);
        element.put("bounds", box);
        elements.put(element);
        appended += 1;
      }
    }
    Log.i(LOG_TAG, "on-device OCR merged lines=" + appended);
  }

  private boolean isSensitiveOcrRegion(JSONArray elements, Rect ocrBounds) {
    int centerX = ocrBounds.centerX();
    int centerY = ocrBounds.centerY();
    for (int index = 0; index < elements.length(); index += 1) {
      JSONObject element = elements.optJSONObject(index);
      if (element == null || !element.optBoolean("password", false)) {
        continue;
      }
      Rect bounds = boundsFor(element);
      if (bounds != null && bounds.contains(centerX, centerY)) {
        return true;
      }
    }
    return false;
  }

  private String nearestClickableParent(JSONArray elements, Rect ocrBounds) {
    String bestId = "";
    double bestScore = Double.NEGATIVE_INFINITY;
    int centerX = ocrBounds.centerX();
    int centerY = ocrBounds.centerY();
    int screenWidth = getResources().getDisplayMetrics().widthPixels;
    for (int index = 0; index < elements.length(); index += 1) {
      JSONObject element = elements.optJSONObject(index);
      if (element == null || !element.optBoolean("clickable", false)
          || !element.optBoolean("enabled", false) || !element.optBoolean("visible", false)
          || element.optBoolean("checkable", false) || element.optBoolean("password", false)) {
        continue;
      }
      Rect bounds = boundsFor(element);
      if (bounds == null || bounds.isEmpty()) {
        continue;
      }
      double score;
      if (bounds.contains(centerX, centerY)) {
        score = 1000000.0 - ((double) bounds.width() * (double) bounds.height());
      } else {
        int overlap = Math.min(bounds.bottom, ocrBounds.bottom) - Math.max(bounds.top, ocrBounds.top);
        double overlapRatio = overlap <= 0 ? 0.0
          : (double) overlap / (double) Math.max(1, Math.min(bounds.height(), ocrBounds.height()));
        int horizontalGap = Math.max(0, Math.max(bounds.left - ocrBounds.right, ocrBounds.left - bounds.right));
        // Do not attach an OCR label to an unrelated trailing control merely
        // because it happens to share the same row.  Baemin's nickname, for
        // example, sits beside separate pencil/customize controls; treating a
        // far-away control as its parent removes the only safe coordinate
        // doorway into profile editing.  A small gap still preserves labels
        // for genuinely adjacent icons/chevrons, while a larger gap leaves the
        // OCR line as its own reversible coordinate candidate.
        if (overlapRatio < 0.35 || horizontalGap > (int) (screenWidth * 0.10f)) {
          continue;
        }
        score = 5000.0 + overlapRatio * 1000.0 - horizontalGap - Math.abs(bounds.centerY() - centerY) * 2.0;
      }
      if (score > bestScore) {
        bestScore = score;
        bestId = element.optString("id", "");
      }
    }
    return bestId;
  }

  private boolean isTightlyContainedByClickableParent(
    JSONArray elements,
    String parentId,
    Rect ocrBounds
  ) {
    if (parentId == null || parentId.length() == 0 || ocrBounds == null || ocrBounds.isEmpty()) {
      return false;
    }
    long ocrArea = Math.max(1L, (long) ocrBounds.width() * (long) ocrBounds.height());
    for (int index = 0; index < elements.length(); index += 1) {
      JSONObject element = elements.optJSONObject(index);
      if (element == null || !parentId.equals(element.optString("id", ""))) {
        continue;
      }
      Rect parentBounds = boundsFor(element);
      if (parentBounds == null || parentBounds.isEmpty()
          || !parentBounds.contains(ocrBounds.centerX(), ocrBounds.centerY())) {
        return false;
      }
      long parentArea = Math.max(
        1L,
        (long) parentBounds.width() * (long) parentBounds.height()
      );
      // A real button/row is only modestly larger than its text. A screen-wide
      // Compose container can be tens of times larger and must not suppress
      // the OCR coordinate candidate inside it.
      return parentArea <= ocrArea * 12L;
    }
    return false;
  }

  private Rect boundsFor(JSONObject element) {
    JSONArray bounds = element.optJSONArray("bounds");
    if (bounds == null || bounds.length() < 4) {
      return null;
    }
    return new Rect(bounds.optInt(0), bounds.optInt(1), bounds.optInt(2), bounds.optInt(3));
  }

  private JSONObject buildRequest(String packageName, String goalText, JSONArray elements) throws Exception {
    long now = System.currentTimeMillis();
    JSONObject screen = new JSONObject();
    screen.put("activity_name", lastActivityName);
    screen.put("window_title", firstReadableLabel(elements));
    screen.put("event_type", lastEventType);
    screen.put("captured_at", Long.toString(now));
    screen.put("elements", elements);

    JSONObject request = new JSONObject();
    request.put("request_id", "android_" + now);
    request.put("session_id", sessionId);
    request.put("app_package", packageName);
    request.put("app_version", appVersion(packageName));
    request.put("locale", Locale.getDefault().toLanguageTag());
    request.put("goal_text", goalText);
    request.put("operation_mode", activeOperationMode);
    request.put("screen", screen);
    long nowElapsed = SystemClock.elapsedRealtime();
    long elapsedSinceAction = lastActionCompletedElapsedMs <= 0L
      ? 0L
      : Math.max(0L, nowElapsed - lastActionCompletedElapsedMs);
    long uiSettleMs = Math.min(760L, elapsedSinceAction);
    long externalWaitMs = Math.max(0L, elapsedSinceAction - uiSettleMs - lastScreenCaptureMs);
    long explorationElapsedMs = elapsedSinceStartNonce(now);
    JSONObject clientTiming = new JSONObject();
    clientTiming.put("measurement_source", "real_device");
    clientTiming.put("exploration_elapsed_ms", explorationElapsedMs);
    clientTiming.put("screen_capture_ms", lastScreenCaptureMs);
    clientTiming.put("action_execution_ms", lastActionExecutionMs);
    clientTiming.put("ui_settle_ms", uiSettleMs);
    clientTiming.put("external_wait_ms", externalWaitMs);
    request.put("client_timing", clientTiming);
    lastScreenCaptureMs = 0L;
    lastActionExecutionMs = 0L;
    lastActionCompletedElapsedMs = 0L;
    if (pendingFromScreen.length() > 0 && pendingPerformedElementId.length() > 0) {
      JSONObject transition = new JSONObject();
      transition.put("from_screen_fingerprint", pendingFromScreen);
      transition.put("performed_element_id", pendingPerformedElementId);
      if (pendingRecommendationId.length() > 0) {
        transition.put("recommendation_id", pendingRecommendationId);
      }
      transition.put("outcome", pendingTransitionOutcome);
      request.put("transition", transition);
      Log.i(
        LOG_TAG,
        "transition queued hasRecommendation=" + (pendingRecommendationId.length() > 0)
      );
    }
    return request;
  }

  private long elapsedSinceStartNonce(long nowWallMs) {
    try {
      long startedWallMs = Long.parseLong(activeStartNonce);
      return Math.max(0L, Math.min(3600000L, nowWallMs - startedWallMs));
    } catch (NumberFormatException ignored) {
      return 0L;
    }
  }

  private void postObservation(
    final String apiBaseUrl,
    final JSONObject request,
    final String treeSignature,
    final long submittedTransitionSequence,
    final String submittedGoal,
    final String submittedStartNonce
  ) {
    new Thread(new Runnable() {
      @Override
      public void run() {
        HttpURLConnection connection = null;
        try {
          URL url = new URL(normalizeBaseUrl(apiBaseUrl) + "/v1/navigation/agent/observe");
          connection = (HttpURLConnection) url.openConnection();
          connection.setConnectTimeout(10000);
          connection.setReadTimeout(45000);
          connection.setDoOutput(true);
          connection.setRequestMethod("POST");
          connection.setRequestProperty("Content-Type", "application/json; charset=utf-8");
          byte[] body = request.toString().getBytes(StandardCharsets.UTF_8);
          connection.setFixedLengthStreamingMode(body.length);
          OutputStream output = connection.getOutputStream();
          output.write(body);
          output.flush();
          output.close();

          int statusCode = connection.getResponseCode();
          String responseBody = readBody(
            statusCode >= 200 && statusCode < 300 ? connection.getInputStream() : connection.getErrorStream()
          );
          if (statusCode < 200 || statusCode >= 300) {
            Log.e(LOG_TAG, "observation response status=" + statusCode);
            markObservationRequestFailed(treeSignature);
            sendIndicator(false, "API 오류");
            return;
          }
          if (!isNavigationRequestCurrent(submittedGoal, submittedStartNonce)) {
            Log.i(LOG_TAG, "discarded stale observation after navigation was cleared or restarted");
            return;
          }
          JSONObject response = new JSONObject(responseBody);
          clearObservationRequestFailure();
          lastTreeSignature = treeSignature;
          lastScreenFingerprint = response.optString("screen_fingerprint", "");
          JSONObject graphUpdate = response.optJSONObject("graph_update");
          JSONObject recommendation = response.optJSONObject("recommendation");
          Log.i(
            LOG_TAG,
            "observation response status=" + statusCode
              + " hasFingerprint=" + (lastScreenFingerprint.length() > 0)
              + " decisionMode=" + response.optString("decision_mode", "unknown")
              + " phase=" + response.optString("phase", "unknown")
              + " automationAction=" + (response.optJSONObject("automation") == null
                ? "none" : response.optJSONObject("automation").optString("action", "none"))
              + " selectedLabel=" + (recommendation == null
                ? "none" : recommendation.optString("selected_label", "none"))
              + " transitionRecorded=" + (graphUpdate != null
                && graphUpdate.optBoolean("transition_recorded", false))
          );
          if (recommendation != null) {
            lastRecommendationId = recommendation.optString("recommendation_id", "");
            lastSelectedElementId = recommendation.optString("selected_element_id", "");
          } else {
            lastRecommendationId = "";
            lastSelectedElementId = "";
          }
          // A slow model response must never erase a click that happened
          // after this request was submitted. Clear only the exact transition
          // snapshot carried by this response.
          clearPendingTransition(submittedTransitionSequence);
          publishOverlayState(response, recommendation);
          if ("destination_reached".equals(response.optString("phase", ""))) {
            postCompletionTiming(
              apiBaseUrl,
              request.optString("session_id", ""),
              elapsedSinceStartNonce(System.currentTimeMillis())
            );
          }
          scheduleAutomation(response, recommendation);
        } catch (Exception error) {
          Log.e(LOG_TAG, "observation request failed: " + error.getClass().getSimpleName());
          markObservationRequestFailed(treeSignature);
          sendIndicator(false, "연결 오류");
        } finally {
          if (connection != null) {
            connection.disconnect();
          }
          finishRequestCycle();
        }
      }
    }, "ExitGuideNavigationRequest").start();
  }

  private void postCompletionTiming(
    final String apiBaseUrl,
    final String completedSessionId,
    final long timeToDestinationMs
  ) {
    if (completedSessionId.length() == 0 || timeToDestinationMs <= 0L) {
      return;
    }
    new Thread(new Runnable() {
      @Override
      public void run() {
        HttpURLConnection connection = null;
        try {
          URL url = new URL(
            normalizeBaseUrl(apiBaseUrl) + "/v1/navigation/agent/performance/complete"
          );
          connection = (HttpURLConnection) url.openConnection();
          connection.setConnectTimeout(10000);
          connection.setReadTimeout(15000);
          connection.setDoOutput(true);
          connection.setRequestMethod("POST");
          connection.setRequestProperty("Content-Type", "application/json; charset=utf-8");
          JSONObject payload = new JSONObject();
          payload.put("session_id", completedSessionId);
          payload.put("measurement_source", "real_device");
          payload.put("time_to_confirmed_destination_ms", timeToDestinationMs);
          byte[] body = payload.toString().getBytes(StandardCharsets.UTF_8);
          connection.setFixedLengthStreamingMode(body.length);
          OutputStream output = connection.getOutputStream();
          output.write(body);
          output.flush();
          output.close();
          int statusCode = connection.getResponseCode();
          if (statusCode < 200 || statusCode >= 300) {
            Log.w(LOG_TAG, "completion timing response status=" + statusCode);
          } else {
            Log.i(LOG_TAG, "completion timing recorded ms=" + timeToDestinationMs);
          }
        } catch (Exception error) {
          // Navigation is already complete. Telemetry failure must never alter
          // the user's result or restart automation.
          Log.w(LOG_TAG, "completion timing upload failed: " + error.getClass().getSimpleName());
        } finally {
          if (connection != null) {
            connection.disconnect();
          }
        }
      }
    }, "ExitGuideCompletionTiming").start();
  }

  private void finishRequestCycle() {
    requestInFlight = false;
    inFlightPackageName = "";
    if (requestQueued) {
      requestQueued = false;
      mainHandler.post(new Runnable() {
        @Override
        public void run() {
          scheduleAnalysis(false);
        }
      });
    }
  }

  private void markObservationRequestFailed(String treeSignature) {
    lastFailedTreeSignature = treeSignature == null ? "" : treeSignature;
    retryNotBeforeElapsedMs = SystemClock.elapsedRealtime() + REQUEST_FAILURE_RETRY_DELAY_MS;
  }

  private void clearObservationRequestFailure() {
    lastFailedTreeSignature = "";
    retryNotBeforeElapsedMs = 0L;
  }

  private boolean isRelevantAccessibilityEventPackage(String eventPackageName) {
    if (eventPackageName == null || eventPackageName.length() == 0
        || getPackageName().equals(eventPackageName)
        || SYSTEM_UI_PACKAGE.equals(eventPackageName)) {
      return false;
    }
    AccessibilityNodeInfo activeRoot = getRootInActiveWindow();
    if (activeRoot == null || activeRoot.getPackageName() == null) {
      if (activeRoot != null) {
        activeRoot.recycle();
      }
      return false;
    }
    String activePackageName = activeRoot.getPackageName().toString();
    activeRoot.recycle();
    return eventPackageName.equals(activePackageName)
      && !SYSTEM_UI_PACKAGE.equals(activePackageName)
      && !getPackageName().equals(activePackageName)
      && (!requestInFlight || inFlightPackageName.length() == 0
        || eventPackageName.equals(inFlightPackageName));
  }

  private boolean isNavigationRequestCurrent(String submittedGoal, String submittedStartNonce) {
    SharedPreferences prefs = getSharedPreferences(PREFS_NAME, MODE_PRIVATE);
    return submittedGoal.equals(clean(prefs.getString(PREF_GOAL_TEXT, "")))
      && submittedStartNonce.equals(clean(prefs.getString(PREF_START_NONCE, "")))
      && prefs.getBoolean(PREF_EXPLORATION_ACTIVE, false);
  }

  private void scheduleAutomation(final JSONObject response, final JSONObject recommendation) {
    mainHandler.post(new Runnable() {
      @Override
      public void run() {
        handleAutomation(response, recommendation);
      }
    });
  }

  private void handleAutomation(JSONObject response, JSONObject recommendation) {
    String phase = response.optString("phase", "guide");
    if ("guiding".equals(phase) || "destination_reached".equals(phase) || "stopped".equals(phase)) {
      return;
    }

    JSONObject automation = response.optJSONObject("automation");
    if (automation == null || !automation.optBoolean("safe_to_execute", false)) {
      return;
    }
    String action = automation.optString("action", "none");
    if ("none".equals(action) && "exploring".equals(phase)) {
      // The API uses a safe no-op only for a bounded re-observation of a
      // just-opened detail whose web-backed accessibility content is still
      // loading. The server records the attempt and will not request an
      // unbounded loop; the phone merely captures the settled tree once more.
      int actionCount = automation.optInt("action_count", -1);
      if (actionCount < 0 || actionCount == lastNoOpRescheduledActionCount) {
        Log.w(LOG_TAG, "suppressed repeated no-op re-observation actionCount=" + actionCount);
        return;
      }
      lastNoOpRescheduledActionCount = actionCount;
      boundedReobserveNotBeforeElapsedMs = SystemClock.elapsedRealtime() + 2600L;
      schedulePostAutomationAnalysis(2600L);
      return;
    }
    if ("click".equals(action)) {
      if (!"exploring".equals(phase) || recommendation == null) {
        return;
      }
      String elementId = automation.optString("selected_element_id", "");
      String recommendationElementId = recommendation.optString("selected_element_id", "");
      String risk = recommendation.optString("risk_level", "blocked");
      boolean confirmation = recommendation.optBoolean("requires_user_confirmation", true);
      if (elementId.length() == 0 || !elementId.equals(recommendationElementId)
          || !"low".equals(risk) || confirmation) {
        sendIndicator(false, "안전 확인");
        return;
      }
      pendingFromScreen = lastScreenFingerprint;
      pendingPerformedElementId = elementId;
      pendingRecommendationId = recommendation.optString("recommendation_id", "");
      pendingTransitionOutcome = "navigated";
      pendingTransitionSequence = ++transitionSequenceCounter;
      long actionStartedElapsedMs = SystemClock.elapsedRealtime();
      boolean clicked = performExplorationClick(elementId);
      lastActionExecutionMs = Math.max(0L, SystemClock.elapsedRealtime() - actionStartedElapsedMs);
      lastActionCompletedElapsedMs = SystemClock.elapsedRealtime();
      if (!clicked) {
        pendingTransitionOutcome = "failed";
        sendIndicator(true, "");
        schedulePostAutomationAnalysis();
        return;
      }
      schedulePostAutomationAnalysis();
      return;
    }
    if ("scroll_forward".equals(action) && "exploring".equals(phase)) {
      String elementId = automation.optString("selected_element_id", "");
      Log.i(LOG_TAG, "automatic exploration scroll element=" + (elementId.length() > 0));
      long actionStartedElapsedMs = SystemClock.elapsedRealtime();
      boolean scrolled = performExplorationScroll(elementId);
      lastActionExecutionMs = Math.max(0L, SystemClock.elapsedRealtime() - actionStartedElapsedMs);
      lastActionCompletedElapsedMs = SystemClock.elapsedRealtime();
      Log.i(LOG_TAG, "automatic exploration scroll completed=" + scrolled);
      schedulePostAutomationAnalysis();
      return;
    }
    if ("back".equals(action)
        && ("exploring".equals(phase) || "returning_to_start".equals(phase))) {
      Log.i(LOG_TAG, "automatic exploration back phase=" + phase);
      long actionStartedElapsedMs = SystemClock.elapsedRealtime();
      boolean backed = performGlobalAction(GLOBAL_ACTION_BACK);
      lastActionExecutionMs = Math.max(0L, SystemClock.elapsedRealtime() - actionStartedElapsedMs);
      lastActionCompletedElapsedMs = SystemClock.elapsedRealtime();
      if (backed) {
        schedulePostAutomationAnalysis();
      } else {
        sendIndicator(false, "뒤로가기");
      }
    }
  }

  private boolean performExplorationClick(String elementId) {
    if (!"explore".equals(activeOperationMode)) {
      return false;
    }
    AccessibilityNodeInfo root = getRootInActiveWindow();
    if (root == null) {
      return false;
    }
    AccessibilityNodeInfo target = null;
    try {
      target = findNodeByStableId(root, elementId);
      if (target == null || !target.isVisibleToUser() || !target.isEnabled() || !target.isClickable()
          || target.isCheckable() || target.isEditable() || target.isPassword()) {
        Rect cachedBounds = lastClickableBounds.get(elementId);
        boolean fallbackDispatched = dispatchTapAtBounds(cachedBounds);
        Log.i(
          LOG_TAG,
          "automatic exploration click cachedBounds=" + fallbackDispatched
            + " elementId=" + elementId
            + " nodeFound=" + (target != null)
        );
        return fallbackDispatched;
      }
      if (target.performAction(AccessibilityNodeInfo.ACTION_CLICK)) {
        Log.i(LOG_TAG, "automatic exploration click nodeAction=true elementId=" + elementId);
        return true;
      }
      if (Build.VERSION.SDK_INT < Build.VERSION_CODES.N) {
        return false;
      }
      Rect bounds = new Rect();
      target.getBoundsInScreen(bounds);
      boolean dispatched = dispatchTapAtBounds(bounds);
      Log.i(LOG_TAG, "automatic exploration click gesture=" + dispatched + " elementId=" + elementId);
      return dispatched;
    } finally {
      if (target != null) {
        target.recycle();
      }
      root.recycle();
    }
  }

  private boolean dispatchTapAtBounds(Rect bounds) {
    if (Build.VERSION.SDK_INT < Build.VERSION_CODES.N || bounds == null || bounds.isEmpty()) {
      return false;
    }
    int screenWidth = getResources().getDisplayMetrics().widthPixels;
    int screenHeight = getResources().getDisplayMetrics().heightPixels;
    float centerX = bounds.exactCenterX();
    float centerY = bounds.exactCenterY();
    if (centerX < 0 || centerX >= screenWidth || centerY < 0 || centerY >= screenHeight) {
      return false;
    }
    Path tapPath = new Path();
    tapPath.moveTo(centerX, centerY);
    GestureDescription.StrokeDescription tap =
      new GestureDescription.StrokeDescription(tapPath, 0L, 80L);
    GestureDescription gesture = new GestureDescription.Builder().addStroke(tap).build();
    return dispatchGesture(gesture, null, null);
  }

  private boolean performExplorationScroll(String elementId) {
    AccessibilityNodeInfo root = getRootInActiveWindow();
    if (root == null) {
      return false;
    }
    AccessibilityNodeInfo target = null;
    try {
      if (elementId != null && elementId.length() > 0) {
        target = findNodeByStableId(root, elementId);
      }
      if (target == null) {
        target = findScrollableNode(root);
      }
      if (dispatchExplorationPageScroll(target)) {
        return true;
      }
      if (target != null && target.isVisibleToUser() && target.isEnabled()
          && target.performAction(AccessibilityNodeInfo.ACTION_SCROLL_FORWARD)) {
        Log.i(LOG_TAG, "automatic exploration page scroll fallback nodeAction=true");
        return true;
      }
      return false;
    } finally {
      if (target != null) {
        target.recycle();
      }
      root.recycle();
    }
  }

  private boolean dispatchExplorationPageScroll(AccessibilityNodeInfo target) {
    if (Build.VERSION.SDK_INT < Build.VERSION_CODES.N) {
      return false;
    }
    int width = getResources().getDisplayMetrics().widthPixels;
    int height = getResources().getDisplayMetrics().heightPixels;
    int safeTop = Math.round(height * 0.08f);
    int safeBottom = Math.round(height * 0.92f);
    Rect viewport = new Rect(0, safeTop, width, safeBottom);
    if (target != null && target.isVisibleToUser() && target.isEnabled()) {
      Rect targetBounds = new Rect();
      target.getBoundsInScreen(targetBounds);
      int clippedTop = Math.max(safeTop, targetBounds.top);
      int clippedBottom = Math.min(safeBottom, targetBounds.bottom);
      if (clippedBottom - clippedTop >= height * PAGE_SCROLL_MIN_VIEWPORT_RATIO) {
        viewport.set(
          Math.max(0, targetBounds.left),
          clippedTop,
          Math.min(width, targetBounds.right),
          clippedBottom
        );
      }
    }
    float viewportHeight = viewport.height();
    float startY = viewport.bottom - viewportHeight * PAGE_SCROLL_EDGE_MARGIN_RATIO;
    float endY = viewport.top + viewportHeight * PAGE_SCROLL_EDGE_MARGIN_RATIO;
    if (startY - endY < height * 0.25f) {
      return false;
    }
    float centerX = Math.max(
      width * 0.12f,
      Math.min(width * 0.88f, viewport.exactCenterX())
    );
    Path swipePath = new Path();
    swipePath.moveTo(centerX, startY);
    swipePath.lineTo(centerX, endY);
    GestureDescription.StrokeDescription swipe =
      new GestureDescription.StrokeDescription(swipePath, 0L, PAGE_SCROLL_DURATION_MS);
    GestureDescription gesture = new GestureDescription.Builder().addStroke(swipe).build();
    boolean dispatched = dispatchGesture(gesture, null, null);
    Log.i(
      LOG_TAG,
      "automatic exploration page scroll gesture=" + dispatched
        + " displacementPx=" + Math.round(startY - endY)
        + " overlapRatio=" + (PAGE_SCROLL_EDGE_MARGIN_RATIO * 2f)
    );
    return dispatched;
  }

  private AccessibilityNodeInfo findScrollableNode(AccessibilityNodeInfo node) {
    if (node.isScrollable()
        || node.getActionList().contains(AccessibilityNodeInfo.AccessibilityAction.ACTION_SCROLL_FORWARD)) {
      return AccessibilityNodeInfo.obtain(node);
    }
    for (int index = 0; index < node.getChildCount(); index += 1) {
      AccessibilityNodeInfo child = node.getChild(index);
      if (child == null) {
        continue;
      }
      try {
        AccessibilityNodeInfo match = findScrollableNode(child);
        if (match != null) {
          return match;
        }
      } finally {
        child.recycle();
      }
    }
    return null;
  }

  private AccessibilityNodeInfo findNodeByStableId(AccessibilityNodeInfo node, String elementId) {
    if (elementId.equals(stableNodeId(node))) {
      return AccessibilityNodeInfo.obtain(node);
    }
    for (int index = 0; index < node.getChildCount(); index += 1) {
      AccessibilityNodeInfo child = node.getChild(index);
      if (child == null) {
        continue;
      }
      try {
        AccessibilityNodeInfo match = findNodeByStableId(child, elementId);
        if (match != null) {
          return match;
        }
      } finally {
        child.recycle();
      }
    }
    return null;
  }

  private void schedulePostAutomationAnalysis() {
    schedulePostAutomationAnalysis(760L);
  }

  private void schedulePostAutomationAnalysis(long delayMs) {
    mainHandler.postDelayed(new Runnable() {
      @Override
      public void run() {
        scheduleAnalysis(true);
      }
    }, Math.max(0L, delayMs));
  }

  private void publishOverlayState(JSONObject response, JSONObject recommendation) {
    String phase = response.optString("phase", "guide");
    if ("destination_reached".equals(phase)) {
      String label = recommendation == null ? "" : recommendation.optString("selected_label", "").trim();
      sendIndicator(
        false,
        label.length() == 0 ? "완료" : label,
        true,
        ExitGuideOverlayService.FINISH_REASON_DESTINATION_REACHED
      );
      return;
    }
    if ("stopped".equals(phase)) {
      sendIndicator(
        false,
        "못 찾음",
        true,
        ExitGuideOverlayService.FINISH_REASON_STOPPED_NOT_FOUND
      );
      return;
    }
    if ("exploring".equals(phase) || "returning_to_start".equals(phase)) {
      sendIndicator(true, "");
      return;
    }
    if (recommendation != null) {
      String label = recommendation.optString("selected_label", "").trim();
      if (label.length() > 0) {
        sendIndicator(false, label);
        return;
      }
    }
    sendIndicator(false, "완료");
  }

  private void appendNode(
    AccessibilityNodeInfo node,
    String parentId,
    JSONArray elements,
    int[] counter
  ) throws Exception {
    if (node == null || counter[0] >= MAX_NODES || !node.isVisibleToUser()) {
      return;
    }
    Rect bounds = new Rect();
    node.getBoundsInScreen(bounds);
    int screenWidth = getResources().getDisplayMetrics().widthPixels;
    int screenHeight = getResources().getDisplayMetrics().heightPixels;
    boolean onScreen = !bounds.isEmpty()
      && bounds.right > 0
      && bounds.bottom > 0
      && bounds.left < screenWidth
      && bounds.top < screenHeight;
    if (!onScreen) {
      for (int index = 0; index < node.getChildCount() && counter[0] < MAX_NODES; index += 1) {
        AccessibilityNodeInfo child = node.getChild(index);
        if (child == null) {
          continue;
        }
        try {
          appendNode(child, parentId, elements, counter);
        } finally {
          child.recycle();
        }
      }
      return;
    }
    String id = stableNodeId(node);
    boolean privateInput = node.isPassword() || node.isEditable();
    JSONObject element = new JSONObject();
    element.put("id", id);
    if (parentId != null) {
      element.put("parent_id", parentId);
    }
    if (!privateInput && node.getText() != null) {
      element.put("text", clean(node.getText().toString()));
    }
    if (!privateInput && node.getContentDescription() != null) {
      element.put("content_description", clean(node.getContentDescription().toString()));
    }
    if (node.getViewIdResourceName() != null) {
      element.put("view_id", node.getViewIdResourceName());
    }
    element.put("role", roleFor(node));
    element.put("clickable", node.isClickable());
    element.put("enabled", node.isEnabled());
    element.put("visible", node.isVisibleToUser());
    element.put(
      "scrollable",
      node.isScrollable()
        || node.getActionList().contains(AccessibilityNodeInfo.AccessibilityAction.ACTION_SCROLL_FORWARD)
    );
    element.put("checkable", node.isCheckable());
    if (node.isCheckable()) {
      element.put("checked", node.isChecked());
    }
    element.put("selected", node.isSelected());
    element.put("password", privateInput);
    JSONArray box = new JSONArray();
    box.put(bounds.left);
    box.put(bounds.top);
    box.put(bounds.right);
    box.put(bounds.bottom);
    element.put("bounds", box);
    elements.put(element);
    counter[0] += 1;

    for (int index = 0; index < node.getChildCount() && counter[0] < MAX_NODES; index += 1) {
      AccessibilityNodeInfo child = node.getChild(index);
      if (child == null) {
        continue;
      }
      try {
        appendNode(child, id, elements, counter);
      } finally {
        child.recycle();
      }
    }
  }

  private String stableNodeId(AccessibilityNodeInfo node) {
    Rect bounds = new Rect();
    node.getBoundsInScreen(bounds);
    String source = clean(node.getViewIdResourceName()) + "|"
      + clean(node.getClassName() == null ? "" : node.getClassName().toString()) + "|"
      + clean(node.isPassword() || node.isEditable() || node.getText() == null ? "" : node.getText().toString()) + "|"
      + clean(node.isPassword() || node.isEditable() || node.getContentDescription() == null
        ? "" : node.getContentDescription().toString()) + "|"
      + bounds.flattenToString();
    return "an_" + sha256(source).substring(0, 20);
  }

  private String roleFor(AccessibilityNodeInfo node) {
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P && node.isHeading()) {
      return "heading";
    }
    String className = node.getClassName() == null ? "" : node.getClassName().toString().toLowerCase(Locale.ROOT);
    if (className.contains("button")) return "button";
    if (className.contains("switch")) return "switch";
    if (className.contains("checkbox")) return "checkbox";
    if (className.contains("radiobutton")) return "radio";
    if (className.contains("edittext")) return "input";
    if (className.contains("recyclerview") || className.contains("listview")) return "list";
    if (className.contains("image")) return "image";
    if (node.isClickable()) return "button";
    return "text";
  }

  private String firstReadableLabel(JSONArray elements) {
    for (int index = 0; index < elements.length(); index += 1) {
      JSONObject item = elements.optJSONObject(index);
      if (item == null) continue;
      String text = item.optString("text", "");
      if (text.length() > 0) return text;
      String description = item.optString("content_description", "");
      if (description.length() > 0) return description;
    }
    return lastActivityName;
  }

  private void indexClickableElements(JSONArray elements) {
    lastClickableElementIds.clear();
    lastClickableBounds.clear();
    ambiguousClickableKeys.clear();
    Map<String, JSONObject> elementsById = new HashMap<>();
    for (int index = 0; index < elements.length(); index += 1) {
      JSONObject item = elements.optJSONObject(index);
      if (item == null) {
        continue;
      }
      String itemId = item.optString("id", "");
      if (itemId.length() > 0) {
        elementsById.put(itemId, item);
        if (item.optBoolean("clickable", false)
            && item.optBoolean("enabled", false)
            && item.optBoolean("visible", false)
            && !item.optBoolean("checkable", false)
            && !item.optBoolean("password", false)) {
          Rect bounds = boundsFor(item);
          if (bounds != null && !bounds.isEmpty()) {
            lastClickableBounds.put(itemId, new Rect(bounds));
          }
        }
      }
    }
    for (int index = 0; index < elements.length(); index += 1) {
      JSONObject item = elements.optJSONObject(index);
      if (item == null) {
        continue;
      }
      String clickableAncestorId = nearestClickableElementId(item, elementsById);
      if (clickableAncestorId.length() == 0) {
        continue;
      }
      // Android frequently emits TYPE_VIEW_CLICKED for a clickable container
      // while putting its readable label only on a non-clickable child.
      addClickableKey("description", item.optString("content_description", ""), clickableAncestorId);
      addClickableKey("text", item.optString("text", ""), clickableAncestorId);
      addClickableKey("view", item.optString("view_id", ""), clickableAncestorId);
    }
  }

  private String nearestClickableElementId(
    JSONObject item,
    Map<String, JSONObject> elementsById
  ) {
    JSONObject cursor = item;
    Set<String> visited = new HashSet<>();
    while (cursor != null) {
      String cursorId = cursor.optString("id", "");
      if (cursorId.length() == 0 || !visited.add(cursorId)) {
        return "";
      }
      if (cursor.optBoolean("clickable", false)) {
        return cursorId;
      }
      String parentId = cursor.optString("parent_id", "");
      cursor = parentId.length() == 0 ? null : elementsById.get(parentId);
    }
    return "";
  }

  private void addClickableKey(String kind, String value, String elementId) {
    String cleaned = clean(value).toLowerCase(Locale.ROOT);
    if (cleaned.length() == 0 || elementId.length() == 0) {
      return;
    }
    String key = kind + "|" + cleaned;
    if (ambiguousClickableKeys.contains(key)) {
      return;
    }
    String existing = lastClickableElementIds.get(key);
    if (existing != null && !existing.equals(elementId)) {
      lastClickableElementIds.remove(key);
      ambiguousClickableKeys.add(key);
      return;
    }
    lastClickableElementIds.put(key, elementId);
  }

  private String elementIdForEvent(AccessibilityEvent event) {
    if (event.getContentDescription() != null) {
      String match = lastClickableElementIds.get(
        "description|" + clean(event.getContentDescription().toString()).toLowerCase(Locale.ROOT)
      );
      if (match != null) {
        return match;
      }
    }
    for (CharSequence text : event.getText()) {
      if (text == null) {
        continue;
      }
      String match = lastClickableElementIds.get(
        "text|" + clean(text.toString()).toLowerCase(Locale.ROOT)
      );
      if (match != null) {
        return match;
      }
    }
    return "";
  }

  private String appVersion(String packageName) {
    try {
      PackageInfo info = getPackageManager().getPackageInfo(packageName, 0);
      return info.versionName == null ? "" : info.versionName;
    } catch (Exception ignored) {
      return "";
    }
  }

  private void clearPendingTransition() {
    pendingFromScreen = "";
    pendingPerformedElementId = "";
    pendingRecommendationId = "";
    pendingTransitionOutcome = "navigated";
    pendingTransitionSequence = 0L;
  }

  private void clearPendingTransition(long submittedTransitionSequence) {
    if (submittedTransitionSequence > 0L
        && pendingTransitionSequence == submittedTransitionSequence) {
      clearPendingTransition();
    }
  }

  private String eventTypeName(int eventType) {
    if (eventType == AccessibilityEvent.TYPE_VIEW_CLICKED) return "view_clicked";
    if (eventType == AccessibilityEvent.TYPE_VIEW_SCROLLED) return "view_scrolled";
    if (eventType == AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED) return "window_content_changed";
    return "window_state_changed";
  }

  private void sendIndicator(boolean exploring, String message) {
    sendIndicator(exploring, message, false);
  }

  private void sendIndicator(boolean exploring, String message, boolean finished) {
    sendIndicator(exploring, message, finished, "");
  }

  private void sendIndicator(boolean exploring, String message, boolean finished, String finishReason) {
    Intent guidance = new Intent(ACTION_GUIDANCE);
    guidance.setPackage(getPackageName());
    guidance.putExtra(EXTRA_GUIDANCE, message);
    guidance.putExtra(EXTRA_EXPLORING, exploring);
    guidance.putExtra(EXTRA_FINISHED, finished);
    guidance.putExtra(EXTRA_FINISH_REASON, finishReason);
    sendBroadcast(guidance);
  }

  private boolean isExplorationActive() {
    return getSharedPreferences(PREFS_NAME, MODE_PRIVATE)
      .getBoolean(PREF_EXPLORATION_ACTIVE, false);
  }

  private String readBody(InputStream stream) throws Exception {
    if (stream == null) return "";
    ByteArrayOutputStream output = new ByteArrayOutputStream();
    byte[] buffer = new byte[4096];
    int read;
    while ((read = stream.read(buffer)) != -1) {
      output.write(buffer, 0, read);
    }
    stream.close();
    return output.toString("UTF-8");
  }

  private String normalizeBaseUrl(String value) {
    String base = clean(value);
    while (base.endsWith("/")) {
      base = base.substring(0, base.length() - 1);
    }
    return base;
  }

  private String clean(String value) {
    return value == null ? "" : value.trim().replaceAll("\\\\s+", " ");
  }

  private String sha256(String value) {
    try {
      MessageDigest digest = MessageDigest.getInstance("SHA-256");
      byte[] bytes = digest.digest(value.getBytes(StandardCharsets.UTF_8));
      StringBuilder result = new StringBuilder();
      for (byte item : bytes) {
        result.append(String.format(Locale.ROOT, "%02x", item & 0xff));
      }
      return result.toString();
    } catch (Exception error) {
      return Integer.toHexString(value.hashCode()) + "00000000000000000000";
    }
  }
}
`;
}

module.exports = withExitGuideOverlay;
