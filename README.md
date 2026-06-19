# 📹 Video Fútbol Análisis
### Pipeline Automatizado de Seguimiento y Análisis Táctico con Drones

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue?style=for-the-badge&logo=python&logoColor=white" alt="Python"/>
  <img src="https://img.shields.io/badge/OpenCV-4.x-green?style=for-the-badge&logo=opencv&logoColor=white" alt="OpenCV"/>
  <img src="https://img.shields.io/badge/YOLOv8-Ultralytics-red?style=for-the-badge" alt="YOLOv8"/>
  <img src="https://img.shields.io/badge/NumPy-Scientific-orange?style=for-the-badge&logo=numpy&logoColor=white" alt="NumPy"/>
  <img src="https://img.shields.io/badge/Pandas-Analytics-150458?style=for-the-badge&logo=pandas&logoColor=white" alt="Pandas"/>
  <img src="https://img.shields.io/badge/pytest-Testing-yellow?style=for-the-badge&logo=pytest&logoColor=white" alt="pytest"/>
</p>

---

> **Un motor de análisis táctico de fútbol de código abierto, diseñado para procesar video de drones y extraer métricas avanzadas de comportamiento colectivo e individual en tiempo real.**

Este repositorio implementa un pipeline completo y modular: desde la captura de frames de un video `.mp4` hasta la generación de reportes tácticos interactivos con estadísticas, gráficas y clips con realidad aumentada. La arquitectura está diseñada para que cualquier nueva habilidad analítica pueda conectarse al sistema sin modificar una sola línea del código base.

---

## 🗺️ Tabla de Contenidos

