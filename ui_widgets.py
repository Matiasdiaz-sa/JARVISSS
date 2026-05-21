"""
Sistema de Widgets Dinámicos para Jarvis.
Permite crear widgets flotantes en el escritorio por comando de voz.
Tipos: temporizador, reloj, nota, youtube, web.
"""
import sys
import os
import json
import math
import time
import datetime
import threading
import re
from http.server import HTTPServer, BaseHTTPRequestHandler
from functools import partial

def log_widget_debug(msg: str):
    with open("widgets_debug.log", "a", encoding="utf-8") as f:
        f.write(f"[{datetime.datetime.now()}] {msg}\n")


from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QTextEdit, QGraphicsDropShadowEffect, QSizeGrip
)
from PyQt6.QtCore import (
    Qt, QTimer, QThread, pyqtSignal, QPointF, QSize, QUrl, QPropertyAnimation,
    QEasingCurve, QRect, pyqtProperty, QObject
)
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QLinearGradient, QRadialGradient,
    QPainterPath, QIcon, QPixmap, QCursor
)


# ============================================================
# PALETA DE COLORES Y ESTILOS COMPARTIDOS
# ============================================================
COLORS = {
    "bg_dark": QColor(18, 18, 24, 230),
    "bg_glass": QColor(30, 30, 45, 200),
    "border": QColor(255, 255, 255, 25),
    "border_hover": QColor(255, 255, 255, 50),
    "text": QColor(240, 240, 255),
    "text_dim": QColor(160, 160, 180),
    "accent_blue": QColor(80, 140, 255),
    "accent_cyan": QColor(50, 220, 220),
    "accent_red": QColor(255, 80, 80),
    "accent_green": QColor(80, 220, 120),
    "accent_orange": QColor(255, 170, 50),
    "accent_purple": QColor(160, 100, 255),
    "close_hover": QColor(255, 60, 60, 200),
}

FONT_FAMILY = "Segoe UI"


