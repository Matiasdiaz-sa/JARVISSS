# JARVISSS

Un asistente de Inteligencia Artificial Avanzado e interactivo con una arquitectura multicerebro (Claude 4.6 Sonnet como principal, con respaldos locales y en la nube), diseñado para controlar el sistema operativo, gestionar herramientas y responder a peticiones con su propia interfaz visual, notificaciones de voz e integraciones.

---

## 💻 Requisitos Previos

Antes de instalar y ejecutar Jarvis en una computadora nueva, asegúrate de tener:

1. **Python 3.10 o superior** instalado y agregado al `PATH`. (Recomendable Python 3.10 o 3.11).
2. **Git** instalado para clonar el repositorio.
3. Una cámara web / micrófono configurados si planeas usar los comandos de voz y visión.

---

## 🛠️ Instalación paso a paso

### 1. Clonar el Repositorio

Abre una terminal o símbolo del sistema (CMD/PowerShell) y ejecuta:
```bash
git clone https://github.com/Matiasdiaz-sa/JARVISSS.git
cd JARVISSS
```

### 2. Crear y activar el Entorno Virtual (Recomendado)
Es vital utilizar un entorno virtual para no tener conflictos con librerías globales de la PC.
```bash
# Crear el entorno
python -m venv venv

# Activar el entorno (en Windows)
.\venv\Scripts\activate

# Activar el entorno (en Mac/Linux)
source venv/bin/activate
```

### 3. Instalar las dependencias
Con el entorno virtual activado, instala todas las librerías necesarias:
```bash
pip install -r requirements.txt
```

---

## 🔑 Configuración del archivo `.env`

Jarvis depende de diversas APIs para su "cerebro", voz y herramientas externas (Spotify, OBS). Debes crear un archivo llamado `.env` en la carpeta raíz del proyecto y agregar las claves de API necesarias.

> **¡IMPORTANTE!** Nunca compartas ni subas tu archivo `.env` a GitHub. Ya está ignorado por defecto en el `.gitignore`.

Crea el archivo `.env` y copia esta estructura, llenando los datos con tus claves reales:

```env
# Cerebro Principal (Anthropic)
ANTHROPIC_API_KEY=tu_clave_de_anthropic_aqui

# Cerebros de Respaldo y Herramientas (Obligatorios para redundancia)
GROQ_API_KEY=tu_clave_de_groq_aqui
GEMINI_API_KEY=tu_clave_de_gemini_aqui

# Integración con Spotify (Para control de música)
SPOTIPY_CLIENT_ID=tu_cliente_id_de_spotify
SPOTIPY_CLIENT_SECRET=tu_cliente_secret_de_spotify
SPOTIPY_REDIRECT_URI=http://localhost:8080

# Integración con OBS Studio (Opcional, para grabar/streamear)
OBS_PASSWORD=tu_contraseña_de_obs
```

### ¿De dónde sacar estas APIs?
- **Anthropic (Claude):** https://console.anthropic.com/
- **Groq (Llama 3):** https://console.groq.com/keys
- **Gemini (Google):** https://aistudio.google.com/
- **Spotify:** Entra a [Spotify Developer](https://developer.spotify.com/dashboard), crea una App y añade `http://localhost:8080` en los Redirect URIs de tu aplicación.

---

## 🚀 Cómo Iniciar Jarvis

Una vez que las librerías estén instaladas y tu `.env` esté configurado correctamente, puedes iniciar Jarvis.

Siempre asegúrate de que el entorno virtual esté activado y ejecuta:

```bash
python main.py
```

### ¿Qué sucederá?
1. Aparecerá la ventana transparente con la forma visual de Jarvis (la estrella naranja de Claude si se conecta a tu API correctamente).
2. Se cargarán todas las rutinas automáticas (`rutinas.json`) y el sistema de memoria (`memoria.json` y `memoria_jarvis.json`).
3. Podrás interactuar con él tanto por voz (usando el micrófono) como enviando comandos de texto si tienes implementada una caja de control.

---

## 🧠 Arquitectura del Sistema (OpenClaw + Llama 3.3)

La arquitectura de Jarvis ha evolucionado para centrarse en la velocidad y la capacidad de orquestación autónoma:

1. **Orquestador Central (OpenClaw):** El cerebro ya no es un simple script, sino que está impulsado por **OpenClaw**, un framework de agentes que permite a la IA decidir qué herramientas usar, leer memoria a largo plazo y ejecutar acciones complejas en tu PC automáticamente.
2. **Motor LLM Ultrarrápido:** El motor lógico principal utiliza **Llama 3.3 70B** a través de la API de Groq, asegurando respuestas y decisiones en fracciones de segundo.
3. **Escucha Activa (OpenWakeWord):** Jarvis está siempre a la escucha con un modelo de IA entrenado localmente (`hey_jarvis.onnx`), que procesa audio sin conexión y detecta la palabra mágica sin consumir recursos de internet.
4. **Respuestas Inmediatas:** Las ejecuciones de aplicaciones del sistema disparan el motor de voz (Edge TTS) en hilos de fondo paralelos. Cuando pides "Abre Spotify", Jarvis te habla en la misma milésima de segundo en la que se abre la aplicación, eliminando la latencia del LLM.
5. **Interfaz Visual Dinámica:** Un widget transparente con motor de renderizado Qt PyQt6 que reacciona de forma fluida a la voz con animaciones "Venom RGB" cuando está pensando.

> **Atajo Global:** Presiona **`Ctrl + Alt + J`** en cualquier momento para hablar con Jarvis sin decir la palabra mágica.

---

## 🛑 Solución de problemas comunes

- **Error `No module named 'litellm'` o similares:** Significa que olvidaste activar el entorno virtual (`venv`) antes de correr Jarvis, o que no ejecutaste `pip install -r requirements.txt`.
- **Cierre inesperado con mensaje de "Puerto 8000 ocupado":** Jarvis usa FastAPI en el puerto 8000 internamente. Si ya tienes otro servicio o una sesión previa de Jarvis "colgada", ciérrala desde el Administrador de Tareas (matando `python.exe`) o usando el script correspondiente si lo tienes en el sistema.
- **No se escucha la voz (Edge TTS):** Verifica tu conexión a internet o el volumen de salida de tu sistema operativo predeterminado.
- **Jarvis se pone Verde al iniciarlo:** Esto significa que tu API de Anthropic y de Google fallaron (o no tienen saldo/están mal escritas en el `.env`). Revisa las variables y reinicia el programa.
