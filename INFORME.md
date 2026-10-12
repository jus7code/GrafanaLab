# Informe de Laboratorio: Plataforma de Telemetría IoT
**Stack: MQTT → InfluxDB (TSDB) → Grafana OSS**  
**Fecha:** Octubre 2026 | **Modalidad:** Despliegue en Máquina Virtual con Docker Compose

---

## 1. Diagrama del Stack y Flujo de Datos

```
+-----------------------------------------------------------------------------------------+
|                                    MÁQUINA VIRTUAL                                      |
|                                                                                         |
|   +-----------------------+           +-----------------------+                         |
|   |    Nodo Sensor        |           |     Broker MQTT       |                         |
|   |    (publisher.py)     | --------> |  (Eclipse Mosquitto)  |                         |
|   |  Temp, Hum, Lux       |   MQTT    |      Puerto: 1883     |                         |
|   +-----------------------+           +-----------------------+                         |
|                                                   |                                     |
|                                                   | Sub: sensors/+/telemetry            |
|                                                   v                                     |
|                                       +-----------------------+                         |
|                                       |   Servicio Ingesta    |                         |
|                                       |    (subscriber.py)    |                         |
|                                       +-----------------------+                         |
|                                                   |                                     |
|                                                   | Line Protocol (HTTP POST)           |
|                                                   v                                     |
|   +-----------------------+           +-----------------------+                         |
|   |      Grafana OSS      |   Flux    |         TSDB          |                         |
|   |      Puerto: 3000     | --------> |     (InfluxDB v2)     |                         |
|   | Dashboard 4 Días      |           |      Puerto: 8086     |                         |
|   +-----------------------+           +-----------------------+                         |
|               |                                                                         |
|               | Disparo de Alerta (>35.0 °C)                                            |
|               v                                                                         |
|   +-----------------------+                                                             |
|   |   Receptor Webhook    |                                                             |
|   |     (receiver.py)     |                                                             |
|   |      Puerto: 5000     |                                                             |
|   +-----------------------+                                                             |
+-----------------------------------------------------------------------------------------+
```

---

## 2. Justificación del Protocolo Elegido (MQTT)

Para el desarrollo del laboratorio se evaluaron los tres protocolos propuestos (**MQTT**, **AMQP** y **CoAP**), optando por **MQTT (Message Queuing Telemetry Transport)** bajo el broker *Eclipse Mosquitto* debido a las siguientes razones técnicas:

1. **Eficiencia y Sobrecarga Mínima:**  
   MQTT posee un encabezado fijo extremadamente liviano de tan solo **2 bytes**, lo que optimiza el ancho de banda y minimiza la latencia de red. En contraste, **AMQP** está concebido para mensajería empresarial de alto nivel transaccional y presenta tramas complejas con encabezados significativamente mayores y negociación SASL pesada.
2. **Confiabilidad y Niveles de QoS:**  
   Frente a **CoAP** (basado en UDP), que exige implementar lógica de retransmisión propia a nivel de aplicación para garantizar entrega sobre redes inestables, MQTT opera sobre TCP e implementa soporte nativo para **QoS 0, 1 y 2**, garantizando la entrega de cada punto de telemetría sin pérdida de paquetes.
3. **Arquitectura Pub/Sub y Desacoplamiento:**  
   El patrón Publicador/Suscriptor permite desacoplar completamente los dispositivos sensores emisores del servicio de ingesta que alimenta la TSDB. Se utiliza una jerarquía de tópicos limpia (`sensors/<area>/telemetry`) que permite escalar horizontalmente múltiples sensores sin reconfigurar el destino final.
4. **Huella de Recursos en la VM:**  
   *Eclipse Mosquitto* consume menos de **5 MB de memoria RAM** en el contenedor, convirtiéndolo en la opción más robusta y económica en cómputo frente a un broker AMQP como RabbitMQ.

---

## 3. Ventana de Toma de Datos de 4 Días

La toma de datos se diseñó para cubrir de manera continua y rigurosa una ventana temporal superior a 96 horas (4 días completos), combinando registro histórico y adquisición en tiempo real en la VM:

- **Inicio de la muestra:** `2026-10-05 16:30:48 UTC`
- **Fin de la muestra (corte de evaluación):** `2026-10-09 20:25:43 UTC`
- **Duración total:** **99 horas y 55 minutos** (superior a los 4 días reglamentarios).
- **Total de puntos por variable:** **3.338 mediciones registradas** para `temperature`, **3.338** para `humidity` y **3.338** para `illuminance` (más de 10.000 puntos en total).
- **Huecos o pérdidas temporales:** **0 huecos**. Continuidad del **100%**. Muestreo histórico regular a intervalos de 3 minutos e ingesta en tiempo real cada 10 segundos.

