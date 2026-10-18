"""皮肤自检：把五种状态各渲染一帧拼成对照图。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from ui.sprite import load_skin  # noqa: E402

STATES = ["idle", "blink", "working", "done", "alert", "sleep"]


def main() -> int:
    app = QApplication(sys.argv)
    skin = load_skin(ROOT / "assets" / "whale-girl" / "frames")
    if not skin:
        print("没有皮肤")
        return 1
    w, h = skin.size_for(1.0)
    tiles = []
    for state in STATES:
        img = QImage(w, h, QImage.Format_ARGB32_Premultiplied)
        img.fill(Qt.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing, True)
        skin.draw(p, w, h, state, 1.2, blink=1.0 if state != "blink" else 0.0,
                  jump=-18 if state == "done" else 0.0,
                  alert=1.0 if state == "alert" else 0.0)
        p.end()
        tiles.append((state, img))

    pad = 12
    sheet = QImage(w * len(tiles) + pad * (len(tiles) + 1), h + 34, QImage.Format_ARGB32)
    sheet.fill(QColor(26, 30, 42))
    p = QPainter(sheet)
    p.setRenderHint(QPainter.Antialiasing, True)
    for i, (name, img) in enumerate(tiles):
        p.drawImage(pad + i * (w + pad), 30, img)
        p.setPen(QColor(210, 225, 255))
        p.drawText(pad + i * (w + pad), 20, name)
    p.end()
    out = ROOT / "assets" / "whale-girl" / "_skin_states.png"
    sheet.save(str(out))
    print("saved", out, sheet.size())
    app.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
