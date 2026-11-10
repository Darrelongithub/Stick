/*
 * Global animation turn coordination for ShimeLinux.
 * SPDX-License-Identifier: BSD-3-Clause (the ShimeLinux project license).
 */
package com.group_finity.mascot

import java.util.ArrayDeque

/**
 * One process-wide stage, independent of image set and behavior type.
 *
 * The coordinator never guesses completion from a wall-clock timeout.  The
 * behavior adapter calls [complete] only after its action reports hasNext() ==
 * false after the final pose tick.  [cancel] is the separate, explicit path for
 * disposal, removal, lost ground and release from a drag.  A cancelled token can
 * never complete a later lease.
 *
 * All mutation is synchronized because behavior requests can originate on the
 * Swing event thread while the manager timer is ticking.  [pump] is deliberately
 * called by the manager after every mascot has applied its frame: the completing
 * mascot's stationary idle is visible before the next behavior is initialized.
 */
class TurnCoordinator<O : Any> {
    data class Request<O : Any>(val id: Long, val owner: O, val payload: Any)
    data class Lease<O : Any>(val token: Long, val request: Request<O>)
    data class Event<O : Any>(
        val kind: String,
        val owner: O?,
        val requestId: Long?,
        val token: Long?,
        val ticks: Long,
    )

    private val pending = ArrayDeque<Request<O>>()
    private val log = ArrayDeque<Event<O>>()
    private var sequence = 0L
    private var tokens = 0L

    var active: Lease<O>? = null
        @Synchronized get
        private set
    var completed = 0L
        private set
    var cancelled = 0L
        private set
    var maxActive = 0
        private set
    var overlaps = 0
        private set

    val queueSize: Int
        @Synchronized get() = pending.size

    @Synchronized
    fun request(owner: O, payload: Any): Request<O> {
        val request = Request(++sequence, owner, payload)
        pending.addLast(request)
        note("queued", owner, request.id, null, 0)
        return request
    }

    /** Grant at most one request.  Initialization happens only after the lease exists. */
    @Synchronized
    fun pump(start: (Lease<O>) -> Unit): Lease<O>? {
        if (active != null || pending.isEmpty()) return null
        val request = pending.removeFirst()
        val lease = Lease(++tokens, request)
        active = lease
        if (active != null) maxActive = 1
        note("started", request.owner, request.id, lease.token, 0)
        try {
            start(lease)
        } catch (error: Throwable) {
            // The owner adapter normally disposes itself and cancels.  If it
            // cannot, fail closed rather than leaving a poisoned active token.
            if (active?.token == lease.token) {
                active = null
                cancelled++
                note("start-failed", request.owner, request.id, lease.token, 0)
            }
            throw error
        }
        return lease
    }

    /** Natural completion.  The owner is frozen before another request can start. */
    @Synchronized
    fun complete(owner: O, token: Long, elapsedTicks: Long, enterIdle: () -> Unit) {
        val lease = active
        require(lease != null && lease.token == token && lease.request.owner === owner) {
            "stale or foreign animation completion"
        }
        require(elapsedTicks > 0) { "completion requires actual playback" }
        enterIdle()
        active = null
        completed++
        note("completed", owner, lease.request.id, token, elapsedTicks)
    }

    /** Explicit interruption/removal; never reported as natural completion. */
    @Synchronized
    fun cancel(owner: O, reason: String, enterIdle: (() -> Unit)? = null) {
        val before = pending.size
        pending.removeAll { it.owner === owner }
        val lease = active
        if (lease != null && lease.request.owner === owner) {
            enterIdle?.invoke()
            active = null
            cancelled++
            note(reason, owner, lease.request.id, lease.token, 0)
        } else if (before != pending.size) {
            note("$reason-queued", owner, null, null, 0)
        }
    }

    /** Cancel a queued interaction without disturbing the active performer. */
    @Synchronized
    fun cancelQueued(owner: O, predicate: (Request<O>) -> Boolean): Int {
        val matches = pending.filter { it.owner === owner && predicate(it) }
        pending.removeAll { it.owner === owner && predicate(it) }
        for (request in matches) note("cancelled-queued", owner, request.id, null, 0)
        return matches.size
    }

    @Synchronized
    fun snapshot(): Map<String, Any?> = mapOf(
        "active" to active?.let {
            mapOf("token" to it.token, "owner" to it.request.owner.toString(),
                  "request" to it.request.id, "payload" to it.request.payload.toString())
        },
        "queue" to pending.map {
            mapOf("id" to it.id, "owner" to it.owner.toString(), "payload" to it.payload.toString())
        },
        "completed" to completed,
        "cancelled" to cancelled,
        "maxActive" to maxActive,
        "overlaps" to overlaps,
        "events" to log.toList(),
    )

    private fun note(kind: String, owner: O?, requestId: Long?, token: Long?, ticks: Long) {
        log.addLast(Event(kind, owner, requestId, token, ticks))
        while (log.size > 256) log.removeFirst()
    }
}
