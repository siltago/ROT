package com.robotbrain.tablet

import android.content.Context
import android.media.AudioManager
import android.os.Bundle
import android.provider.Settings
import android.view.WindowInsets
import android.view.WindowInsetsController
import android.view.WindowManager
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.R) {
            window.insetsController?.apply {
                hide(WindowInsets.Type.systemBars())
                systemBarsBehavior = WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
            }
        } else {
            @Suppress("DEPRECATION")
            window.decorView.systemUiVisibility = 5894
        }
    }

    // Small hardware controls Bob may use on the device he lives on (see
    // lib/devices/device_controls.dart): media volume and screen brightness,
    // both as 0..100 percentages. Brightness is set on this window only
    // (no WRITE_SETTINGS permission needed) and reverts with the app.
    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "robotbrain/device")
            .setMethodCallHandler { call, result ->
                val audio = getSystemService(Context.AUDIO_SERVICE) as AudioManager
                when (call.method) {
                    "getState" -> result.success(
                        mapOf("volume" to volumePercent(audio), "brightness" to brightnessPercent())
                    )
                    "setVolume" -> {
                        val percent = (call.argument<Int>("percent") ?: 50).coerceIn(0, 100)
                        val max = audio.getStreamMaxVolume(AudioManager.STREAM_MUSIC)
                        audio.setStreamVolume(
                            AudioManager.STREAM_MUSIC, Math.round(max * percent / 100f), 0
                        )
                        result.success(volumePercent(audio))
                    }
                    "setBrightness" -> {
                        val percent = (call.argument<Int>("percent") ?: 50).coerceIn(5, 100)
                        val attrs = window.attributes
                        attrs.screenBrightness = percent / 100f
                        window.attributes = attrs
                        result.success(percent)
                    }
                    else -> result.notImplemented()
                }
            }
    }

    private fun volumePercent(audio: AudioManager): Int {
        val max = audio.getStreamMaxVolume(AudioManager.STREAM_MUSIC)
        if (max <= 0) return 0
        return Math.round(audio.getStreamVolume(AudioManager.STREAM_MUSIC) * 100f / max)
    }

    private fun brightnessPercent(): Int {
        val current = window.attributes.screenBrightness
        if (current >= 0f) return Math.round(current * 100f)
        return try {
            Math.round(Settings.System.getInt(contentResolver, Settings.System.SCREEN_BRIGHTNESS) * 100f / 255f)
        } catch (e: Settings.SettingNotFoundException) {
            50
        }
    }
}
