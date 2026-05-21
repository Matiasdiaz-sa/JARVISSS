import sys
import json
import urllib.request
from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QFont

class AgendaWorker(QThread):
    update_signal = pyqtSignal(list)

    def run(self):
        import time
        while True:
            try:
                req = urllib.request.Request("http://127.0.0.1:8000/api/agenda")
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
        self.drag_pos = None
        
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

    def on_agenda_update(self, items):
        self.items = items
        if not self.items:
            self.hide()
        else:
            self.show()
            # Ajustar altura dinámicamente: 50px de cabecera + 40px por item + 15px de padding final
            new_height = 50 + (len(self.items) * 40) + 15
            self.resize(300, new_height)
            self.update()

    def paintEvent(self, event):
        if not self.items:
            return
            
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Fondo translúcido
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(20, 20, 20, 210)))
        painter.drawRoundedRect(self.rect(), 15, 15)
        
        # Título
        painter.setPen(QPen(QColor(255, 255, 255, 230)))
        font_title = QFont("Segoe UI", 11, QFont.Weight.Bold)
        painter.setFont(font_title)
        painter.drawText(15, 30, "⏳ Agenda de Jarvis")
        
        # Dibujar una línea separadora tenue
        painter.setPen(QPen(QColor(255, 255, 255, 50), 1))
        painter.drawLine(15, 40, self.width() - 15, 40)
        
        font_item = QFont("Segoe UI", 10)
        painter.setFont(font_item)
        
        y = 65
        for item in self.items:
            # Color basado en el tipo
            color_reloj = QColor(255, 170, 50) if item["type"] == "temporizador" else QColor(100, 200, 255)
            painter.setPen(QPen(color_reloj))
            
            # Formato de tiempo
            segundos_totales = int(item["remaining_seconds"])
            horas = segundos_totales // 3600
            minutos = (segundos_totales % 3600) // 60
            segundos = segundos_totales % 60
            
            if horas > 0:
                tiempo_str = f"{horas:02d}:{minutos:02d}:{segundos:02d}"
            else:
                tiempo_str = f"{minutos:02d}:{segundos:02d}"
                
            # Dibujar etiqueta
            painter.setPen(QPen(QColor(255, 255, 255)))
            label_text = item["label"]
            if len(label_text) > 18:
                label_text = label_text[:15] + "..."
            painter.drawText(20, y, label_text)
            
            # Dibujar tiempo (alineado a la derecha)
            painter.setPen(QPen(color_reloj, 2))
            font_time = QFont("Segoe UI", 12, QFont.Weight.Bold)
            painter.setFont(font_time)
            
            fm = painter.fontMetrics()
            time_width = fm.horizontalAdvance(tiempo_str)
            painter.drawText(self.width() - time_width - 20, y, tiempo_str)
            
            painter.setFont(font_item) # reset font para el siguiente
            y += 40

if __name__ == "__main__":
    app = QApplication(sys.argv)
    widget = AgendaWidget()
    # Solo para testing visual, le agregamos items dummy
    widget.items = [
        {"type": "temporizador", "label": "Cocinar pasta", "remaining_seconds": 605},
        {"type": "alarma", "label": "Despertar", "remaining_seconds": 3600}
    ]
    widget.show()
    sys.exit(app.exec())
