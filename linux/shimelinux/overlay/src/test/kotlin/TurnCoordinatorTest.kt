/* SPDX-License-Identifier: BSD-3-Clause (the ShimeLinux project license). */
import com.group_finity.mascot.TurnCoordinator
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNull
import kotlin.test.assertTrue

class TurnCoordinatorTest {
    private class Owner(val name: String) {
        var idle = 0
        var started = mutableListOf<Any>()
        override fun toString() = name
    }

    @Test fun fifoAcrossOwnersAndTypes() {
        val c = TurnCoordinator<Owner>()
        val a = Owner("Blue"); val b = Owner("Orange"); val d = Owner("Green")
        c.request(a, "Walk"); c.request(b, "Dragged"); c.request(d, "FightCombo")
        val first = c.pump { it.request.owner.started += it.request.payload }!!
        assertNull(c.pump { error("must not overlap") })
        assertEquals(listOf<Any>("Walk"), a.started)
        assertEquals(emptyList(), b.started)
        c.complete(a, first.token, 12) { a.idle++ }
        assertEquals(1, a.idle)
        val second = c.pump { it.request.owner.started += it.request.payload }!!
        assertEquals("Dragged", second.request.payload)
        c.cancel(b, "drag-released") { b.idle++ }
        val third = c.pump { it.request.owner.started += it.request.payload }!!
        assertEquals("FightCombo", third.request.payload)
        assertEquals(1, c.maxActive)
        assertEquals(0, c.overlaps)
    }

    @Test fun staleAndForeignCompletionCannotReleaseStage() {
        val c = TurnCoordinator<Owner>()
        val a = Owner("A"); val b = Owner("B")
        val lease = c.run { request(a, "Wave"); pump {} }!!
        assertFailsWith<IllegalArgumentException> { c.complete(b, lease.token, 1) {} }
        assertFailsWith<IllegalArgumentException> { c.complete(a, lease.token + 1, 1) {} }
        assertFailsWith<IllegalArgumentException> { c.complete(a, lease.token, 0) {} }
        c.cancel(a, "removed")
        c.request(b, "Run")
        val next = c.pump {}!!
        assertFailsWith<IllegalArgumentException> { c.complete(a, lease.token, 5) {} }
        c.complete(b, next.token, 5) {}
        assertEquals(1, c.completed)
        assertEquals(1, c.cancelled)
    }

    @Test fun multipleExplicitRequestsKeepTheirOrder() {
        val c = TurnCoordinator<Owner>()
        val a = Owner("A")
        c.request(a, "Wave"); c.request(a, "Jump"); c.request(a, "Run")
        for (name in listOf("Wave", "Jump", "Run")) {
            val lease = c.pump {}!!
            assertEquals(name, lease.request.payload)
            c.complete(a, lease.token, 3) {}
        }
        assertEquals(3, c.completed)
        assertEquals(0, c.queueSize)
    }

    @Test fun removalCancelsQueuedRequestsAndActiveLease() {
        val c = TurnCoordinator<Owner>()
        val a = Owner("A"); val b = Owner("B")
        c.request(a, "Walk"); c.request(a, "Wave"); c.request(b, "Run")
        c.pump {}
        c.cancel(a, "disposed")
        assertEquals(1, c.queueSize)
        assertNull(c.active)
        val lease = c.pump {}!!
        assertEquals(b, lease.request.owner)
    }

    @Test fun releasedBeforeDragStartsCancelsOnlyThatQueuedRequest() {
        val c = TurnCoordinator<Owner>()
        val a = Owner("A"); val b = Owner("B")
        c.request(b, "Walk")
        c.request(a, "Dragged")
        c.request(a, "Wave")
        assertEquals(1, c.cancelQueued(a) { it.payload == "Dragged" })
        val first = c.pump {}!!
        assertEquals(b, first.request.owner)
        c.complete(b, first.token, 2) {}
        assertEquals("Wave", c.pump {}!!.request.payload)
    }

    @Test fun failedInitializationDoesNotPoisonTheQueue() {
        val c = TurnCoordinator<Owner>()
        val a = Owner("A"); val b = Owner("B")
        c.request(a, "Broken"); c.request(b, "Wave")
        assertFailsWith<IllegalStateException> { c.pump { error("bad action") } }
        assertNull(c.active)
        assertEquals("Wave", c.pump {}!!.request.payload)
        assertTrue(c.snapshot()["events"].toString().contains("start-failed"))
    }
}
