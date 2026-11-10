// SPDX-License-Identifier: BSD-3-Clause
// Headless playback/coordination harness. Compile with harness/build_subset.py.
import com.group_finity.mascot.*
import com.group_finity.mascot.config.*
import java.awt.Color
import java.awt.Point
import java.awt.RenderingHints
import java.awt.image.BufferedImage
import java.io.File
import java.util.logging.Level
import java.util.logging.Logger
import javax.imageio.ImageIO
import javax.xml.parsers.DocumentBuilderFactory

fun main(args: Array<String>) {
    val repo = File(args.getOrElse(0) { "." }).canonicalFile
    val output = File(args.getOrElse(1) { "preview/native" }).canonicalFile
    output.mkdirs()
    val framesDir = File(output, "frames").apply { mkdirs() }
    System.setProperty("ava.testRoot", File(output, "config").absolutePath)
    System.setProperty("ava.scriptBridge", File(repo, "linux/shimelinux/harness/eval-server.js").absolutePath)
    Logger.getLogger("").level = Level.SEVERE
    for (handler in Logger.getLogger("").handlers) handler.level = Level.SEVERE
    Main.properties.setProperty("Scaling", "1.0")
    Main.properties.setProperty("Filter", "Nearest")
    Main.properties.setProperty("Opacity", "1.0")
    Main.properties.setProperty("Multiscreen", "false")
    Main.properties.setProperty("Breeding", "false")
    Main.properties.setProperty("Sounds", "false")
    NativeFactory.instance = TestNativeFactory()

    val names = listOf("Blue", "Orange", "Yellow", "Green")
    val factory = DocumentBuilderFactory.newInstance().apply { isNamespaceAware = true }
    for (name in names) {
        val target = File(output, "config/img/$name")
        target.parentFile.mkdirs()
        if (!target.exists()) {
            java.nio.file.Files.createSymbolicLink(target.toPath(), File(repo, "AVA Shimejis/$name").toPath())
        }
        val config = Configuration()
        for (file in listOf("actions.xml", "behaviors.xml")) {
            val doc = factory.newDocumentBuilder().parse(File(repo, "AVA Shimejis/$name/conf/$file"))
            config.load(Entry(doc.documentElement), name)
        }
        Main.configurations[name] = config
        println("LOADED $name: ${config.behaviorNames.size} behaviors")
    }

    val manager = Manager().apply { isExitOnLastRemoved = false }
    val mascots = names.mapIndexed { index, name ->
        Mascot(name).apply {
            anchor = Point(260 + index * 360, 950)
            behavior = Main.getConfiguration(name).buildBehavior("Fall")
            manager.add(this)
        }
    }
    manager.tick()
    val opening = listOf("Wave", "Dance", "Jump", "Walk")
    for ((index, mascot) in mascots.withIndex()) {
        mascot.behavior = Main.getConfiguration(mascot.imageSet).buildBehavior(opening[index])
    }

    var overlaps = 0
    var idleMovement = 0
    var pauseViolations = 0
    val previousPoint = mascots.map { Point(it.anchor) }.toMutableList()
    val previousBehavior = mascots.map { it.behavior?.behaviorName }.toMutableList()
    val log = File(output, "native-events.tsv").printWriter()
    log.println("tick\tactive\tqueue\tcompleted\tcancelled\t" +
        names.joinToString("\t") { "$it-behavior\t$it-x\t$it-y" })
    val width = 1600
    val height = 420
    for (tick in 1..1200) {
        val pausedToken = manager.turns.active?.token
        val pausedQueue = manager.turns.queueSize
        manager.tick()
        val active = manager.turns.active?.request?.owner
        if (manager.turns.maxActive > 1) overlaps++
        if (tick in 401..430 && (manager.turns.active?.token != pausedToken ||
                manager.turns.queueSize != pausedQueue)) pauseViolations++
        for ((i, mascot) in mascots.withIndex()) {
            if (mascot.manager == null) continue
            if (mascot !== active && mascot.behavior?.behaviorName == "Idle" &&
                previousBehavior[i] == "Idle" && mascot.anchor != previousPoint[i]) idleMovement++
            previousPoint[i] = Point(mascot.anchor)
            previousBehavior[i] = mascot.behavior?.behaviorName
        }
        log.println(listOf(tick, active?.imageSet ?: "-", manager.turns.queueSize,
            manager.turns.completed, manager.turns.cancelled).plus(mascots.flatMap {
                listOf(it.behavior?.behaviorName ?: "-", it.anchor.x, it.anchor.y)
            }).joinToString("\t"))

        if (tick <= 600 && tick % 2 == 0) {
            val image = BufferedImage(width, height, BufferedImage.TYPE_INT_RGB)
            val g = image.createGraphics()
            g.color = Color(24, 26, 32)
            g.fillRect(0, 0, width, height)
            g.color = Color(70, 74, 84)
            g.drawLine(0, 360, width, 360)
            g.setRenderingHint(RenderingHints.KEY_INTERPOLATION, RenderingHints.VALUE_INTERPOLATION_NEAREST_NEIGHBOR)
            for ((i, mascot) in mascots.withIndex()) {
                if (mascot.manager == null) continue
                val pose = mascot.image ?: continue
                val src = (pose.image as TestImage).image
                val x = mascot.anchor.x * width / 1920 - pose.center.x
                val y = 360 + (mascot.anchor.y - 1080) - pose.center.y
                if (mascot === active) {
                    g.color = Color(70, 90, 120)
                    g.fillRect(x - 6, y - 6, src.width + 12, src.height + 12)
                }
                g.drawImage(src, x, y, null)
                g.color = Color(180, 190, 205)
                g.drawString("${names[i]} ${mascot.behavior?.behaviorName ?: "-"}", x, 392)
            }
            g.color = Color(220, 225, 235)
            g.drawString("tick $tick  active=${active?.imageSet ?: "-"}  completed=${manager.turns.completed}  queue=${manager.turns.queueSize}", 12, 20)
            g.dispose()
            ImageIO.write(image, "png", File(framesDir, "frame-${tick / 2}.png"))
        }

        if (tick == 200) mascots[0].behavior = Main.getConfiguration("Blue").buildBehavior("Dragged")
        if (tick == 220) {
            mascots[0].isDragging = false
            mascots[0].behavior = Main.getConfiguration("Blue").buildBehavior("Thrown")
        }
        // Release a queued drag before it is granted: must not leave a stuck lease.
        if (tick == 250) mascots[1].behavior = Main.getConfiguration("Orange").buildBehavior("Dragged")
        if (tick == 251) {
            mascots[1].isDragging = false
            Mascot::class.java.getDeclaredMethod("cancelUnstartedDrag").apply { isAccessible = true }
                .invoke(mascots[1])
        }
        // Menu path: setBehaviorAll must queue, not bypass the active lease.
        if (tick == 650) manager.setBehaviorAll("ChaseMouse")
        if (tick == 400) mascots.forEach { it.isPaused = true }
        if (tick == 430) mascots.forEach { it.isPaused = false }
        if (tick == 1100) mascots[3].dispose()
    }
    log.close()
    check(overlaps == 0) { "overlapping leases" }
    check(idleMovement == 0) { "waiting idle translated" }
    check(pauseViolations == 0) { "pause changed the lease/queue" }
    check(manager.turns.completed > 20) { "too few natural completions: ${manager.turns.completed}" }
    check(manager.count == 3) { "disposed mascot remained managed" }
    val summary = "NATIVE CORE: 1200 ticks, ${manager.turns.completed} completed, " +
        "${manager.turns.cancelled} cancelled; overlaps=$overlaps idleMovement=$idleMovement pauseViolations=$pauseViolations"
    File(output, "summary.txt").writeText(summary + "\n")
    println(summary)
}
