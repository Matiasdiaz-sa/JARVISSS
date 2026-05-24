import sys
import json
import urllib.request
from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QLinearGradient, QPainterPath

class AgendaWorker(QThread):
    update_signal = pyqtSignal(list)

    def run(self):
        import time
        while True:
            try:
                req = urllib.request.Request("http://127.0.0.1:14782/api/agenda")
                with urllib.request.urlopen(req, timeout=1.0) as response:
                    data = json.loads(response.read().decode())
                    self.update_signal.emit(data.get("items", []))
            except Exception as e:
                # Si el servidor no está corriendo, simplemente enviamos vacío
                self.update_signal.emit([])
            time.sleep(0.5)

class AgendaWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        # Posición inicial (arriba a la derecha)
        screen = QApplication.primaryScreen().geometry()
        self.move(screen.width() - 320, 50)
        self.resize(300, 100)
        
        self.items = []
        self._prev_items_hash = ""  # Para detectar cambios
        self.drag_pos = None
        self._opacity = 0.0  # Para fade-in/out
        self._target_opacity = 0.0
        
        # Timer de animación para transiciones suaves
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._animate)
        self._anim_timer.start(16)  # ~60 FPS
        
        self.worker = AgendaWorker()
        self.worker.update_signal.connect(self.on_agenda_update)
        self.worker.start()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if self.drag_pos is not None:
            delta = event.globalPosition().toPoint() - self.drag_pos
            self.move(self.pos() + delta)
            self.drag_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        self.drag_pos = None

    def _animate(self):
        """Interpola la opacidad suavemente."""
        diff = self._target_opacity - self._opacity
        if abs(diff) > 0.01:
            self._opacity += diff * 0.15
            self.update()
        elif self._target_opacity == 0 and self._opacity < 0.02:
            self._opacity = 0
            if self.isVisible():
                self.hide()
    
    def _items_hash(self, items):
        """Genera un hash simple para detectar cambios."""
        return str([(i.get("id"), i.get("label"), int(i.get("remaining_seconds", 0))) for i in items])

    def on_agenda_update(self, items):
        new_hash = self._items_hash(items)
        
        if not items:
            self._target_opacity = 0.0
            self.items = []
            return
        
        # Solo actualizar si cambió algo significativo
        self.items = items
        self._prev_items_hash = new_hash
        
        if not self.isVisible():
            self.show()
            self._opacity = 0.0
        
        self._target_opacity = 1.0
        
        # Ajustar altura dinámicamente
        new_height = 50 + (len(self.items) * 45) + 15
        self.resize(300, new_height)
        self.update()

    def paintEvent(self, event):
        if not self.items and self._opacity < 0.02:
            return
            
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setOpacity(self._opacity)
        
        # Fondo con glassmorphism
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), 16, 16)
        
        gradient = QLinearGradient(0, 0, 0, self.height())
        gradient.setColorAt(0, QColor(30, 30, 45, 210))
        gradient.setColorAt(1, QColor(18, 18, 24, 230))
        painter.fillPath(path, QBrush(gradient))
        
        # Borde sutil
        painter.setPen(QPen(QColor(255, 255, 255, 25), 1))
        painter.drawPath(path)
        
        # Highlight superior (glassmorphism)
        highlight = QPainterPath()
        highlight.addRoundedRect(1, 1, self.width() - 2, 25, 15, 15)
        painter.fillPath(highlight, QBrush(QColor(255, 255, 255, 8)))
        
        # Título
        painter.setPen(QPen(QColor(200, 200, 220, 230)))
        font_title = QFont("Segoe UI", 11, QFont.Weight.Bold)
        painter.setFont(font_title)
        painter.drawText(15, 28, "RELOJ Agenda de Jarvis")
        
        # Línea separadora
        painter.setPen(QPen(QColor(255, 255, 255, 30), 1))
        painter.drawLine(15, 38, self.width() - 15, 38)
        
        font_item = QFont("Segoe UI", 10)
        painter.setFont(font_item)
        
        y = 62
        for item in self.items:
            # Color basado en el tipo
            if item["type"] == "temporizador":
                # Color según tiempo restante
                remaining = item.get("remaining_seconds", 0)
                if remaining > 60:
                    color_reloj = QColor(80, 220, 120)  # Verde
                elif remaining > 15:
                    color_reloj = QColor(255, 170, 50)   # Naranja
                else:
                    color_reloj = QColor(255, 80, 80)    # Rojo
            else:
                color_reloj = QColor(80, 140, 255)  # Azul para alarmas
            
            # Icono según tipo
            icon = "⏱️" if item["type"] == "temporizador" else "⏰"
            
            # Formato de tiempo
            segundos_totales = int(item["remaining_seconds"])
            horas = segundos_totales // 3600
            minutos = (segundos_totales % 3600) // 60
            segundos = segundos_totales % 60
            
            if horas > 0:
                tiempo_str = f"{horas:02d}:{minutos:02d}:{segundos:02d}"
            else:
                tiempo_str = f"{minutos:02d}:{segundos:02d}"
                
            # Dibujar icono y etiqueta
            painter.setPen(QPen(QColor(240, 240, 255)))
            label_text = item["label"]
            if len(label_text) > 18:
                label_text = label_text[:15] + "..."
            painter.drawText(20, y, f"{icon} {label_text}")
            
            # Dibujar tiempo (alineado a la derecha)
            painter.setPen(QPen(color_reloj, 2))
            font_time = QFont("Segoe UI", 13, QFont.Weight.Bold)
            painter.setFont(font_time)
            
            fm = painter.fontMetrics()
            time_width = fm.horizontalAdvance(tiempo_str)
            painter.drawText(self.width() - time_width - 20, y, tiempo_str)
            
            painter.setFont(font_item)  # reset font
            y += 45
        
        painter.end()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    widget = AgendaWidget()
    # Solo para testing visual, le agregamos items dummy
    widget.items = [
        {"type": "temporizador", "label": "Cocinar pasta", "remaining_seconds": 605},
        {"type": "alarma", "label": "Despertar", "remaining_seconds": 3600}
    ]
    widget._opacity = 1.0
    widget._target_opacity = 1.0
    widget.show()
    sys.exit(app.exec())
