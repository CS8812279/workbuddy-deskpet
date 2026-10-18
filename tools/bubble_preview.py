"""气泡样式自检：渲染三种内容，存 assets/preview/bubble.png。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QPoint, QRect, QTimer  # noqa: E402
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from ui.bubble import Bubble  # noqa: E402


def main() -> int:
    app = QApplication(sys.argv)
    cases = [
        ("需要你确认 · 桌宠", "Bash：pip install -r requirements.txt", "#FF8A73"),
        ("", "再来一下嘛", "#8FE7FF"),
        ("完成 · 生成四版游戏策划案", "耗时 2 分 14 秒，产出 4 份文档", "#7BE38F"),
    ]
    shots = []
    anchor = QRect(0, 0, 200, 200)
    for title, text, accent in cases:
        b = Bubble()
        b.show_text(title, text, anchor, seconds=0, accent=accent)
        app.processEvents()
        img = QImage(b.size(), QImage.Format_ARGB32)
        img.fill(QColor(22, 26, 38))
        p = QPainter(img)
        b.render(p, QPoint(0, 0))
        p.end()
        shots.append(img)
        b.hide()

    pad = 14
    w = max(i.width() for i in shots) + pad * 2
    h = sum(i.height() for i in shots) + pad * (len(shots) + 1)
    sheet = QImage(w, h, QImage.Format_ARGB32)
    sheet.fill(QColor(22, 26, 38))
    p = QPainter(sheet)
    y = pad
    for i in shots:
        p.drawImage(pad, y, i)
        y += i.height() + pad
    p.end()
    sheet.save(str(ROOT / "assets" / "preview" / "bubble.png"))
    print("saved", sheet.size())
    QTimer.singleShot(0, app.quit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
