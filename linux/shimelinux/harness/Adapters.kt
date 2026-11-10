// SPDX-License-Identifier: BSD-3-Clause
// Headless test adapters ONLY. The production patch never uses this file.
package com.group_finity.mascot

import com.group_finity.mascot.config.Configuration
import com.group_finity.mascot.environment.*
import com.group_finity.mascot.image.*
import java.awt.Component
import java.awt.Point
import java.awt.Rectangle
import java.awt.image.BufferedImage
import java.io.InputStream
import java.nio.file.Path
import java.util.Properties
import java.util.ResourceBundle
import javax.swing.JPanel
import kotlin.io.path.Path as fsPath

object Main {
    val properties = Properties()
    val languageBundle: ResourceBundle = ResourceBundle.getBundle("conf.language")
    val configurations = mutableMapOf<String, Configuration>()
    fun getConfiguration(name: String): Configuration = configurations.getValue(name)
    fun hasConfiguration(name: String): Boolean = configurations.containsKey(name)
    fun showError(message: String, error: Throwable) { throw error }
    fun createMascot(name: String) {}
    fun setMascotBehaviorEnabled(name: String, mascot: Mascot, enabled: Boolean) {}
    fun exit() {}
}

fun getPath(vararg subpaths: String): Path =
    fsPath(System.getProperty("ava.testRoot"), *subpaths)
fun loadResource(path: String): InputStream? = Main::class.java.getResourceAsStream("/$path")
inline fun <reified T> getProperty(key: String, defaultValue: T): T =
    Main.properties.getProperty(key, defaultValue.toString()).let { value ->
        when (T::class) {
            Int::class -> value.toInt()
            Double::class -> value.toDouble()
            Boolean::class -> value.toBoolean()
            else -> value
        } as? T ?: defaultValue
    }
fun localize(key: String): String =
    if (Main.languageBundle.containsKey(key)) Main.languageBundle.getString(key) else key

val currentEnvironment = "headless-test"

abstract class NativeFactory {
    abstract val environment: Environment
    abstract fun newTranslucentWindow(): TranslucentWindow
    abstract fun newNativeImage(src: BufferedImage): NativeImage
    companion object { lateinit var instance: NativeFactory }
}

class TestImage(val image: BufferedImage) : NativeImage
class TestWindow : TranslucentWindow {
    private val panel = JPanel()
    var displayed: BufferedImage? = null
    var updates = 0
    override fun asComponent(): Component = panel
    override fun setImage(image: NativeImage) { displayed = (image as TestImage).image }
    override fun updateImage() { updates++ }
    override fun setAlwaysOnTop(value: Boolean) {}
    override fun dispose() {}
}

class TestEnvironment : Environment() {
    override val workArea = Area().apply { set(Rectangle(0, 0, 1920, 1080)) }
    override val activeIE = Area().apply { isVisible = false }
    override val activeIETitle = ""
    override fun tick() {
        screen.set(workArea.toRectangle())
        complexScreen.set(mapOf("test" to workArea.toRectangle()))
        cursor.set(Point(960, 540))
    }
    override fun moveActiveIE(point: Point) {}
    override fun restoreIE() {}
    override fun refreshCache() {}
    override fun dispose() {}
}

class TestNativeFactory : NativeFactory() {
    override val environment = TestEnvironment()
    val windows = mutableMapOf<Mascot, TestWindow>()
    override fun newTranslucentWindow(): TranslucentWindow = TestWindow()
    override fun newNativeImage(src: BufferedImage): NativeImage = TestImage(src)
}

class DebugWindow(imageSet: String) {
    var isVisible = true
    fun set(vararg values: Any?) {}
}
