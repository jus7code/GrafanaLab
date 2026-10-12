# Plataforma de Telemetría IoT — Stack Completo (MQTT → TSDB → Grafana)

Este repositorio contiene la implementación completa del stack de telemetría IoT sobre Docker Compose, diseñado para la ingesta continua, persistencia en base de datos de series temporales (TSDB), visualización en Grafana OSS y gestión de alertas por umbral.

---

## 🏗️ Arquitectura del Sistema

```
+-----------------------------------------------------------------------------------------+
|                                    MÁQUINA VIRTUAL                                      |
|                                                                                         |
|   +-----------------------+           +-----------------------+                         |
|   |   Publicador IoT      |           |     Broker MQTT       |                         |
|   |    (publisher.py)     | --------> |  (Eclipse Mosquitto)  |                         |
|   |  Temp, Hum, Lux       |   MQTT    |      Puerto: 1883     |                         |
|   +-----------------------+           +-----------------------+                         |
|                                                   |                                     |
|                                                   | MQTT Sub (sensors/+/telemetry)      |
|                                                   v                                     |
|                                       +-----------------------+                         |
|                                       |   Ingesta / Bridge    |                         |
|                                       |    (subscriber.py)    |                         |
|                                       +-----------------------+                         |
|                                                   |                                     |
|                                                   | Influx Line Protocol / API Write    |
|                                                   v                                     |
|   +-----------------------+           +-----------------------+                         |
|   |      Grafana OSS      |   Flux    |         TSDB          |                         |
|   |      Puerto: 3000     | --------> |     (InfluxDB v2)     |                         |
|   | Dashboard 4 Días      |           |      Puerto: 8086     |                         |
|   +-----------------------+           +-----------------------+                         |
|               |                                                                         |
|               | Webhook Alert (>35.0 °C)                                                |
|               v                                                                         |
|   +-----------------------+                                                             |
|   |   Webhook Receiver    |                                                             |
|   |     (receiver.py)     |                                                             |
|   |      Puerto: 5000     |                                                             |
|   +-----------------------+                                                             |
+-----------------------------------------------------------------------------------------+
```

---

## 📦 Componentes del Stack

| Componente | Servicio / Imagen | Rol en la Plataforma | Puerto Expuesto |
|---|---|---|---|
| **Protocolo de Ingesta** | `mosquitto` (`eclipse-mosquitto:latest`) | Broker de mensajería MQTT ligero para transporte de variables. | `1883`, `9001` |
| **TSDB** | `influxdb` (`influxdb:2.7-alpine`) | Persistencia y consulta histórica de alta eficiencia (4 días). | `8086` |
| **Suscriptor/Bridge** | `subscriber` (Python 3.12) | Ingesta desacoplada: consume MQTT y persiste en InfluxDB con timestamp real. | Interno |
| **Publicador** | `publisher` (Python 3.12) | Simula nodo sensor: emite `temperature`, `humidity`, `illuminance` cada 10 s y precarga ventana de 4 días. | Interno |
| **Visualización** | `grafana` (`grafana/grafana:latest`) | Grafana OSS aprovisionado automáticamente con Datasource, Dashboard y Reglas de Alerta. | `80` (HTTP), `3000` |
| **Receptor de Alertas** | `webhook-receiver` (Python Flask) | Registra disparos de alertas de Grafana en formato JSON estructurado y log plano. | `5000` |
| **Renderizador** | `renderer` (`grafana-image-renderer:latest`) | Generación automatizada de capturas PNG de paneles y dashboards. | Interno |

---

## 🚀 Despliegue Rápido en la VM

### Prerrequisitos
- Docker Engine `>= 24.0`
- Docker Compose `>= 2.20`

### 1. Clonar el repositorio y navegar a la carpeta
```bash
git clone <URL_DEL_REPOSITORIO>
cd iot-telemetry-platform
```

### 2. Configurar variables de entorno (Opcional)
Se incluye un archivo de plantilla `.env.example`. Los valores por defecto en `docker-compose.yml` permiten levantar el entorno inmediatamente sin necesidad de configuración adicional.

```bash
cp .env.example .env
```

### 3. Levantar la plataforma completa
```bash
docker compose up -d
```

