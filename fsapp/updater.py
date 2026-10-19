"""Checks GitHub for a newer release of the program."""
import json
import re

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from .version import BUILD, REPO

API = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"


def parse_release(data):
    """Return (build number, notes, download url) from the GitHub release JSON, or None."""
    m = re.search(r"(\d+)$", data.get("tag_name") or "")
    if not m:
        return None
    url = next((a.get("browser_download_url") for a in data.get("assets") or []
                if (a.get("name") or "").lower().endswith(".zip")), None)
    return int(m.group(1)), (data.get("body") or "").strip(), url or data.get("html_url") or RELEASES_PAGE


def is_newer(latest_build, current=BUILD):
    return current > 0 and latest_build > current


class UpdateChecker(QObject):
    """result(newer: bool, build: int, notes: str, url: str) — or failed(message)."""
    result = Signal(bool, int, str, str)
    failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.net = QNetworkAccessManager(self)
        self.net.finished.connect(self._done)

    def check(self):
        req = QNetworkRequest(QUrl(API))
        req.setRawHeader(b"Accept", b"application/vnd.github+json")
        req.setRawHeader(b"User-Agent", b"FinancialStatements")
        req.setTransferTimeout(10000)
        self.net.get(req)

    def _done(self, reply):
        try:
            if reply.error() != QNetworkReply.NoError:
                self.failed.emit(reply.errorString())
                return
            info = parse_release(json.loads(bytes(reply.readAll()).decode("utf-8")))
            if not info:
                self.failed.emit("لا توجد إصدارات منشورة بعد.")
                return
            build, notes, url = info
            self.result.emit(is_newer(build), build, notes, url)
        except (ValueError, KeyError) as e:
            self.failed.emit(str(e))
        finally:
            reply.deleteLater()