# ============================================================
# BASE WIDGET — Ventana flotante con glassmorphism
# ============================================================
class BaseWidget(QWidget):
    """Widget base con funcionalidad común: frameless, translúcido, arrastrable, botón cerrar."""
    
    closed = pyqtSignal(str)  # Emite el widget_id cuando se cierra
    
    def __init__(self, widget_id: str, title: str = "", width: int = 280, height: int = 160, parent=None):
        super().__init__(parent)
        self.widget_id = widget_id
        self.title_text = title
        self._opacity = 0.0
        
        # Configuración de ventana
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(width, height)
        
        # Posición inicial (escalonada garantizada para que no se superpongan)
        screen = QApplication.primaryScreen().geometry()
        try:
            # widget_id tiene formato "tipo_contador_timestamp"
            contador = int(widget_id.split("_")[1])
            offset_x = (contador * 50) % 400
            offset_y = (contador * 60) % 300
        except:
            offset_x = hash(widget_id) % 200
            offset_y = hash(widget_id) % 200
            
        self.move(screen.width() - width - 40 - offset_x, 80 + offset_y)
        
        # Variables de arrastre
        self.drag_pos = None
        
        # Animación de aparición (eliminada para evitar bugs de timer)
        self._opacity = 1.0
        self.update()
    
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
    
    def close_widget(self):
        """Cierra el widget con animación."""
        self.closed.emit(self.widget_id)
        self.close()
        self.deleteLater()
    
    def paintEvent(self, event):
        """Dibuja el fondo con glassmorphism."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setOpacity(self._opacity)
        
        # Fondo con glassmorphism
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), 16, 16)
        
        # Gradiente de fondo
        gradient = QLinearGradient(0, 0, 0, self.height())
        gradient.setColorAt(0, COLORS["bg_glass"])
        gradient.setColorAt(1, COLORS["bg_dark"])
        painter.fillPath(path, QBrush(gradient))
        
        # Borde sutil
        painter.setPen(QPen(COLORS["border"], 1))
        painter.drawPath(path)
        
        # Línea de brillo superior (glassmorphism)
        highlight = QPainterPath()
        highlight.addRoundedRect(1, 1, self.width() - 2, 30, 15, 15)
        painter.fillPath(highlight, QBrush(QColor(255, 255, 255, 8)))
        
        # Título
        if self.title_text:
            painter.setPen(QPen(COLORS["text_dim"]))
            painter.setFont(QFont(FONT_FAMILY, 9, QFont.Weight.DemiBold))
            painter.drawText(15, 22, self.title_text)
        
        # Botón de cerrar (X)
        close_rect_x = self.width() - 30
        close_rect_y = 6
        close_size = 20
        
        # Detectar si el mouse está sobre el botón
        mouse_pos = self.mapFromGlobal(QCursor.pos())
        hovering_close = (close_rect_x <= mouse_pos.x() <= close_rect_x + close_size and
                         close_rect_y <= mouse_pos.y() <= close_rect_y + close_size)
        
        if hovering_close:
            painter.setBrush(QBrush(COLORS["close_hover"]))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(close_rect_x, close_rect_y, close_size, close_size)
        
        painter.setPen(QPen(QColor(255, 255, 255, 180 if hovering_close else 100), 2))
        cx, cy = close_rect_x + close_size // 2, close_rect_y + close_size // 2
        painter.drawLine(cx - 4, cy - 4, cx + 4, cy + 4)
        painter.drawLine(cx + 4, cy - 4, cx - 4, cy + 4)
        
        # Dibujar contenido específico del widget hijo
        self.paint_content(painter)
        
        painter.end()
    
    def mouseDoubleClickEvent(self, event):
        # Detectar doble clic en botón cerrar
        close_rect_x = self.width() - 30
        close_rect_y = 6
        close_size = 20
        if (close_rect_x <= event.position().x() <= close_rect_x + close_size and
            close_rect_y <= event.position().y() <= close_rect_y + close_size):
            self.close_widget()
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # Detectar clic en botón cerrar
            close_rect_x = self.width() - 30
            close_rect_y = 6
            close_size = 20
            if (close_rect_x <= event.position().x() <= close_rect_x + close_size and
                close_rect_y <= event.position().y() <= close_rect_y + close_size):
                self.close_widget()
                return
            self.drag_pos = event.globalPosition().toPoint()
    
    def paint_content(self, painter):
        """Método a sobreescribir por los widgets hijos."""
        pass


# ============================================================
# TIMER WIDGET — Temporizador visual con cuenta regresiva
# ============================================================
class TimerWidget(BaseWidget):
    def __init__(self, widget_id: str, duration_seconds: float, label: str = "Temporizador", parent=None):
        super().__init__(widget_id, f"⏱️ {label}", width=260, height=160, parent=parent)
        self.total_seconds = duration_seconds
        self.remaining_seconds = duration_seconds
        self.label = label
        self.finished = False
        self.finished_time = None
        self.start_time = time.time()
        
        # Timer de actualización
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self._tick)
        self.update_timer.start(100)  # Actualizar cada 100ms
    
    def _tick(self):
        elapsed = time.time() - self.start_time
        self.remaining_seconds = max(0, self.total_seconds - elapsed)
        
        if self.remaining_seconds <= 0 and not self.finished:
            self.finished = True
            self.finished_time = time.time()
            self.title_text = f"✅ {self.label} — ¡Terminado!"
            # Beep sonoro
            try:
                import winsound
                def beeps():
                    for _ in range(3):
                        winsound.Beep(880, 150)
                        winsound.Beep(1046, 150)
                        time.sleep(0.1)
                threading.Thread(target=beeps, daemon=True).start()
            except Exception:
                pass
                
        if self.finished and self.finished_time and (time.time() - self.finished_time > 5.0):
            self.close_widget()
            return
        
        self.update()
    
    def paint_content(self, painter):
        # Progreso
        progress = self.remaining_seconds / self.total_seconds if self.total_seconds > 0 else 0
        
        # Color que cambia según el progreso
        if progress > 0.5:
            color = COLORS["accent_green"]
        elif progress > 0.2:
            color = COLORS["accent_orange"]
        else:
            color = COLORS["accent_red"]
        
        if self.finished:
            color = COLORS["accent_cyan"]
        
        # Barra de progreso circular
        center_x = self.width() // 2
        center_y = 95
        radius = 40
        
        # Fondo del arco
        painter.setPen(QPen(QColor(255, 255, 255, 20), 6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawArc(center_x - radius, center_y - radius, radius * 2, radius * 2, 0, 360 * 16)
        
        # Arco de progreso
        painter.setPen(QPen(color, 6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        span_angle = int(progress * 360 * 16)
        painter.drawArc(center_x - radius, center_y - radius, radius * 2, radius * 2, 90 * 16, -span_angle)
        
        # Texto del tiempo
        remaining = int(self.remaining_seconds)
        hours = remaining // 3600
        minutes = (remaining % 3600) // 60
        seconds = remaining % 60
        
        if hours > 0:
            time_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        else:
            time_str = f"{minutes:02d}:{seconds:02d}"
        
        painter.setPen(QPen(COLORS["text"]))
        painter.setFont(QFont(FONT_FAMILY, 16, QFont.Weight.Bold))
        fm = painter.fontMetrics()
        tw = fm.horizontalAdvance(time_str)
        painter.drawText(center_x - tw // 2, center_y + 7, time_str)


# ============================================================
# CLOCK WIDGET — Reloj digital flotante
# ============================================================
class ClockWidget(BaseWidget):
    def __init__(self, widget_id: str, parent=None):
        super().__init__(widget_id, "🕐 Reloj", width=220, height=120, parent=parent)
        
        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self.update)
        self.clock_timer.start(1000)
    
    def paint_content(self, painter):
        now = datetime.datetime.now()
        
        # Hora grande
        time_str = now.strftime("%H:%M:%S")
        painter.setPen(QPen(COLORS["accent_cyan"]))
        painter.setFont(QFont(FONT_FAMILY, 28, QFont.Weight.Bold))
        fm = painter.fontMetrics()
        tw = fm.horizontalAdvance(time_str)
        painter.drawText(self.width() // 2 - tw // 2, 70, time_str)
        
        # Fecha
        date_str = now.strftime("%A %d de %B")
        # Traducir días y meses al español
        traducciones = {
            "Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miércoles",
            "Thursday": "Jueves", "Friday": "Viernes", "Saturday": "Sábado", "Sunday": "Domingo",
            "January": "enero", "February": "febrero", "March": "marzo", "April": "abril",
            "May": "mayo", "June": "junio", "July": "julio", "August": "agosto",
            "September": "septiembre", "October": "octubre", "November": "noviembre", "December": "diciembre",
        }
        for eng, esp in traducciones.items():
            date_str = date_str.replace(eng, esp)
        
        painter.setPen(QPen(COLORS["text_dim"]))
        painter.setFont(QFont(FONT_FAMILY, 10))
        fm = painter.fontMetrics()
        tw = fm.horizontalAdvance(date_str)
        painter.drawText(self.width() // 2 - tw // 2, 95, date_str)


# ============================================================
# NOTE WIDGET — Nota adhesiva flotante
# ============================================================
class NoteWidget(BaseWidget):
    def __init__(self, widget_id: str, text: str = "", title: str = "Nota", parent=None):
        super().__init__(widget_id, f"📝 {title}", width=280, height=200, parent=parent)
        self.note_text = text
        
        # QTextEdit para editar la nota
        self.text_edit = QTextEdit(self)
        self.text_edit.setPlainText(text)
        self.text_edit.setGeometry(12, 35, self.width() - 24, self.height() - 47)
        self.text_edit.setStyleSheet(f"""
            QTextEdit {{
                background-color: rgba(255, 255, 255, 10);
                color: rgb(230, 230, 245);
                border: 1px solid rgba(255, 255, 255, 15);
                border-radius: 8px;
                padding: 8px;
                font-family: '{FONT_FAMILY}';
                font-size: 12px;
                selection-background-color: rgba(80, 140, 255, 100);
            }}
            QScrollBar:vertical {{
                width: 6px;
                background: transparent;
            }}
            QScrollBar::handle:vertical {{
                background: rgba(255, 255, 255, 30);
                border-radius: 3px;
                min-height: 20px;
            }}
        """)


# ============================================================
# YOUTUBE WIDGET — Video embebido de YouTube
# ============================================================
class YouTubeWidget(BaseWidget):
    def __init__(self, widget_id: str, video_url: str = "", search_query: str = "", parent=None):
        title_label = search_query or "YouTube"
        super().__init__(widget_id, f"▶️ {title_label}", width=480, height=320, parent=parent)
        
        self.video_url = video_url
        self.search_query = search_query
        self._web_view = None
        
        # Intentar cargar WebEngine
        try:
            from PyQt6.QtWebEngineWidgets import QWebEngineView
            self._web_view = QWebEngineView(self)
            self._web_view.setGeometry(8, 34, self.width() - 16, self.height() - 42)
            self._web_view.setStyleSheet("background: transparent; border-radius: 10px;")
            
            if video_url:
                # Extraer video ID y usar embed
                video_id = self._extract_video_id(video_url)
                if video_id:
                    embed_url = f"https://www.youtube.com/embed/{video_id}?autoplay=1"
                    self._web_view.setUrl(QUrl(embed_url))
                else:
                    self._web_view.setUrl(QUrl(video_url))
            elif search_query:
                # Buscar en YouTube
                search_url = f"https://www.youtube.com/results?search_query={search_query.replace(' ', '+')}"
                self._web_view.setUrl(QUrl(search_url))
        except ImportError:
            # Si no hay WebEngine, mostrar un mensaje
            self._fallback_label = QLabel("⚠️ Instalar PyQt6-WebEngine\npip install PyQt6-WebEngine", self)
            self._fallback_label.setGeometry(20, 60, self.width() - 40, 100)
            self._fallback_label.setStyleSheet(f"color: {COLORS['accent_orange'].name()}; font-family: '{FONT_FAMILY}'; font-size: 12px;")
            self._fallback_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._fallback_label.setWordWrap(True)
    
    def _extract_video_id(self, url: str) -> str:
        """Extrae el ID del video de una URL de YouTube."""
        patterns = [
            r'(?:youtube\.com/watch\?v=|youtu\.be/)([a-zA-Z0-9_-]{11})',
            r'youtube\.com/embed/([a-zA-Z0-9_-]{11})',
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return ""
    
    def close_widget(self):
        """Override para limpiar el WebEngine."""
        if self._web_view:
            self._web_view.setUrl(QUrl("about:blank"))
        super().close_widget()


# ============================================================
# WEB WIDGET — Mini navegador web embebido
# ============================================================
class WebWidget(BaseWidget):
    def __init__(self, widget_id: str, url: str = "https://www.google.com", title: str = "Web", parent=None):
        super().__init__(widget_id, f"🌐 {title}", width=500, height=400, parent=parent)
        
        self._web_view = None
        
        try:
            from PyQt6.QtWebEngineWidgets import QWebEngineView
            self._web_view = QWebEngineView(self)
            self._web_view.setGeometry(8, 34, self.width() - 16, self.height() - 42)
            
            # Asegurar que la URL tiene protocolo
            if not url.startswith("http://") and not url.startswith("https://"):
                url = f"https://{url}"
            
            self._web_view.setUrl(QUrl(url))
        except ImportError:
            self._fallback_label = QLabel("⚠️ Instalar PyQt6-WebEngine\npip install PyQt6-WebEngine", self)
            self._fallback_label.setGeometry(20, 60, self.width() - 40, 100)
            self._fallback_label.setStyleSheet(f"color: {COLORS['accent_orange'].name()}; font-family: '{FONT_FAMILY}'; font-size: 12px;")
            self._fallback_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._fallback_label.setWordWrap(True)
    
    def close_widget(self):
        if self._web_view:
            self._web_view.setUrl(QUrl("about:blank"))
        super().close_widget()


# ============================================================
# WIDGET MANAGER — Gestor central de widgets + servidor HTTP
# ============================================================
class WidgetRequestHandler(BaseHTTPRequestHandler):
    """Handler HTTP para recibir comandos de creación/destrucción de widgets."""
    
    # Se inyecta la función callback de la señal al crear la clase
    widget_callback = None
    
    def log_message(self, format, *args):
        pass
    
    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode('utf-8')
        
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b'{"error": "Invalid JSON"}')
            return
        
        if self.path == "/widget":
            log_widget_debug(f"HTTP handler: /widget received: {body}")
            if self.widget_callback:
                try:
                    self.widget_callback(json.dumps(data))
                    log_widget_debug("Emitido con éxito")
                except Exception as e:
                    log_widget_debug(f"Error al emitir: {e}")
            else:
                log_widget_debug("widget_callback es None")
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"status": "ok"}')
            
        elif self.path == "/widget/close":
            if self.widget_callback:
                data["_action"] = "close"
                self.widget_callback(json.dumps(data))
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"status": "ok"}')
        else:
            self.send_response(404)
            self.end_headers()


class WidgetServerThread(QThread):
    widget_command = pyqtSignal(str)
    
    def __init__(self, port=8001, parent=None):
        super().__init__(parent)
        self.port = port
        self.server = None
        self.daemon = True
    
    def run(self):
        # Pasar el método bound emit como callback
        emit_callback = self.widget_command.emit
        
        class Handler(WidgetRequestHandler):
            widget_callback = emit_callback
            
        try:
            self.server = HTTPServer(('127.0.0.1', self.port), Handler)
            print(f"[Widgets] Servidor escuchando en {self.port}")
            self.server.serve_forever()
        except OSError as e:
            print(f"[Widgets] Error servidor: {e}")
    
    def stop(self):
        if self.server:
            self.server.shutdown()



class WidgetManager(QObject):
    """Gestor central de widgets dinámicos. Maneja creación, destrucción y listado."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.widgets = {}  # widget_id -> BaseWidget
        self._counter = 0
        
        # Servidor HTTP para recibir comandos
        self.server_thread = WidgetServerThread(port=8001)
        self.server_thread.widget_command.connect(self._handle_command)
        self.server_thread.start()
    
    def _generate_id(self, tipo: str) -> str:
        self._counter += 1
        return f"{tipo}_{self._counter}_{int(time.time()) % 10000}"
    
    def _handle_command(self, json_str: str):
        """Procesa un comando recibido por HTTP (se ejecuta en el hilo principal de Qt)."""
        log_widget_debug(f"Recibido comando en thread: {QThread.currentThread().objectName() or 'Main Thread'} - Data: {json_str}")
        try:
            data = json.loads(json_str)
            
            if data.get("_action") == "close":
                identificador = data.get("identificador", "")
                self.close_widget(identificador)
                return
            
            tipo = data.get("tipo", "")
            parametro = data.get("parametro", "")
            titulo = data.get("titulo", "")
            
            self.create_widget(tipo, parametro, titulo)
            
        except Exception as e:
            print(f"[Widgets] Error procesando comando: {e}")
    
    def create_widget(self, tipo: str, parametro: str = "", titulo: str = "") -> str:
        """Crea un widget del tipo especificado y lo muestra."""
        widget_id = self._generate_id(tipo)
        widget = None
        
        if tipo == "temporizador":
            # Parsear duración
            seconds = self._parse_duration(parametro)
            label = titulo or "Temporizador"
            widget = TimerWidget(widget_id, seconds, label)
            
        elif tipo == "reloj":
            widget = ClockWidget(widget_id)
            
        elif tipo == "nota":
            text = parametro or ""
            label = titulo or "Nota"
            widget = NoteWidget(widget_id, text, label)
            
        elif tipo == "youtube":
            # Determinar si es URL o búsqueda
            if parametro and ("youtube.com" in parametro or "youtu.be" in parametro):
                widget = YouTubeWidget(widget_id, video_url=parametro)
            else:
                widget = YouTubeWidget(widget_id, search_query=parametro or "lofi hip hop")
            
        elif tipo == "web":
            url = parametro or "https://www.google.com"
            label = titulo or "Web"
            widget = WebWidget(widget_id, url, label)
        
        if widget:
            widget.closed.connect(self._on_widget_closed)
            widget.show()
            self.widgets[widget_id] = widget
            msg = f"[Widgets] Widget creado: {tipo} (ID: {widget_id}) en pos {widget.pos()}"
            print(msg)
            log_widget_debug(msg)
            return widget_id
        else:
            msg = f"[Widgets] Tipo de widget desconocido: {tipo}"
            print(msg)
            log_widget_debug(msg)
            return ""
    
    def close_widget(self, identificador: str):
        """Cierra widgets por ID, tipo, o 'todos'."""
        if identificador.lower() == "todos" or identificador.lower() == "all":
            for wid in list(self.widgets.keys()):
                self.widgets[wid].close_widget()
            return
        
        # Buscar por ID exacto
        if identificador in self.widgets:
            self.widgets[identificador].close_widget()
            return
        
        # Buscar por tipo (cierra todos los de ese tipo)
        to_close = [wid for wid in self.widgets if identificador.lower() in wid.lower()]
        if to_close:
            for wid in to_close:
                self.widgets[wid].close_widget()
            return
        
        # Buscar por título
        to_close = []
        for wid, w in self.widgets.items():
            if identificador.lower() in w.title_text.lower():
                to_close.append(wid)
        for wid in to_close:
            self.widgets[wid].close_widget()
    
    def _on_widget_closed(self, widget_id: str):
        """Callback cuando un widget se cierra."""
        if widget_id in self.widgets:
            del self.widgets[widget_id]
            print(f"[Widgets] Widget cerrado: {widget_id}")
    
    def list_widgets(self) -> list:
        """Retorna la lista de widgets activos."""
        result = []
        for wid, w in self.widgets.items():
            result.append({
                "id": wid,
                "type": wid.split("_")[0],
                "title": w.title_text,
            })
        return result
    
    def _parse_duration(self, duration_str: str) -> float:
        """Parsea una duración como '5m', '30s', '1h', '10 minutos' a segundos."""
        if not duration_str:
            return 300.0  # 5 minutos por defecto
        
        duration_str = duration_str.lower().strip()
        num_match = re.search(r'(\d+)', duration_str)
        if not num_match:
            return 300.0
        
        val = int(num_match.group(1))
        
        if "h" in duration_str or "hora" in duration_str:
            return val * 3600.0
        elif "m" in duration_str or "min" in duration_str:
            return val * 60.0
        else:
            return val * 1.0  # Asumir segundos
    
    def shutdown(self):
        """Cierra todos los widgets y detiene el servidor."""
        for wid in list(self.widgets.keys()):
            try:
                self.widgets[wid].close_widget()
            except Exception:
                pass
        self.server_thread.stop()


# ============================================================
# TESTING STANDALONE
# ============================================================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    manager = WidgetManager()
    
    # Crear widgets de prueba
    manager.create_widget("reloj")
    manager.create_widget("temporizador", "30s", "Test Timer")
    manager.create_widget("nota", "Esta es una nota de prueba\n\n¡Funciona!", "Mi Nota")
    
    sys.exit(app.exec())
