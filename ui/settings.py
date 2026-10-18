"""设置窗口：角色 / 名称 / 声音 / 弹窗。"""
from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QCheckBox, QDialog, QFileDialog, QFormLayout, QFrame,
                               QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QSpinBox, QVBoxLayout, QWidget)

CUSTOM_DIR = Path(__file__).resolve().parent.parent / "assets" / "custom"


def _section(title: str) -> QLabel:
    lab = QLabel(title)
    lab.setStyleSheet("color:#8A97B8; font-size:11px; font-weight:600; letter-spacing:1px;")
    return lab


class SettingsDialog(QDialog):
    saved = Signal(dict)   # 回传新配置

    def __init__(self, cfg: dict, preview: QPixmap | None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("桌宠设置")
        self.setModal(True)
        self.setMinimumWidth(420)
        self.cfg = cfg
        self.preview_pm = preview
        self._new_skin: str | None = cfg["pet"].get("skin_file") or None
        self._new_sound: str | None = cfg["alerts"].get("sound_file") or None

        self.setStyleSheet("""
            QDialog { background:#121828; }
            QLabel { color:#DCE6FF; font-size:12px; }
            QLineEdit, QSpinBox {
                background:#1B2338; color:#E8EFFF; border:1px solid #2C3854;
                border-radius:6px; padding:5px 8px; font-size:12px;
            }
            QPushButton {
                background:#243056; color:#DCE6FF; border:1px solid #35446B;
                border-radius:6px; padding:6px 12px; font-size:12px;
            }
            QPushButton:hover { background:#2C3B69; }
            QPushButton#primary { background:#3F6DFF; border-color:#3F6DFF; color:white; }
            QPushButton#primary:hover { background:#5380FF; }
            QCheckBox { color:#DCE6FF; font-size:12px; }
            QFrame#card { background:#171F33; border:1px solid #26314B; border-radius:10px; }
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 14)
        root.setSpacing(12)

        # ---- 角色 ----
        root.addWidget(_section("角色"))
        card = QFrame()
        card.setObjectName("card")
        row = QHBoxLayout(card)
        row.setContentsMargins(12, 10, 12, 10)
        row.setSpacing(12)

        self.thumb = QLabel()
        self.thumb.setFixedSize(72, 96)
        self.thumb.setAlignment(Qt.AlignCenter)
        self.thumb.setStyleSheet("background:#0E1424; border-radius:6px;")
        if preview is not None:
            self.thumb.setPixmap(preview.scaled(72, 96, Qt.KeepAspectRatio,
                                                Qt.SmoothTransformation))
        row.addWidget(self.thumb)

        col = QVBoxLayout()
        col.setSpacing(8)
        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("名称"))
        self.ed_name = QLineEdit(self.cfg["pet"].get("name") or "墨团")
        self.ed_name.setMaxLength(12)
        name_row.addWidget(self.ed_name, 1)
        col.addLayout(name_row)

        btn_row = QHBoxLayout()
        self.btn_png = QPushButton("导入 PNG…")
        self.btn_png.clicked.connect(self._pick_png)
        self.btn_reset = QPushButton("恢复默认形象")
        self.btn_reset.clicked.connect(self._reset_skin)
        btn_row.addWidget(self.btn_png)
        btn_row.addWidget(self.btn_reset)
        btn_row.addStretch(1)
        col.addLayout(btn_row)

        self.lbl_skin = QLabel(self._skin_text())
        self.lbl_skin.setStyleSheet("color:#7E8BA8; font-size:11px;")
        col.addWidget(self.lbl_skin)
        row.addLayout(col, 1)
        root.addWidget(card)

        # ---- 声音 ----
        root.addWidget(_section("声音"))
        snd = QFrame()
        snd.setObjectName("card")
        form = QFormLayout(snd)
        form.setContentsMargins(12, 10, 12, 10)
        form.setSpacing(8)
        self.ck_sound = QCheckBox("开启提示音")
        self.ck_sound.setChecked(bool(self.cfg["alerts"]["sound"]))
        form.addRow(self.ck_sound)

        snd_row = QHBoxLayout()
        self.lbl_sound = QLabel(Path(self._new_sound).name if self._new_sound else "内置合成音")
        self.lbl_sound.setStyleSheet("color:#7E8BA8; font-size:11px;")
        b1 = QPushButton("选择 WAV…")
        b1.clicked.connect(self._pick_sound)
        b2 = QPushButton("试听")
        b2.clicked.connect(self._test_sound)
        snd_row.addWidget(self.lbl_sound, 1)
        snd_row.addWidget(b1)
        snd_row.addWidget(b2)
        form.addRow(snd_row)
        root.addWidget(snd)

        # ---- 弹窗 ----
        root.addWidget(_section("提醒"))
        alert = QFrame()
        alert.setObjectName("card")
        form2 = QFormLayout(alert)
        form2.setContentsMargins(12, 10, 12, 10)
        form2.setSpacing(8)

        self.ck_done = QCheckBox("任务完成提醒")
        self.ck_done.setChecked(bool(self.cfg["alerts"]["complete"]))
        self.ck_appr = QCheckBox("等待确认提醒（跳到屏幕中央抖动）")
        self.ck_appr.setChecked(bool(self.cfg["alerts"]["approval"]))
        self.ck_tray = QCheckBox("系统托盘通知")
        self.ck_tray.setChecked(bool(self.cfg["alerts"]["tray"]))
        form2.addRow(self.ck_done)
        form2.addRow(self.ck_appr)
        form2.addRow(self.ck_tray)

        dur_row = QHBoxLayout()
        dur_row.addWidget(QLabel("气泡停留"))
        self.sp_dur = QSpinBox()
        self.sp_dur.setRange(2, 30)
        self.sp_dur.setSuffix(" 秒")
        self.sp_dur.setValue(int(self.cfg["alerts"]["bubble_seconds"]))
        dur_row.addWidget(self.sp_dur)
        dur_row.addStretch(1)
        form2.addRow(dur_row)
        root.addWidget(alert)

        # ---- 按钮 ----
        btns = QHBoxLayout()
        btns.addStretch(1)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        save = QPushButton("保存")
        save.setObjectName("primary")
        save.clicked.connect(self._save)
        btns.addWidget(cancel)
        btns.addWidget(save)
        root.addLayout(btns)

    # ---------------- 交互 ----------------
    def _skin_text(self) -> str:
        if self._new_skin:
            return f"自定义：{Path(self._new_skin).name}"
        return "当前：鲸鱼娘（五态立绘）"

    def _pick_png(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择角色 PNG", "", "图片 (*.png *.webp)")
        if not path:
            return
        CUSTOM_DIR.mkdir(parents=True, exist_ok=True)
        dst = CUSTOM_DIR / Path(path).name
        try:
            shutil.copyfile(path, dst)
        except Exception:
            return
        self._new_skin = str(dst)
        pm = QPixmap(str(dst))
        if not pm.isNull():
            self.thumb.setPixmap(pm.scaled(72, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.lbl_skin.setText(self._skin_text())

    def _reset_skin(self) -> None:
        self._new_skin = ""
        self.lbl_skin.setText("当前：鲸鱼娘（五态立绘）")

    def _pick_sound(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择提示音", "", "音频 (*.wav)")
        if not path:
            return
        CUSTOM_DIR.mkdir(parents=True, exist_ok=True)
        dst = CUSTOM_DIR / Path(path).name
        try:
            shutil.copyfile(path, dst)
        except Exception:
            return
        self._new_sound = str(dst)
        self.lbl_sound.setText(Path(dst).name)

    def _test_sound(self) -> None:
        import winsound

        target = self._new_sound
        if not target:
            target = str(Path(__file__).resolve().parent.parent / "assets" / "sounds" / "complete.wav")
        if Path(target).exists():
            try:
                winsound.PlaySound(target, winsound.SND_FILENAME | winsound.SND_ASYNC)
            except Exception:
                pass

    def _save(self) -> None:
        self.cfg["pet"]["name"] = self.ed_name.text().strip() or "墨团"
        self.cfg["pet"]["skin_file"] = self._new_skin or ""
        self.cfg["alerts"]["sound"] = self.ck_sound.isChecked()
        self.cfg["alerts"]["sound_file"] = self._new_sound or ""
        self.cfg["alerts"]["complete"] = self.ck_done.isChecked()
        self.cfg["alerts"]["approval"] = self.ck_appr.isChecked()
        self.cfg["alerts"]["tray"] = self.ck_tray.isChecked()
        self.cfg["alerts"]["bubble_seconds"] = self.sp_dur.value()
        self.saved.emit(self.cfg)
        self.accept()
