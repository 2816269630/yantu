"""Durable, single-process Yjs rooms for native documents."""
from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

from pycrdt import Doc


def state_vector_entries(data: bytes) -> dict[int, int]:
    """Decode Yjs state vectors so client ordering does not affect equality."""
    position = 0

    def uint() -> int:
        nonlocal position
        value = 0
        shift = 0
        while position < len(data) and shift <= 63:
            byte = data[position]
            position += 1
            value |= (byte & 0x7f) << shift
            if not byte & 0x80:
                return value
            shift += 7
        raise ValueError('invalid Yjs state vector')

    count = uint()
    if count > 10000:
        raise ValueError('Yjs state vector is too large')
    entries = {}
    for _ in range(count):
        client, clock = uint(), uint()
        if client in entries:
            raise ValueError('duplicate Yjs client')
        entries[client] = clock
    if position != len(data):
        raise ValueError('trailing Yjs state vector data')
    return entries


@dataclass
class Room:
    document: Doc | None = None
    clients: dict = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class CollaborationHub:
    def __init__(self, uploads: Path):
        self.directory = uploads / '.collaboration'
        self.rooms: dict[str, Room] = {}
        self.lock = asyncio.Lock()

    def path(self, resource_id: str) -> Path:
        return self.directory / f'{resource_id}.bin'

    async def room(self, resource_id: str) -> Room:
        async with self.lock:
            room = self.rooms.get(resource_id)
            if room is None:
                room = Room()
                path = self.path(resource_id)
                if path.is_file():
                    room.document = Doc()
                    room.document.apply_update(path.read_bytes())
                self.rooms[resource_id] = room
            return room

    def save(self, resource_id: str, document: Doc) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.path(resource_id)
        temporary = self.directory / f'.{resource_id}.{uuid4().hex}.tmp'
        try:
            with temporary.open('wb') as stream:
                stream.write(document.get_update())
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
