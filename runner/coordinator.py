"""One animation lease for the entire crew; no timers or guessed completion.

The renderer advances poses. Only the renderer's final-pose-expired event calls
complete(). A lease is released after the owner has returned to its frozen idle
pose. The next lease is granted by a separate pump(), never inside advance().
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from itertools import count
from typing import Any


@dataclass(frozen=True)
class Request:
    id: int
    owner: str
    payload: Any = None


@dataclass(frozen=True)
class Lease:
    token: int
    request: Request


@dataclass
class Completion:
    token: int
    owner: str
    request_id: int
    frame_count: int
    elapsed_ticks: float


class ActionCoordinator:
    def __init__(self, owners=()):
        self.owners = tuple(dict.fromkeys(owners))
        self.queue: deque[Request] = deque()
        self.active: Lease | None = None
        self.history: list[Completion] = []
        self.events: deque[dict] = deque(maxlen=256)
        self._ids = count(1)
        self._tokens = count(1)
        self.max_active = 0
        self.overlaps = 0
        self.tick = 0  # diagnostic clock only; NEVER used to release a lease

    def register(self, owner):
        if owner not in self.owners:
            self.owners += (owner,)

    def request(self, owner, payload=None):
        self.register(owner)
        item = Request(next(self._ids), owner, payload)
        self.queue.append(item)
        self.events.append({"event": "queued", "id": item.id, "owner": owner,
                            "action": getattr(payload, "name", None)})
        return item

    # Spelling used by the review API.
    enqueue = request

    def pump(self):
        if self.active is not None or not self.queue:
            return None
        item = self.queue.popleft()
        self.active = Lease(next(self._tokens), item)
        self.max_active = max(self.max_active, 1)
        self.events.append({"event": "started", "token": self.active.token,
                            "id": item.id, "owner": item.owner,
                            "action": getattr(item.payload, "name", None)})
        return self.active

    def complete(self, owner, token, *, frame_count, elapsed_ticks):
        lease = self.active
        if lease is None or lease.token != token or lease.request.owner != owner:
            raise RuntimeError("stale or foreign animation completion")
        if frame_count <= 0 or elapsed_ticks <= 0:
            raise ValueError("completion requires actual rendered playback")
        self.history.append(Completion(token, owner, lease.request.id,
                                       frame_count, elapsed_ticks))
        self.events.append({"event": "completed", "token": token,
                            "id": lease.request.id, "owner": owner,
                            "action": getattr(lease.request.payload, "name", None),
                            "frames": frame_count, "ticks": elapsed_ticks})
        self.active = None

    def snapshot(self):
        return {"active": None if self.active is None else {
                    "token": self.active.token, "owner": self.active.request.owner,
                    "request_id": self.active.request.id,
                    "action": getattr(self.active.request.payload, "name", None)},
                "queue": [{"id": r.id, "owner": r.owner,
                           "action": getattr(r.payload, "name", None)} for r in self.queue],
                "completed": len(self.history), "overlaps": self.overlaps,
                "events": list(self.events)[-24:]}
