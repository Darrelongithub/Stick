/*
 * Stationary waiting idle for ShimeLinux global animation turns.
 * SPDX-License-Identifier: BSD-3-Clause (the ShimeLinux project license).
 */
package com.group_finity.mascot.behavior

import com.group_finity.mascot.Mascot
import com.group_finity.mascot.Main
import com.group_finity.mascot.exception.LostGroundException
import com.group_finity.mascot.exception.VariableException
import java.awt.event.MouseEvent
import javax.swing.SwingUtilities

/**
 * Displays exactly one idle pose and then holds it indefinitely.
 *
 * Construction is deliberately deferred until Mascot.apply(), after the last
 * animated pose has been displayed.  This behavior is installed outside the
 * queue.  It never advances an action, translates the anchor, plays a sound, or
 * requests a turn while another mascot is active.
 */
class StationaryIdle private constructor(private val mascot: Mascot) : Behavior {
    private var initialized = false
    override val behaviorName: String = "Idle"

    fun initialize() {
        if (initialized) return
        initialized = true
        val configuration = Main.getConfiguration(mascot.imageSet)
        val idleName = listOf("WaitIdle", "Idle", "Stand").firstOrNull(configuration::hasAction)
        if (idleName != null) {
            try {
                val action = configuration.buildAction(idleName, emptyMap())
                action.init(mascot)
                if (action.hasNext()) action.next()
            } catch (_: LostGroundException) {
                // Initial spawn can be above the work area.  The first granted
                // Fall restores the mascot; do not bypass the queue here.
            } catch (_: VariableException) {
                // Fail closed: no animation request is made from idle setup.
            }
        }
        mascot.affordances.clear()
        mascot.hotspots.clear()
        mascot.sound = null
        mascot.isDragging = false
    }

    override fun init(mascot: Mascot) {
        // Mascot.apply owns one-time initialization, not the behavior setter.
    }

    override fun next() {
        // Intentionally stationary.  In particular, do not call action.next().
    }

    override fun mousePressed(e: MouseEvent) {
        if (SwingUtilities.isLeftMouseButton(e)) {
            val configuration = Main.getConfiguration(mascot.imageSet)
            mascot.behavior = configuration.buildBehavior(UserBehavior.BEHAVIOURNAME_DRAGGED, mascot)
        }
    }

    override fun mouseReleased(e: MouseEvent) {
        // UserBehavior handles release once a queued drag has actually started.
    }

    override fun toString() = "Behavior[name=$behaviorName]"

    companion object {
        fun deferred(mascot: Mascot) = StationaryIdle(mascot)
    }
}
