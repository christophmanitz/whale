#!/usr/bin/env python3
"""Terminal-Server: WebSocket ↔ PTY Bridge für opencode im Projektordner."""

import asyncio
import fcntl
import json
import os
import pty
import select
import signal
import struct
import subprocess

import websockets

PROJECT_DIR = os.path.expanduser("~/projects/latex-studio/projects/default")
PORT = 8762


def set_winsize(fd: int, row: int, col: int, xpix: int = 0, ypix: int = 0) -> None:
    """Setzt die Terminal-Grösse im PTY."""
    winsize = struct.pack("HHHH", row, col, xpix, ypix)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)


async def handle_terminal(websocket: websockets.WebSocketServerProtocol) -> None:
    """Spawned opencode im PTY und bridged WebSocket ↔ PTY."""
    master_fd, slave_fd = pty.openpty()

    # Terminal-Grösse im PTY setzen (80x24 default)
    set_winsize(master_fd, 24, 80)

    proc = subprocess.Popen(
        ["opencode"],
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        cwd=PROJECT_DIR,
        preexec_fn=os.setsid,  # Neue Session (für sauberes Killen)
    )

    # PTY-Reader: liest Output vom opencode und schickt ihn via WebSocket
    async def read_pty():
        loop = asyncio.get_event_loop()
        while True:
            try:
                data = await loop.run_in_executor(None, lambda: os.read(master_fd, 4096))
                if not data:
                    break
                await websocket.send(data.decode("utf-8", errors="replace"))
            except (OSError, websockets.exceptions.ConnectionClosed):
                break

    # WebSocket-Reader: liest Input vom User und schreibt ihn ins PTY
    async def ws_reader():
        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    if data.get("type") == "resize":
                        set_winsize(master_fd, data.get("rows", 24), data.get("cols", 80))
                        os.killpg(proc.pid, signal.SIGWINCH)
                except json.JSONDecodeError:
                    os.write(master_fd, message.encode())
        except websockets.exceptions.ConnectionClosed:
            pass

    await asyncio.gather(read_pty(), ws_reader())

    # Aufräumen
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass


async def main():
    async with websockets.serve(handle_terminal, "localhost", PORT):
        print(f"Terminal-Server läuft auf ws://localhost:{PORT}")
        await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Terminal-Server beendet.")