- [Visión General del Sistema](#-visión-general-del-sistema)
- [Arquitectura Modular y Ecosistema de Skills](#-arquitectura-modular-y-ecosistema-de-skills)
- [Catálogo de Skills Analíticas](#-catálogo-de-skills-analíticas)
- [Estructura del Proyecto](#-estructura-del-proyecto)
- [Instalación y Configuración](#-instalación-y-configuración)
- [Ejecución](#-ejecución)
- [Infraestructura de Testing](#-infraestructura-de-testing)
- [Integración con LLMs (Together AI)](#-integración-con-llms-together-ai)
- [Hoja de Ruta](#-hoja-de-ruta)

---

## 🌐 Visión General del Sistema

El pipeline se estructura en **cuatro etapas secuenciales**, cada una construyendo sobre la salida de la anterior:

```
┌─────────────────────────────────────────────────────────────────────┐
│   ENTRADA: Video .mp4 grabado con dron de alta altitud              │
└────────────────────────┬────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│  ETAPA 1 · DETECCIÓN                                                │
│  DroneDetector (YOLOv8-P2S3A)                                       │
│  · Detecta jugadores, árbitros y balón por frame                    │
│  · Clasifica equipos por color de camiseta (DBSCAN sobre HSV)       │
└────────────────────────┬────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│  ETAPA 2 · SEGUIMIENTO (Multi-Object Tracking)                      │
│  RobustDroneTracker                                                 │
│  · Filtro de Kalman para predicción de movimiento                   │
│  · Algoritmo Húngaro (IoU + distancia + matiz de color)             │
│  · Re-identificación offline entre tracklets fragmentados           │
└────────────────────────┬────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│  ETAPA 3 · PROYECCIÓN GEOMÉTRICA                                    │
│  PitchRegistrator + TrajectoryDataLayer                             │
│  · Homografía 3×3 (cámara → plano de campo 105×68 m)               │
│  · Interpolación cuadrática del balón en gaps de detección          │
│  · Exportación a DataFrame MultiIndex (frame_id, player_id)         │
└────────────────────────┬────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│  ETAPA 4 · ANÁLISIS TÁCTICO (Ecosistema de Skills)                  │
│  analytics/@register_skill + FootballTacticalAnalyzer               │
│  · Módulos analíticos plug-and-play conectados mediante decorador   │
│  · Reportes en Markdown, Dashboard HTML y JSON                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 🔌 Arquitectura Modular y Ecosistema de Skills

El corazón del proyecto es el **módulo `analytics/`** y su patrón de registro dinámico.

### El Problema que Resuelve

En proyectos de análisis deportivo convencionales, agregar una nueva métrica requiere modificar el orquestador central, actualizar los reportes, ajustar los tests y reescribir la documentación. Esto crea acoplamiento y deuda técnica.

### La Solución: `@register_skill`

Cualquier clase de análisis puede registrarse en el sistema con un único decorador:

```python
# analytics/mi_nueva_metrica.py

from analytics import register_skill

@register_skill("mi_metrica")
class MiNuevaMetrica:
    def calculate(self, trajectory_df, ...):
        # Lógica analítica completamente aislada
        return resultado_dict
```

El sistema la descubre automáticamente mediante **autodiscovery** al iniciar el pipeline. Desde `main.py`, la invocación es siempre la misma, independientemente de la skill:

```python
import analytics

# Obtener cualquier skill registrada por su nombre
MiClase = analytics.get_skill("mi_metrica")
instancia = MiClase()
resultado = instancia.calculate(trajectory_df)
```

### Flujo de Datos Interno

Todas las skills consumen el mismo contrato de datos: el **`TrajectoryDataLayer` DataFrame**, un `pandas.DataFrame` con `MultiIndex(frame_id, player_id)` y las columnas estándar del pipeline:

| Columna | Tipo | Descripción |
|---|---|---|
| `x_meter` | `float` | Coordenada X del jugador en metros (plano real) |
| `y_meter` | `float` | Coordenada Y del jugador en metros (plano real) |
| `x_pixel` | `float` | Coordenada X en píxeles del frame original |
| `y_pixel` | `float` | Coordenada Y en píxeles del frame original |
| `label` | `str` | `"player"`, `"ball"` o `"referee"` |
| `team_id` | `int` | `0` (Equipo A), `1` (Equipo B) o `-1` (desconocido) |
| `confidence` | `float` | Confianza de detección YOLO `[0.0, 1.0]` |
| `reconstructed` | `bool` | `True` si la coordenada fue interpolada |

---

## 🛠️ Catálogo de Skills Analíticas

A continuación se presenta el catálogo completo de skills, tanto las ya implementadas como las prospectadas para futuras fases del proyecto.

---

### ✅ `possession` — Análisis de Posesión del Balón
**Estado:** Implementado · `analytics/possession.py`

Calcula la posesión del balón por equipo y jugador en cada frame usando **proximidad espacial normalizada** (Guo et al., 2026). La distancia de cada jugador al balón se normaliza por la altura de su bounding box para compensar la altitud variable del dron. Un mecanismo de **histéresis `(T_in, T_out)`** evita cambios de posesión espurios durante disputas prolongadas.

```
D_norm(i) = d(jugador_i, balón) / H_i

Adquisición de posesión: D_norm < T_in  (ej. 1.5)
Pérdida de posesión:     D_norm > T_out (ej. 2.5)
```

**Salidas:** `possession_summary.csv` · % posesión por equipo · cambios de posesión · racha máxima

---

### ✅ `match_stats` — Estadísticas Descriptivas del Partido
**Estado:** Implementado · `analytics/match_stats.py`

Calcula las métricas básicas descriptivas del partido directamente sobre el DataFrame de trayectorias. Todos los campos se exportan en español.

| Grupo | Métricas incluidas |
|---|---|
| **A · Volumen** | Frames procesados, duración efectiva, tasa de detección del balón, jugadores activos/frame |
| **B · Posesión** | % por equipo, posesión no disputada, racha máxima (segundos), cambios de posesión |
| **C · Distancia** | Distancia total por equipo, media por jugador, máximo individual, velocidad pico estimada |

**Salidas:** `match_stats.json` · Sección 4 en `match_report.md`

---

### 🔄 `compactness` — Compactación Táctica (Convex Hull)
**Estado:** Parcialmente implementado · `football_tactical_analytics_engine.py`

Calcula el **área del polígono convexo** que envuelve a los jugadores de cada equipo en coordenadas de metros reales. Un área pequeña indica un bloque defensivo compacto; un área grande revela amplitud en fases de ataque o presión alta. Se calcula también el centroide de cada equipo y la **distancia inter-centroide** entre ambos equipos.

**Salidas:** `metricas_compactacion_es.csv` · área de Hull por frame · centroide por equipo

---

### 🗺️ `zone_control` — Dominio Espacial y Mapas de Calor
**Estado:** Prospectado · Fase 2

Divide el campo real (105×68 m) en zonas funcionales y calcula el **porcentaje de ocupación** de cada equipo en cada zona a lo largo del partido. Genera **mapas de calor de influencia** (heatmaps) para visualizar las posiciones más frecuentes de cada jugador.

```
Tercio defensivo:  x ∈ [0, 35) m
Tercio medio:      x ∈ [35, 70) m
Tercio ofensivo:   x ∈ [70, 105] m
```

**Salidas:** Heatmap PNG por jugador · tabla de ocupación por zonas · `zone_control.json`

---

### 🕸️ `pass_network` — Redes de Pases y Líneas de Visión
**Estado:** Parcialmente implementado · `football_tactical_analytics_engine.py`

Detecta **carriles de pase** entre jugadores del equipo en posesión y determina si están **bloqueados por defensores** o libres. Permite reconstruir la estructura de la red de pases del equipo mediante grafos de proximidad táctica.

**Salidas:** Grafo de pases por fase · carriles bloqueados/libres · visualización SVG sobre campo 2D

---

### 🔷 `tactical_shape` — Reconocimiento de Formación Táctica
**Estado:** Prospectado · Fase 3

Identifica automáticamente el **esquema táctico** de cada equipo (ej. 4-4-2, 4-3-3, 3-5-2) en distintas fases del juego (posesión propia, pérdida, presión alta). Utiliza **clustering jerárquico** sobre las posiciones promedio de los jugadores proyectadas al campo real.

**Salidas:** Etiqueta de formación por fase · historial de cambios de sistema · confianza de identificación

---

### ⚡ `pressing_intensity` — Intensidad de Presión (PPDA)
**Estado:** Prospectado · Fase 3

Estima el **índice PPDA** (Passes Allowed Per Defensive Action) basado en las transiciones de posesión y la distancia de los defensores al portador del balón en campo contrario. Mide qué tan agresivo es el equipo sin balón para recuperarlo.

**Salidas:** PPDA por período · intensidad de presión alta vs. baja · línea de presión media (m)

---

### 🏃 `fatigue_load` — Estimación de Carga Física y Fatiga
**Estado:** Prospectado · Fase 3

Calcula las **cargas de trabajo físicas** de cada jugador a partir de sus trayectorias en metros reales. Clasifica el esfuerzo en bandas de velocidad (caminando, trotando, corriendo, sprint) y estima el impacto acumulado de sprints de alta intensidad (> 20 km/h).

```
Bandas de velocidad:
  Caminar:  v < 7  km/h
  Trotar:   7 ≤ v < 14 km/h
  Correr:   14 ≤ v < 20 km/h
  Sprint:   v ≥ 20 km/h   ← Zona de carga alta
```

**Salidas:** Distancia por banda por jugador · tiempo en zona de sprint · índice de fatiga acumulada

---

### 🎬 `highlight_extractor` — Clips de Highlights con Overlays AR
**Estado:** Parcialmente implementado · `football_tactical_analytics_engine.py`

Detecta automáticamente **momentos de alta intensidad táctica** en el video (recuperaciones de balón, presión alta, cambios de posesión) y exporta clips `.mp4` recortados. Sobre cada clip aplica **gráficos de realidad aumentada** usando homografía inversa:

- Líneas de bloque defensivo entre jugadores
- Arcos de movimiento colectivo
- Etiquetas de distancia entre jugadores seleccionados
- Identificadores de equipo y número de jugador

**Salidas:** Clips `.mp4` por evento · overlays AR renderizados en píxeles del frame original

---

## 📁 Estructura del Proyecto

```
video_futbol_analisis/
│
├── main.py                          # Orquestador principal del pipeline
├── run_tactical_analysis.py         # Entrypoint para análisis táctico offline
├── football_tactical_analytics_engine.py  # Motor de análisis avanzado
│
├── core/                            # Módulos del núcleo del pipeline
│   ├── detector.py                  # DroneDetector (YOLOv8 + DBSCAN)
│   ├── tracker.py                   # RobustDroneTracker (Kalman + Húngaro)
│   └── homography.py                # PitchRegistrator (Homografía)
│
├── wrappers/                        # Capa de datos y abstracción
│   └── data_layers.py               # TrajectoryDataLayer (DataFrame + interpolación)
│
├── analytics/                       # 🔌 Ecosistema de Skills Analíticas
│   ├── __init__.py                  # Registro (@register_skill) y autodiscovery
│   ├── possession.py                # ✅ Skill: Análisis de Posesión
│   └── match_stats.py               # ✅ Skill: Estadísticas Descriptivas
│
├── src/                             # Módulos auxiliares y utilidades
│   ├── ingestion/
│   │   └── video_reader.py          # DroneVideoIngestor (decord, zero-copy)
│   ├── preprocessing/
│   │   └── homography_calibrator.py # PitchCalibrator (interactivo/headless)
│   └── utils/
│       └── llm_client.py            # Cliente Together AI (LLM integration)
│
├── tests/                           # Suite de tests E2E (60+ casos, 4 tiers)
│   ├── test_tier1.py                # Tier 1: Cobertura de funcionalidades
│   ├── test_tier2.py                # Tier 2: Casos borde y límite
│   ├── test_tier3.py                # Tier 3: Combinaciones cruzadas
│   ├── test_tier4.py                # Tier 4: Escenarios reales (subprocess)
│   └── test_tier1_match_stats.py    # Tests específicos de match_stats
│
├── inputs/                          # Videos .mp4 de entrada
├── outputs/                         # Salidas organizadas por match_id
│   └── {match_id}/
│       ├── final_dataset/
│       │   ├── trajectories.csv     # Dataset de trayectorias procesadas
│       │   └── trajectories.parquet
│       └── reports/
│           ├── match_report.md      # Reporte en Markdown (español)
│           ├── match_stats.json     # Estadísticas en JSON
│           ├── possession_summary.csv
│           └── dashboard.html       # Dashboard interactivo (Chart.js)
│
├── agent_config.yaml                # Configuración de agentes LLM
├── requirements_llm.txt             # Dependencias del cliente LLM
├── TEST_INFRA.md                    # Documentación de la infraestructura de tests
└── .env                             # Variables de entorno (API keys)
```

---

## ⚙️ Instalación y Configuración

### Requisitos del Sistema
- Python 3.10+
- OpenCV (`cv2`)
- PyTorch (para YOLOv8, opcional — el sistema corre en modo simulación sin él)

### Instalación de Dependencias

```powershell
# Clonar el repositorio
git clone https://github.com/tu-usuario/video_futbol_analisis.git
cd video_futbol_analisis

# Instalar dependencias principales
pip install opencv-python numpy pandas scipy scikit-learn

# Opcional: YOLOv8 para detección real
pip install ultralytics

# Opcional: soporte de formato Parquet
pip install pyarrow

# Dependencias del cliente LLM (Together AI)
pip install -r requirements_llm.txt
```

### Configuración del Entorno

Crea un archivo `.env` en la raíz con las siguientes variables:

```env
# Together AI (para integración de LLMs)
OPEN_API_KEY=tu_api_key_aqui
OPEN_API_BASE=https://api.together.xyz/v1
```

---

## 🚀 Ejecución

### Procesamiento de un Video Individual

```powershell
# Procesamiento estándar (1 frame por segundo para video a 30fps)
python main.py --video inputs/partido.mp4

# Procesamiento de mayor densidad (1 de cada 15 frames)
python main.py --video inputs/partido.mp4 --stride 15

# Limitar la cantidad de frames a procesar
python main.py --video inputs/partido.mp4 --frames 500

# Downscale de 4K a 1080p para mayor velocidad
python main.py --video inputs/partido.mp4 --resize-1080p

# Con modelo YOLO real
python main.py --video inputs/partido.mp4 --weights yolov8-p2s3a.pt
```

### Modo Batch (múltiples videos)

```powershell
# Procesa todos los .mp4 en la carpeta inputs/
python main.py --batch
```

### Análisis Táctico Offline

```powershell
# Análisis táctico sobre trayectorias ya procesadas
python run_tactical_analysis.py --trajectory outputs/partido/final_dataset/trajectories.csv
```

---

## 🧪 Infraestructura de Testing

El proyecto implementa un esquema de testing **E2E opaco de 4 niveles** con **81+ casos de prueba** que corren en segundos usando videos mock generados programáticamente (sin binarios pesados en el repositorio).

```powershell
# Ejecutar la suite completa
pytest tests/ -v

# Ejecutar por tier
pytest tests/test_tier1.py -v        # Cobertura funcional
pytest tests/test_tier2.py -v        # Casos borde y límite
pytest tests/test_tier3.py -v        # Combinaciones cruzadas
pytest tests/test_tier4.py -v        # Escenarios reales (subprocess)

# Tests de las nuevas estadísticas
pytest tests/test_tier1_match_stats.py -v
```

| Tier | Propósito | N° de Tests |
|---|---|---|
| **Tier 1** | Cobertura nominal de cada feature | 25 |
| **Tier 2** | Casos borde, inputs corruptos, divisiones por cero | 25 |
| **Tier 3** | Integraciones cruzadas entre módulos | 5 |
| **Tier 4** | Pipeline completo vía subprocess | 5 |
| **Match Stats** | Estadísticas descriptivas Stage 1 | 4 |

---

## 🤖 Integración con LLMs (Together AI)

El pipeline incluye una integración opcional con modelos de lenguaje grandes a través de **Together AI** para soporte a análisis asistido e interpretación táctica.

```python
from src.utils.llm_client import TogetherClient

client = TogetherClient()
respuesta = client.chat(
    model="deepseek-ai/DeepSeek-V3",
    messages=[{"role": "user", "content": "Interpreta estas métricas tácticas..."}]
)
```

Los modelos recomendados para este proyecto son:
- **`deepseek-ai/DeepSeek-V3`** — análisis de código y razonamiento matemático
- **`meta-llama/Llama-3.3-70B-Instruct-Turbo`** — generación de reportes en español

---

## 📅 Hoja de Ruta

| Fase | Skills / Módulos | Estado |
|---|---|---|
| **Fase 1** | Detección (YOLOv8), Seguimiento (Kalman/Húngaro), Homografía | ✅ Completado |
| **Fase 1** | `possession` — Análisis de Posesión | ✅ Completado |
| **Fase 1** | `match_stats` — Estadísticas Descriptivas (Grupos A, B, C) | ✅ Completado |
| **Fase 1** | Compactación Táctica (Convex Hull) — básico | 🔄 En progreso |
| **Fase 1** | Extracción de Highlights — detección de eventos | 🔄 En progreso |
| **Fase 2** | `zone_control` — Dominio Espacial y Heatmaps | 📋 Planificado |
| **Fase 2** | `match_stats` Grupos D (Zonas) y E (Compactness) | 📋 Planificado |
| **Fase 2** | Overlays AR en clips de video (homografía inversa) | 📋 Planificado |
| **Fase 3** | `tactical_shape` — Reconocimiento de Formaciones | 🔭 Prospectado |
| **Fase 3** | `pressing_intensity` — PPDA | 🔭 Prospectado |
| **Fase 3** | `fatigue_load` — Carga Física y Estimación de Fatiga | 🔭 Prospectado |
| **Fase 4** | Dashboard Web interactivo en tiempo real | 🔭 Prospectado |

---

## 📚 Referencias

- Guo et al. (2026). *YOLOv8-P2S3A/HWD3A: High-Altitude Drone Soccer Tracking*. Preprint.
- Kalman, R.E. (1960). *A New Approach to Linear Filtering and Prediction Problems*. ASME.
- Kuhn, H.W. (1955). *The Hungarian Method for the Assignment Problem*. Naval Research Logistics.

---

<p align="center">
  Construido con 🧠 análisis táctico, 📐 geometría computacional y 🤖 agentes de IA avanzados.<br/>
  <i>Un motor escalable para revolucionar el análisis táctico en el fútbol moderno.</i>
</p>
