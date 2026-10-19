"""面板预览：喂一份假数据，看 DSH 动作行的排版。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QPoint  # noqa: E402
from PySide6.QtGui import QColor, QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from ui.panel import Panel  # noqa: E402

app = QApplication(sys.argv)
p = Panel()
p.set_name("小离")
p.update_data({
    "credits": {"ok": True, "remaining": 4918, "used_today": 330},
    "deepseek": {"ok": True, "balance": 111.41, "today": 2.14, "currency": "CNY"},
    "spark": [500, 900, 300, 700, 800, 450, 60],
    "running": [{"title": "Harness 小红书私信插件", "idle_min": 0}],
    "dsh": [
        {"title": "小红书私信", "idle_min": 0.1,
         "activity": {"kind": "tool", "text": "写文件 · 2026-10-19-柄图.md"}},
        {"title": "你是这个账号的小红书助手", "idle_min": 27, "activity": None},
    ],
    "pending": [],
    "recent": [("done", "完成：帮我在小红书抓5条笔记", "16:12")],
})
app.processEvents()
img = QImage(p.size(), QImage.Format_ARGB32)
img.fill(QColor(16, 20, 30))
painter = QPainter(img)
p.render(painter, QPoint(0, 0))
painter.end()
out = ROOT / "assets" / "preview" / "_panel_dsh.png"
img.save(str(out))
print("saved", p.size(), out)
