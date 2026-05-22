import sys
import os
import time
import math

# Evitar crash en pythonw al intentar imprimir (sys.stdout no soporta escritura)
sys.stdout = open(os.path.join(os.path.dirname(__file__), "jarvis.log"), "w", encoding="utf-8", buffering=1)
sys.stderr = open(os.path.join(os.path.dirname(__file__), "jarvis_error.log"), "w", encoding="utf-8", buffering=1)

from PyQt6.QtWidgets import QApplication, QWidget, QPushButton, QSystemTrayIcon, QMenu
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QPointF
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QLinearGradient, QPainterPath, QIcon, QPixmap
from PyQt6.QtGui import QAction

import motor_audio

class AudioWorker(QThread):
    # Señal: estado, energia, conf
    update_signal = pyqtSignal(str, float, float)

    def run(self):
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
        
        # Orbe más pequeño (100x100)
        self.resize(100, 100)
        
        # Posición inicial (Abajo a la derecha)
        screen = QApplication.primaryScreen().geometry()
        self.move(screen.width() - 150, screen.height() - 150)
        
        # Variables de estado
        self.estado_actual = "esperando"
        self.estado_anterior = "esperando"
        self.energia_actual = 0
        self.modo_centinela = False
        self.modo_captura = False
        self.modo_grabando_obs = False
        
        # Colores Venom / Líquido Simbionte
        self.color_idle = QColor(15, 15, 20, 240) # Negro/Gris oscuro líquido
        self.color_escuchando = QColor(180, 0, 0, 255) # Rojo Carmesí (Carnage)
        self.color_pensando = QColor(80, 0, 120, 255) # Violeta oscuro profundo
        self.color_hablando = QColor(0, 50, 150, 255) # Azul líquido profundo
        self.color_centinela = QColor(10, 10, 10, 255) # Negro azabache para centinela
        self.color_obs = QColor(0, 100, 50, 255) # Verde tóxico
        self.color_captura = QColor(120, 0, 120, 255) # Magenta oscuro
        
        self.current_render_color = QColor(self.color_idle)
        
        # Animación de inercia líquida (drag effect)
        self.inercia_x = 0.0
        self.inercia_y = 0.0
        
        # Sistema de Puntos Líquido (Venom)
        self.num_points = 32
        self.base_radius = 28 # Radio base de la masa líquida
        self.target_radii = [self.base_radius] * self.num_points
        self.current_radii = [self.base_radius] * self.num_points
        
        # Timer de animación 60 FPS
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self.update_animation)
        self.anim_timer.start(16)
        
        # Timer de estado
        self.lock_timer = QTimer(self)
        self.lock_timer.timeout.connect(self.check_system_states)
        self.lock_timer.start(100)
        
        self.time_counter = 0.0
        self.drag_pos = None
        
        # Tray
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(self.create_tray_icon(0))
        
        tray_menu = QMenu()
        restore_action = QAction("Mostrar Jarvis", self)
        restore_action.triggered.connect(self.show_normal)
        
        desactivar_centinela_action = QAction("Desactivar Centinela", self)
        desactivar_centinela_action.triggered.connect(self.desactivar_centinela_manual)
        
        quit_action = QAction("Apagar Jarvis", self)
        quit_action.triggered.connect(QApplication.instance().quit)
        
        tray_menu.addAction(restore_action)
        tray_menu.addAction(desactivar_centinela_action)
        tray_menu.addAction(quit_action)
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()
        self.tray_icon.activated.connect(self.on_tray_activated)

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
            
            # Efecto físico: la masa líquida se arrastra (inercia opuesta al movimiento)
            self.inercia_x -= delta.x() * 1.5
            self.inercia_y -= delta.y() * 1.5
            dist = math.hypot(self.inercia_x, self.inercia_y)
            if dist > 30:
                self.inercia_x = (self.inercia_x / dist) * 30
                self.inercia_y = (self.inercia_y / dist) * 30

    def mouseReleaseEvent(self, event):
        self.drag_pos = None

    def show_normal(self):
        self.show()
        self.activateWindow()
        
    def on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_normal()

    def desactivar_centinela_manual(self):
        if os.path.exists("centinela.lock"):
            try:
                os.remove("centinela.lock")
            except Exception:
                pass
        self.modo_centinela = False

    def create_tray_icon(self, vol):
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QBrush(self.current_render_color))
        painter.setPen(Qt.PenStyle.NoPen)
        r = 8 + (vol / 50.0) * 8
        painter.drawEllipse(QPointF(16, 16), r, r)
        painter.end()
        return QIcon(pixmap)

    def on_audio_update(self, estado, energia, conf):
        self.estado_actual = estado
        self.energia_actual = energia

    def check_system_states(self):
        lock_file = motor_audio.LOCK_FILE
        if os.path.exists(lock_file):
            if self.estado_actual != "hablando":
                self.estado_anterior = self.estado_actual
            self.estado_actual = "hablando"
        else:
            if self.estado_actual == "hablando":
                self.estado_actual = getattr(self, "estado_anterior", "esperando")
                
        self.modo_centinela = os.path.exists("centinela.lock")
        self.modo_captura = os.path.exists("captura.lock")
        self.modo_grabando_obs = os.path.exists("obs_rec.lock") # Para el modo cámara verde
        
        if os.path.exists("pensando.lock"):
            self.estado_actual = "pensando"
        
        try:
            ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cerebro_actual.txt")
            if os.path.exists(ruta):
                with open(ruta, "r", encoding="utf-8") as f:
                    self.cerebro_actual = f.read().strip()
            else:
                self.cerebro_actual = "gemini"
        except:
            self.cerebro_actual = "gemini"
                
    def update_animation(self):
        self.time_counter += 0.1
        
        target_color = self.color_idle
        
        # Decaimiento suave de la inercia (fricción viscosa)
        self.inercia_x *= 0.85
        self.inercia_y *= 0.85
        
        # Pequeña inercia autónoma para que no esté estático (el líquido "burbujea")
        if self.estado_actual in ["hablando", "pensando"]:
            self.inercia_x += math.sin(self.time_counter * 3) * 1.5
            self.inercia_y += math.cos(self.time_counter * 2.5) * 1.5
        
        # Velocidad del movimiento base según estado
        vel_base = 0.8 if self.estado_actual in ["esperando", "hibernando"] else 2.5
        
        # Movimiento base de líquido simbiótico (Venom)
        base_noise = []
        for i in range(self.num_points):
            # Onda suave pero constante para dar sensación de vida viscosa
            onda1 = math.sin(self.time_counter * vel_base + i * (math.pi / 4)) * 2.5
            onda2 = math.cos(self.time_counter * (vel_base * 0.7) - i * (math.pi / 3)) * 1.5
            base_noise.append(onda1 + onda2)
        
        # Inicializar todos los radios con el ruido base y la deformación por inercia
        for i in range(self.num_points):
            angle = i * (2 * math.pi / self.num_points)
            # Dot product: alarga los puntos en la dirección opuesta al movimiento (cola) y achata el frente
            dot = math.cos(angle) * self.inercia_x + math.sin(angle) * self.inercia_y
            self.target_radii[i] = self.base_radius + base_noise[i] + dot
            
        # Determinar el Perfil de la Estela según el estado
        if self.modo_captura:
            target_color = self.color_captura
            # Un cuadrado más puntiagudo/fotográfico
            for i in range(self.num_points):
                if i % 8 == 0: # 4 Esquinas en 32 puntos
                    self.target_radii[i] += 15
        elif self.modo_grabando_obs:
            target_color = self.color_obs
            # Modo espinoso para la grabación de pantalla
            for i in range(self.num_points):
                if i % 4 == 0:
                    self.target_radii[i] += 12
        elif self.estado_actual == "grabando":
            target_color = self.color_escuchando
            # Modo Carnage: reacciona brutalmente a la voz con picos, pero limitado para no deformarse demasiado
            vol = min(15, self.energia_actual / 80.0) # Limitado a un máximo de +15 radio
            for i in range(self.num_points):
                # Picos asimétricos rápidos
                spike = math.sin(i * 7 + self.time_counter * 15) * vol
                ruido = (hash(str(self.time_counter + i)) % 10) * (vol / 10) if vol > 2 else 0
                self.target_radii[i] += max(0, spike + ruido)
                
        elif self.estado_actual == "hablando":
            target_color = self.color_hablando
            # Modo Venom pacífico: olas rítmicas profundas
            vol_simulado = 15.0
            for i in range(self.num_points):
                onda = math.sin(self.time_counter * 4 + i * (math.pi / 2)) * vol_simulado
                self.target_radii[i] += max(0, onda)
                
        elif self.estado_actual == "pensando":
            cerebro = getattr(self, "cerebro_actual", "gemini")
            
            if cerebro == "claude":
                target_color = QColor(230, 90, 20, 255) # Naranja Claude
                # Logo de Anthropic: Estrella irregular / burst
                for i in range(self.num_points):
                    onda1 = math.sin(i * (11 * math.pi * 2 / self.num_points) + self.time_counter * 5) * 14
                    onda2 = math.cos(i * (5 * math.pi * 2 / self.num_points) - self.time_counter * 3) * 6
                    self.target_radii[i] += max(0, onda1 + onda2) # Puntas caóticas hacia afuera
                    
            elif cerebro == "llama":
                target_color = QColor(20, 180, 50, 255) # Verde fijo como pidió el usuario
                # Forma Meta (Infinito / Figura 8)
                for i in range(self.num_points):
                    theta = i * (math.pi * 2 / self.num_points)
                    # abs(cos(theta)) genera un infinito horizontal al pinchar arriba y abajo
                    pincho = abs(math.cos(theta))
                    # Hacemos que el radio base se adapte a esta figura, más un ligero latido
                    self.target_radii[i] = self.base_radius * (0.3 + 0.8 * pincho) + math.sin(self.time_counter * 3) * 3
                    
            else: # Gemini o por defecto
                # Modo Gemini: Estrella brillante de 4 puntas y color RGB (Arcoíris)
                h = int((self.time_counter * 60) % 360) # Cambia el Hue con el tiempo
                target_color = QColor.fromHsv(h, 240, 255, 255)
                for i in range(self.num_points):
                    theta = i * (math.pi * 2 / self.num_points)
                    # abs(cos(2*theta)) genera 4 puntas largas (0, 90, 180, 270)
                    estrella = abs(math.cos(2 * theta))
                    # Rotamos la estrella lentamente sumándole self.time_counter al ángulo
                    theta_rot = theta + self.time_counter * 0.5
                    estrella_rotada = abs(math.cos(2 * theta_rot))
                    # Aplicar forma de estrella más un ligero destello
                    self.target_radii[i] = self.base_radius * (0.3 + 0.7 * estrella_rotada) + (hash(str(self.time_counter+i))%5)
                
        elif self.modo_centinela:
            target_color = self.color_centinela
            # Modo alerta: picos afilados estáticos pero viscosos
            for i in range(self.num_points):
                if i % 2 == 0:
                    self.target_radii[i] += 8
                else:
                    self.target_radii[i] -= 4
            
        elif self.estado_actual == "hibernando":
            target_color = QColor(10, 10, 10, 200)
            for i in range(self.num_points):
                self.target_radii[i] = 10 + (base_noise[i] * 0.5)

        # Interpolación LÍQUIDA (Lerp de los radios)
        for i in range(self.num_points):
            diff = self.target_radii[i] - self.current_radii[i]
            self.current_radii[i] += diff * 0.15 # 0.15 = Velocidad viscosa
            
        # Interpolación de Colores
        r = self.current_render_color.red() + (target_color.red() - self.current_render_color.red()) * 0.1
        g = self.current_render_color.green() + (target_color.green() - self.current_render_color.green()) * 0.1
        b = self.current_render_color.blue() + (target_color.blue() - self.current_render_color.blue()) * 0.1
        a = self.current_render_color.alpha() + (target_color.alpha() - self.current_render_color.alpha()) * 0.1
        self.current_render_color.setRgb(int(r), int(g), int(b), int(a))
        
        self.update() # Forzar repintado
        
        if self.isHidden():
            self.tray_icon.setIcon(self.create_tray_icon(self.energia_actual))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        center_x = self.width() // 2
        center_y = self.height() // 2
        
        # 1. Calcular Puntos de la Estela Líquida (Morphing)
        points = []
        for i in range(self.num_points):
            angle = i * (2 * math.pi / self.num_points)
            r = self.current_radii[i]
            x = center_x + math.cos(angle) * r
            y = center_y + math.sin(angle) * r
            points.append(QPointF(x, y))
            
        # Crear Path Cerrado Curvo (Spline de Bézier)
        path = QPainterPath()
        path.moveTo(points[0])
        for i in range(self.num_points):
            p_current = points[i]
            p_next = points[(i + 1) % self.num_points]
            
            # Puntos de control (midpoints) para que la curva pase suavemente
            mid_x = (p_current.x() + p_next.x()) / 2
            mid_y = (p_current.y() + p_next.y()) / 2
            path.quadTo(p_current, QPointF(mid_x, mid_y))
            
        # 2. Dibujar el Simbionte (Toda la masa líquida)
        base_color = QColor(self.current_render_color)
        
        # Efecto 3D / Glossy (Luz arriba a la izquierda, sombra abajo a la derecha)
        max_r = max(self.current_radii) if self.current_radii else 50
        grad = QLinearGradient(center_x - max_r, center_y - max_r, center_x + max_r, center_y + max_r)
        grad.setColorAt(0.0, base_color.lighter(140)) # Reflejo brillante
        grad.setColorAt(0.4, base_color)             # Color base
        grad.setColorAt(1.0, base_color.darker(200)) # Sombra profunda
        
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(grad))
        painter.drawPath(path)
        
        # (Brillos eliminados por petición del usuario para dejar la masa limpia)
        
        # (Icono de Micrófono eliminado por petición del usuario para dejar la masa limpia)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Iniciar gestor de widgets para que reciba comandos
    try:
        import ui_widgets
        widget_manager = ui_widgets.WidgetManager()
    except Exception as e:
        print(f"Error al cargar ui_widgets: {e}")
        
    widget = JarvisWidget()
    widget.show()
    sys.exit(app.exec())
