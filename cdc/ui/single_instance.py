"""单实例：第二次启动时唤醒已有窗口。"""

from __future__ import annotations

import os

from PySide6.QtCore import QObject
from PySide6.QtNetwork import QLocalServer, QLocalSocket


class SingleInstance(QObject):
    def __init__(self) -> None:
        super().__init__()
        user = os.environ.get("USERNAME") or "user"
        self.name = f"CDriveCleaner-{user}"
        self.server = QLocalServer(self)
        self.server.newConnection.connect(self._on_connection)
        self.window = None

    def _probe(self) -> bool:
        socket = QLocalSocket()
        socket.connectToServer(self.name)
        if not socket.waitForConnected(250):
            socket.abort()
            return False
        socket.write(b"show")
        socket.waitForBytesWritten(250)
        socket.disconnectFromServer()
        return True

    def try_listen(self) -> bool:
        if self._probe():
            return False
        if not self.server.listen(self.name):
            QLocalServer.removeServer(self.name)
            if not self.server.listen(self.name):
                return False
        return True

    def activate_existing(self) -> None:
        # _probe 已经发送 show 消息
        return

    def set_window(self, window) -> None:
        self.window = window

    def _on_connection(self) -> None:
        socket = self.server.nextPendingConnection()
        if socket is None:
            return
        socket.readyRead.connect(lambda: self._read(socket))
        socket.disconnected.connect(socket.deleteLater)

    def _read(self, socket: QLocalSocket) -> None:
        data = bytes(socket.readAll()).strip()
        if data != b"show" or self.window is None:
            return
        try:
            if self.window.isMinimized():
                self.window.showNormal()
            self.window.show()
            self.window.raise_()
            self.window.activateWindow()
        except RuntimeError:
            pass