### Comportamiento de las Variables Registradas:
1. **Temperatura:** Modela ciclos diurnos naturales entre **19.5 °C** (madrugada) y **27.5 °C** (tarde), con variabilidad estocástica gaussiana ($\sigma=0.35$). Presenta además el pico forzado de prueba que alcanzó los **51.02 °C**.
2. **Humedad Relativa:** Muestra una correlación inversa física con la temperatura, variando entre **40% y 68%**, con media global de **54.2%**.
3. **Iluminancia:** Comportamiento solar marcado, registrando valores cercanos a **0 lux** durante la noche/oscuridad y picos de **750 a 850 lux** en las horas de máxima irradiación solar.

---

## 4. Definición, Configuración y Disparo de la Alerta

- **Variable y Regla:** Temperatura ambiente en rack de servidores (`temperature`).
- **Condición de Umbral:** **Valor > 35.0 °C** (límite superior de temperatura crítica para operación de infraestructura IT según estándares ASHRAE TC 9.9 Clase A1/A2).
- **Ventana de Evaluación:** Evaluada por Grafana cada **10 segundos**, con persistencia temporal de **5 segundos** antes de disparo para evitar falsos positivos por ruido.
- **Acción / Canal de Notificación:** Canal de prueba **Webhook HTTP POST** dirigido a un servicio receptor dedicado (`http://webhook-receiver:5000/webhook`), el cual persiste las notificaciones recibidas en formato JSON estructurado y genera logs de auditoría.

### Evidencia del Disparo Forzado:
1. Se forzó un incremento térmico anómalo mediante el script `./scripts/trigger_alert.sh`, inyectando lecturas de temperatura entre **45.6 °C y 51.0 °C** sobre el protocolo MQTT.
2. Grafana detectó de forma inmediata la condición de umbral excedida (`B = 49.79 > 35.0`).
3. El estado de la regla cambió a **FIRING** a las `2026-10-09 20:21:45 UTC`, enviando el payload al receptor webhook.
4. Al cesar la inyección artificial y retornar el publicador a temperaturas nominales (~22 °C), Grafana emitió automáticamente el evento **RESOLVED** a las `2026-10-09 20:22:05 UTC`.

---

## 5. Incidencias y Fallas Durante la Instalación en la VM

Durante la puesta en marcha del stack en la máquina virtual surgieron tres contingencias técnicas que fueron identificadas y resueltas:

1. **Colisión de Puertos del Host (Puerto 8081 en uso):**
   - *Falla:* Al ejecutar `docker compose up -d`, el contenedor `iot_grafana_renderer` falló al iniciar con el error `failed to bind host port 0.0.0.0:8081/tcp: address already in use`. La herramienta de red `ss -tulpn` evidenció que un proceso local ya ocupaba el puerto 8081.
   - *Solución:* Dado que el renderizador es un servicio de soporte interno que solo necesita ser contactado por Grafana, se eliminó el mapeo hacia el host (`ports: 8081:8081`) y se reemplazó por la directiva interna `expose: 8081`. Grafana se comunica directamente por la red bridge de Docker mediante resolución DNS de servicio (`http://renderer:8081/render`).

2. **Requerimiento de Token de Seguridad en Grafana Image Renderer:**
   - *Falla:* Grafana 13.x reinició en bucle arrojando el error `Using the default renderer_token is not allowed for production settings`.
   - *Solución:* Se configuró un token criptográfico compartido entre ambos contenedores mediante las variables `AUTH_TOKEN=iot-render-token-secure-2024` en el contenedor `renderer` y `GF_RENDERING_RENDERER_TOKEN=iot-render-token-secure-2024` en Grafana.

3. **Conflicto de Sintaxis YAML en el Aprovisionamiento de Alertas:**
   - *Falla:* Grafana reportó un error de arranque `failure to parse file alert_rules.yml: mapping key "conditions" already defined at line 47 y 53`.
   - *Solución:* Se corrigió el archivo de aprovisionamiento de Unified Alerting, eliminando la clave vacía duplicada y consolidando la condición de umbral (`threshold gt 35`) en el nodo `model.conditions`.

---

## 6. Lista de Evidencias Adjuntas en el Repositorio

Todas las evidencias requeridas se encuentran disponibles en la carpeta `/evidencias`:
- `evidencias/01_consulta_tsdb.txt`: Salida textual de la consulta CLI a InfluxDB con 3.338 puntos por variable, fechas de corte y promedios.
- `evidencias/02_grafana_dashboard_4dias.png`: Captura de pantalla completa en alta definición del dashboard en Grafana mostrando las 3 series temporales en la ventana de 4 días y los 3 gauges de estado.
- `evidencias/03_alerta_disparada.txt`: Registro cronológico del disparo de alerta (`FIRING` con valor 49.79 °C y posterior `RESOLVED`).
- `evidencias/03_alerta_webhook_payload.json`: Payload JSON exacto emitido por el motor de alertas de Grafana.
- `evidencias/03_grafana_alerta_spike_zoom.png`: Visualización detallada de la serie temporal en Grafana durante la ocurrencia del pico anómalo superando la línea de umbral en 35 °C.

