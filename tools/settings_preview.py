"""设置窗口自检：渲染一张截图。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtGui import QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from core import config  # noqa: E402
from ui.settings import SettingsDialog  # noqa: E402
from ui.sprite import load_skin  # noqa: E402


def main() -> int:
    app = QApplication(sys.argv)
    cfg = config.load()
    skin = load_skin(ROOT / "assets" / "whale-girl" / "frames")
    pm = skin.frames["idle"] if skin else QPixmap()
    dlg = SettingsDialog(cfg, pm)
    dlg.show()

    def grab() -> None:
        dlg.grab().save(str(ROOT / "assets" / "preview" / "settings.png"))
        print("saved", dlg.size())
        app.quit()

    QTimer.singleShot(600, grab)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
