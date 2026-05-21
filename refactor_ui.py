import re
import os

ui_path = r"e:\Proyecto-IALOCAL\ui_jarvis.py"

with open(ui_path, "r", encoding="utf-8") as f:
    ui_code = f.read()

# 1. Imports
ui_code = ui_code.replace(
    "from PyQt6.QtWidgets import QApplication, QWidget",
    "from PyQt6.QtWidgets import QApplication, QWidget, QPushButton, QSystemTrayIcon, QMenu"
)
ui_code = ui_code.replace(
    "from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QLinearGradient, QCursor, QPainterPath",
    "from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QLinearGradient, QCursor, QPainterPath, QIcon, QPixmap\nfrom PyQt6.QtGui import QAction"
)

# 2. Add Init logic for button and tray icon
init_target = """        # Iniciar motor de audio
        self.worker = AudioWorker()
        self.worker.update_signal.connect(self.on_audio_update)
        self.worker.start()"""

init_repl = """        # ====== Boton Ocultar ======
        self.btn_hide = QPushButton("-", self)
        self.btn_hide.resize(25, 25)
        self.btn_hide.move(self.width() - 30, 5)
        self.btn_hide.setStyleSheet("background-color: rgba(255,255,255,30); color: white; border-radius: 12px; font-weight: bold; font-size: 16px;")
        self.btn_hide.clicked.connect(self.hide_to_tray)
        self.btn_hide.setCursor(Qt.CursorShape.PointingHandCursor)

        # ====== System Tray ======
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(self.create_tray_icon(4))
        
        tray_menu = QMenu()
        restore_action = QAction("Mostrar Jarvis", self)
        restore_action.triggered.connect(self.show_normal)
        quit_action = QAction("Apagar Jarvis", self)
        quit_action.triggered.connect(QApplication.instance().quit)
        
        tray_menu.addAction(restore_action)
        tray_menu.addAction(quit_action)
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()
        
        # Al hacer doble clic en el tray
        self.tray_icon.activated.connect(self.on_tray_activated)

        # Iniciar motor de audio
        self.worker = AudioWorker()
        self.worker.update_signal.connect(self.on_audio_update)
        self.worker.start()"""

ui_code = ui_code.replace(init_target, init_repl)

# 3. Add methods for tray logic
methods_target = """    def mouseReleaseEvent(self, event):
        self.drag_pos = None"""

methods_repl = """    def mouseReleaseEvent(self, event):
        self.drag_pos = None

    def hide_to_tray(self):
        self.hide()
        self.tray_icon.showMessage("Jarvis", "Me he ocultado. Sigo escuchando en segundo plano.", QSystemTrayIcon.MessageIcon.Information, 2000)

    def show_normal(self):
        self.show()
        self.activateWindow()
        
    def on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_normal()

    def create_tray_icon(self, vol_boost):
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Elegir color
        color = self.color_base
        if self.estado_actual == "grabando": color = self.color_activo
        elif self.estado_actual == "pensando": color = self.color_pensando
        elif self.estado_actual == "hablando": color = self.color_hablando
        
        painter.setBrush(QBrush(color))
        painter.setPen(Qt.PenStyle.NoPen)
        
        # Dibujar 4 barritas
        bars = 4
        bar_w = 4
        gap = 2
        start_x = (32 - (bars * bar_w + (bars - 1) * gap)) // 2
        
        import math
        for i in range(bars):
            factor = math.sin(((i + 1) / bars) * math.pi)
            h = max(4, min(24, vol_boost * factor))
            
            if self.estado_actual == "hibernando": h = 2
            elif self.estado_actual == "esperando" and vol_boost < 5: h = 4
            
            x = start_x + i * (bar_w + gap)
            y = 16 - (h / 2)
            painter.drawRoundedRect(int(x), int(y), bar_w, int(h), 2, 2)
            
        painter.end()
        return QIcon(pixmap)"""

ui_code = ui_code.replace(methods_target, methods_repl)

# 4. Update animation to update tray icon
anim_target = """        self.update() # Forzar repintado (llama a paintEvent)"""

anim_repl = """        self.update() # Forzar repintado (llama a paintEvent)
        
        # Si está oculto, actualizar el icono del tray para mostrar la actividad
        if self.isHidden():
            avg_height = sum(self.current_heights) / len(self.current_heights)
            self.tray_icon.setIcon(self.create_tray_icon(avg_height))"""

ui_code = ui_code.replace(anim_target, anim_repl)

# 5. Fix eye logic (change esperando to hibernando)
ui_code = ui_code.replace(
    'if self.estado_actual == "esperando":',
    'if self.estado_actual == "hibernando":'
)

with open(ui_path, "w", encoding="utf-8") as f:
    f.write(ui_code)

print("UI Refactor complete.")
