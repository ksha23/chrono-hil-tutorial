# =============================================================================
# PROJECT CHRONO - http://projectchrono.org
#
# Copyright (c) 2026 projectchrono.org
# All rights reserved.
#
# Use of this source code is governed by a BSD-style license that can be found
# in the LICENSE file at the top level of the distribution and at
# http://projectchrono.org/license-chrono.txt.
# =============================================================================
"""Input from another process, over a socket. Portable."""

import socket

from ..config import UDP_PORT

class Console:
    def __init__(self, port=UDP_PORT):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("0.0.0.0", port))
        self.sock.setblocking(False)
        self.last = (0.0, 0.0, 0.0)
        self.commands = []
        self.addr = None
        print(f"[udp] listening on {port} - "
              "now run:  python archive/operator_console.py")

    def poll(self):
        while True:
            try:
                data, addr = self.sock.recvfrom(256)
            except BlockingIOError:
                break
            f = data.decode().split(",")
            if len(f) < 3:
                continue
            try:
                self.last = tuple(float(x) for x in f[:3])
            except ValueError:
                continue
            self.addr = addr
            if len(f) > 3 and f[3] and f[3] != "-":
                self.commands.append(f[3][0])
        return self.last

    def take_commands(self):
        c, self.commands = self.commands, []
        return c

    def send(self, text):
        if self.addr:
            self.sock.sendto(text.encode(), self.addr)