Todos los servicios levantarán en orden con healthchecks validados:
- Mosquitto se inicia y valida puerto `1883`.
- InfluxDB inicializa la organización `iot-lab` y el bucket `telemetry`.
- Subscriber se conecta al broker y a InfluxDB.
- Publisher genera la toma de 4 días y arranca la publicación en tiempo real cada 10 segundos.
- Grafana provisiona automáticamente el datasource Flux, el dashboard y la regla de alerta.

### 4. Acceso a las Interfaces Web
- **Grafana OSS:** `http://<TU_DOMINIO_O_IP>/` (o `http://<IP_DE_LA_VM>:3000`)  
  - Usuario: `admin`  
  - Contraseña: `admin`  
  - Dashboard: *IoT Platform / IoT Environmental Telemetry — Monitoreo de 4 Días*
- **InfluxDB UI:** `http://<IP_DE_LA_VM>:8086`  
  - Usuario: `iotuser`  
  - Contraseña: `iotpassword123`

---

## 🧪 Pruebas y Evidencias

### 1. Consultar puntos guardados en la TSDB
Ejecutar el script automatizado de consulta:
```bash
./scripts/query_tsdb.sh
```
O consultar interactivamente vía CLI:
```bash
docker exec iot_influxdb influx query \
  --org iot-lab \
  --token iot-lab-super-secret-auth-token-2024 \
  'from(bucket: "telemetry") |> range(start: -5d) |> count()'
```
Evidencia generada en: `evidencias/01_consulta_tsdb.txt`.

### 2. Forzar disparo de la alerta por umbral (> 35.0 °C)
Ejecutar el inyector de picos anómalos:
```bash
./scripts/trigger_alert.sh
```
El script envía lecturas de temperatura cercanas a 50 °C por MQTT. Grafana detectará la transgresión del umbral, transicionará a estado **FIRING** y emitirá el webhook de alerta.

Verificar el log del receptor de alertas:
```bash
docker logs iot_webhook_receiver
```
Evidencias generadas en:
- `evidencias/03_alerta_disparada.txt`
- `evidencias/03_alerta_webhook_payload.json`
- `evidencias/03_grafana_alerta_spike_zoom.png`

### 3. Captura del Dashboard de 4 Días
El renderizador genera capturas de alta definición directamente desde Grafana:
- `evidencias/02_grafana_dashboard_4dias.png`: Vista completa de 4 días con las 3 variables y gauges de estado.

---

## 📂 Estructura del Repositorio
```
iot-telemetry-platform/
├── docker-compose.yml               # Orquestación completa de 7 servicios
├── .env.example                     # Plantilla de variables de entorno
├── README.md                        # Guía de despliegue y uso
├── INFORME.md                       # Informe de entrega del laboratorio (1-2 páginas)
├── mosquitto/                       # Configuración de Eclipse Mosquitto
│   └── config/mosquitto.conf
├── publisher/                       # Nodo sensor publicador MQTT
│   ├── Dockerfile
│   ├── requirements.txt
│   └── publisher.py
├── subscriber/                      # Bridge de ingesta MQTT -> InfluxDB
│   ├── Dockerfile
│   ├── requirements.txt
│   └── subscriber.py
├── webhook_receiver/                # Servicio receptor de alertas de Grafana
│   ├── Dockerfile
│   ├── requirements.txt
│   └── receiver.py
├── grafana/provisioning/            # Aprovisionamiento automatizado de Grafana
│   ├── datasources/datasource.yml
│   ├── dashboards/dashboard_provider.yml
│   ├── dashboards/definitions/telemetry_dashboard.json
│   └── alerting/
│       ├── contact_points.yml
│       ├── notification_policies.yml
│       └── alert_rules.yml
├── scripts/                         # Scripts de prueba y automatización
│   ├── query_tsdb.sh
│   └── trigger_alert.sh
└── evidencias/                      # Archivos de evidencia exigidos
    ├── 01_consulta_tsdb.txt
    ├── 02_grafana_dashboard_4dias.png
    ├── 03_alerta_disparada.txt
    ├── 03_alerta_webhook_payload.json
    └── 03_grafana_alerta_spike_zoom.png
```

