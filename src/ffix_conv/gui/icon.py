"""The application icon, drawn in code for this project: a pale crystal on a deep-blue tile with two
exchange arrows. It is FFIX-inspired in palette only and uses no Square Enix artwork or logos."""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QPolygonF

NAVY, BLUE, GOLD, ICE = QColor("#14215a"), QColor("#3d63b5"), QColor("#e8c46a"), QColor("#dff4ff")


def pixmap(size):
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    s = size / 64.0
    bg = QLinearGradient(0, 0, 0, size)
    bg.setColorAt(0, BLUE)
    bg.setColorAt(1, NAVY)
    p.setPen(QPen(GOLD, max(1.0, 1.6 * s)))
    p.setBrush(bg)
    p.drawRoundedRect(QRectF(1.5 * s, 1.5 * s, 61 * s, 61 * s), 12 * s, 12 * s)

    # crystal: an elongated octahedron seen from the side, light and dark facets
    top, bottom, left, right, mid_y = (32, 9), (32, 55), (21, 30), (43, 30), 30
    pts = lambda *xy: QPolygonF([QPointF(x * s, y * s) for x, y in xy])
    p.setPen(QPen(QColor("#9fd3f0"), max(1.0, 0.8 * s)))
    p.setBrush(ICE)
    p.drawPolygon(pts(top, left, (32, mid_y + 4)))
    p.setBrush(QColor("#b5e2fa"))
    p.drawPolygon(pts(top, right, (32, mid_y + 4)))
    p.setBrush(QColor("#7fc0e8"))
    p.drawPolygon(pts(left, bottom, (32, mid_y + 4)))
    p.setBrush(QColor("#5aa6db"))
    p.drawPolygon(pts(right, bottom, (32, mid_y + 4)))

    # exchange arrows (PS1 <-> PC)
    pen = QPen(GOLD, max(1.2, 2.6 * s), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    for sweep, start, tip in ((-70, 200, (9.5, 41)), (-70, 20, (54.5, 23))):
        path = QPainterPath()
        path.arcMoveTo(QRectF(8 * s, 8 * s, 48 * s, 48 * s), start)
        path.arcTo(QRectF(8 * s, 8 * s, 48 * s, 48 * s), start, sweep)
        p.drawPath(path)
    p.setBrush(GOLD)
    p.setPen(Qt.NoPen)
    p.drawPolygon(pts((13, 46), (19, 44), (12, 39)))
    p.drawPolygon(pts((51, 18), (45, 20), (52, 25)))
    p.end()
    return pm


def app_icon():
    icon = QIcon()
    for n in (16, 20, 24, 32, 40, 48, 64, 128, 256):
        icon.addPixmap(pixmap(n))
    return icon


def write_ico(path):
    """Write a multi-size .ico for the Windows executable (used by the build)."""
    import struct
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice
    images = []
    for n in (16, 24, 32, 48, 64, 128, 256):
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.WriteOnly)
        pixmap(n).save(buf, "PNG")
        images.append((n, bytes(ba)))
    out = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    for n, data in images:
        out += struct.pack("<BBBBHHII", n % 256, n % 256, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    with open(path, "wb") as f:
        f.write(out + b"".join(d for _, d in images))
