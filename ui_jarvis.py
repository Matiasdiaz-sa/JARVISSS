import sys
import os
import time
import math

# Evitar crash en pythonw al intentar imprimir (sys.stdout no soporta escritura)
sys.stdout = open(os.path.join(os.path.dirname(__file__), "jarvis.log"), "w", encoding="utf-8", buffering=1)
sys.stderr = open(os.path.join(os.path.dirname(__file__), "jarvis_error.log"), "w", encoding="utf-8", buffering=1)

from PyQt6.QtWidgets import QApplication, QWidget, QPushButton, QSystemTrayIcon, QMenu
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QPointF
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QLinearGradient, QCursor, QPainterPath, QIcon, QPixmap
from PyQt6.QtGui import QAction

import motor_audio

class AudioWorker(QThread):
    # Señal: estado, energia, conf
    update_signal = pyqtSignal(str, float, float)

    def run(self):
        # Esta función corre en segundo plano y llama al motor_audio
        def callback(estado, energia, conf):
            self.update_signal.emit(estado, energia, conf)
            
        print("[UI] Iniciando Hilo de Audio...")
        try:
            motor_audio.escuchar_continuo(callback_ui=callback)
        except Exception as e:
            print(f"[UI] Error en motor de audio: {e}")


class JarvisWidget(QWidget):
    def __init__(self):
        super().__init__()
        
        # Configuración Ventana Transparente Flotante
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        # Tamaño base del widget
        self.resize(300, 150)
        
        # Posición inicial (Abajo a la derecha)
        screen = QApplication.primaryScreen().geometry()
        self.move(screen.width() - 350, screen.height() - 150)
        
        # Variables de estado visual
        self.num_bars = 7
        self.target_heights = [10] * self.num_bars
        self.current_heights = [0] * self.num_bars
        
        self.estado_actual = "esperando" # esperando, grabando, pensando, hablando
        self.energia_actual = 0.0
        
        self.color_base = QColor(100, 100, 100, 100) # Gris oscuro
        self.color_activo = QColor(255, 50, 50, 200) # Rojo (Escuchando)
        self.color_pensando = QColor(255, 200, 50, 200) # Naranja/Amarillo (Pensando)
        self.color_hablando = QColor(50, 150, 255, 255) # Azul (Hablando)
        
        self.current_render_color = QColor(self.color_base)
        self.current_opacity = 0.0
        self.target_opacity = 1.0
        self.setWindowOpacity(0.0)
        
        # Timer para animación suave (60 FPS)
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self.update_animation)
        self.anim_timer.start(16)
        
        # Timer para chequear si Jarvis está hablando (lee tts.lock)
        self.tts_timer = QTimer(self)
        self.tts_timer.timeout.connect(self.check_tts_lock)
        self.tts_timer.start(100)
        
        self.time_counter = 0.0

        # Para arrastrar el widget
        self.drag_pos = None
        
        # ====== Boton Ocultar ======
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
        return QIcon(pixmap)

    def on_audio_update(self, estado, energia, conf):
        self.estado_actual = estado
        self.energia_actual = energia
        
        # Si está grabando o esperando, la altura depende de la energía de la voz
        if estado == "grabando" or estado == "esperando":
            # Normalizar energía (ajustar según tu micrófono)
            base_height = 10
            # Mapeo no lineal para que se vea bien
            vol_boost = min(100, (energia / 500.0) * 100)
            
            if estado == "grabando":
                vol_boost = min(100, (energia / 200.0) * 100) # Más sensible cuando graba
            
            for i in range(self.num_bars):
                # Generar un poco de asimetría para que parezca una onda de sonido
                factor = math.sin((i / self.num_bars) * math.pi) 
                # Agregar algo de ruido si hay voz
                ruido = 0 if vol_boost < 5 else (hash(str(time.time() + i)) % 20)
                self.target_heights[i] = base_height + (vol_boost * factor) + ruido

    def check_tts_lock(self):
        lock_file = motor_audio.LOCK_FILE
        if os.path.exists(lock_file):
            if self.estado_actual != "hablando":
                self.estado_anterior = self.estado_actual
            self.estado_actual = "hablando"
        else:
            if self.estado_actual == "hablando":
                self.estado_actual = getattr(self, "estado_anterior", "esperando")
                
    def update_animation(self):
        self.time_counter += 0.1
        
        # Si está pensando, hacer un pulso suave y aleatorio
        if self.estado_actual == "pensando":
            for i in range(self.num_bars):
                self.target_heights[i] = 20 + math.sin(self.time_counter + i) * 15
                
        # Si está hablando, simular voz de Jarvis con ondas azules altas
        elif self.estado_actual == "hablando":
            for i in range(self.num_bars):
                ruido = hash(str(self.time_counter + i)) % 60
                self.target_heights[i] = 30 + ruido
                
        # Si está en silencio y esperando, mantenerlo chato
        elif self.estado_actual == "esperando" and self.energia_actual < 50:
            for i in range(self.num_bars):
                self.target_heights[i] = 5

        elif self.estado_actual == "hibernando":
            for i in range(self.num_bars):
                self.target_heights[i] = 2

        # Interpolar suavemente de current_heights a target_heights
        for i in range(self.num_bars):
            # Lerp (Linear Interpolation)
            diff = self.target_heights[i] - self.current_heights[i]
            self.current_heights[i] += diff * 0.3 # Factor de suavidad
            
        # Determinar color objetivo
        target_color = self.color_base
        if self.estado_actual == "grabando":
            target_color = self.color_activo
        elif self.estado_actual == "pensando":
            target_color = self.color_pensando
        elif self.estado_actual == "hablando":
            target_color = self.color_hablando
        elif self.estado_actual == "hibernando":
            if self.energia_actual > 100:
                target_color = QColor(200, 100, 100, 150)
                
        # Interpolar color
        r = self.current_render_color.red() + (target_color.red() - self.current_render_color.red()) * 0.1
        g = self.current_render_color.green() + (target_color.green() - self.current_render_color.green()) * 0.1
        b = self.current_render_color.blue() + (target_color.blue() - self.current_render_color.blue()) * 0.1
        a = self.current_render_color.alpha() + (target_color.alpha() - self.current_render_color.alpha()) * 0.1
        self.current_render_color.setRgb(int(r), int(g), int(b), int(a))
        
        # Determinar opacidad de ventana
        self.target_opacity = 0.0 if self.estado_actual == "hibernando" else 1.0
        diff_op = self.target_opacity - self.current_opacity
        self.current_opacity += diff_op * 0.1
        
        if abs(self.current_opacity - self.target_opacity) > 0.01:
            self.setWindowOpacity(max(0.0, min(1.0, self.current_opacity)))
            
            # Si es casi invisible, hacerlo intocable (click-through)
            if self.current_opacity < 0.1:
                self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            else:
                self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
            
        self.update() # Forzar repintado (llama a paintEvent)
        
        # Si está oculto, actualizar el icono del tray para mostrar la actividad
        if self.isHidden():
            avg_height = sum(self.current_heights) / len(self.current_heights)
            self.tray_icon.setIcon(self.create_tray_icon(avg_height))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Dibujar rectángulos redondeados
        bar_width = 15
        gap = 10
        total_width = (self.num_bars * bar_width) + ((self.num_bars - 1) * gap)
        
        start_x = (self.width() - total_width) // 2
        center_y = self.height() // 2
        
        painter.setPen(Qt.PenStyle.NoPen)
        
        for i in range(self.num_bars):
            h = max(4, self.current_heights[i])
            x = start_x + (i * (bar_width + gap))
            y = center_y - (h / 2)
            
            # Dibujar sombra (resplandor)
            painter.setBrush(QBrush(QColor(self.current_render_color.red(), self.current_render_color.green(), self.current_render_color.blue(), 50)))
            painter.drawRoundedRect(int(x - 2), int(y - 2), int(bar_width + 4), int(h + 4), 5, 5)
            
            # Dibujar barra principal
            painter.setBrush(QBrush(self.current_render_color))
            painter.drawRoundedRect(int(x), int(y), bar_width, int(h), 5, 5)

        # ====== Ojos al Front ======
        eye_radius = 12
        pupil_radius = 5
        eye_y = 35 # Altura de los ojos (parte superior)
        eye_spacing = 30
        center_win_x = self.width() // 2
        
        left_eye_center = QPointF(center_win_x - eye_spacing, eye_y)
        right_eye_center = QPointF(center_win_x + eye_spacing, eye_y)
        
        # Posición global de la ventana y ratón
        global_pos = self.mapToGlobal(self.rect().topLeft())
        mouse_pos = QCursor.pos()
        
        def draw_eye(eye_center):
            if self.estado_actual == "hibernando":
                # Ojos cerrados (línea curva hacia abajo simulando estar durmiendo)
                painter.setPen(QPen(QColor(150, 150, 150, 200), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                
                path = QPainterPath()
                # Puntos de la curva del ojo cerrado (como una U suave)
                path.moveTo(eye_center.x() - eye_radius + 2, eye_center.y())
                path.quadTo(eye_center.x(), eye_center.y() + eye_radius - 4, eye_center.x() + eye_radius - 2, eye_center.y())
                painter.drawPath(path)
                
                painter.setPen(Qt.PenStyle.NoPen)
                return

            # Dibujar esclerótica (blanco)
            painter.setBrush(QBrush(QColor(255, 255, 255, 220)))
            painter.drawEllipse(eye_center, eye_radius, eye_radius)
            
            # Calcular posición de la pupila
            # Centro del ojo global
            global_eye_x = global_pos.x() + eye_center.x()
            global_eye_y = global_pos.y() + eye_center.y()
            
            dx = mouse_pos.x() - global_eye_x
            dy = mouse_pos.y() - global_eye_y
            dist = math.hypot(dx, dy)
            
            # Limitar la pupila al borde del ojo
            max_dist = eye_radius - pupil_radius - 2
            if dist > max_dist and dist != 0:
                dx = (dx / dist) * max_dist
                dy = (dy / dist) * max_dist
                
            pupil_center = QPointF(eye_center.x() + dx, eye_center.y() + dy)
            
            # Dibujar pupila del color actual
            painter.setBrush(QBrush(self.current_render_color))
            painter.drawEllipse(pupil_center, pupil_radius, pupil_radius)

        draw_eye(left_eye_center)
        draw_eye(right_eye_center)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    widget = JarvisWidget()
    widget.show()
    
    from ui_agenda import AgendaWidget
    widget.agenda_widget = AgendaWidget()
    
    sys.exit(app.exec())
