#!/usr/bin/env bash
set -euo pipefail

OUTPUT_FILE="/home/zerolf/iot-telemetry-platform/evidencias/01_consulta_tsdb.txt"
INFLUX_TOKEN="iot-lab-super-secret-auth-token-2024"
INFLUX_ORG="iot-lab"
INFLUX_BUCKET="telemetry"

echo "================================================================================" > "$OUTPUT_FILE"
echo "  EVIDENCIA DE CONSULTA DE PUNTOS GUARDADOS EN LA TSDB (InfluxDB v2.7)" >> "$OUTPUT_FILE"
echo "  Plataforma IoT Telemetría — Fecha de ejecución: $(date -u '+%Y-%m-%d %H:%M:%S UTC')" >> "$OUTPUT_FILE"
echo "================================================================================" >> "$OUTPUT_FILE"
echo "" >> "$OUTPUT_FILE"

echo "1. VERIFICACIÓN DE ORGANIZACIÓN Y BUCKETS EN LA TSDB:" >> "$OUTPUT_FILE"
echo "Comando: influx bucket list --org $INFLUX_ORG" >> "$OUTPUT_FILE"
echo "--------------------------------------------------------------------------------" >> "$OUTPUT_FILE"
docker exec iot_influxdb influx bucket list --org "$INFLUX_ORG" --token "$INFLUX_TOKEN" >> "$OUTPUT_FILE" 2>&1
echo "" >> "$OUTPUT_FILE"

echo "2. TOTAL DE PUNTOS REGISTRADOS EN LA VENTANA DE 4 DÍAS POR VARIABLE:" >> "$OUTPUT_FILE"
echo "Comando: from(bucket: \"$INFLUX_BUCKET\") |> range(start: -5d) |> count()" >> "$OUTPUT_FILE"
echo "--------------------------------------------------------------------------------" >> "$OUTPUT_FILE"
docker exec iot_influxdb influx query --org "$INFLUX_ORG" --token "$INFLUX_TOKEN" \
  'from(bucket: "telemetry") |> range(start: -5d) |> filter(fn: (r) => r._measurement == "environment") |> count()' >> "$OUTPUT_FILE" 2>&1
echo "" >> "$OUTPUT_FILE"

echo "3. RANGO TEMPORAL DE LA MUESTRA DE 4 DÍAS (PUNTO MÁS ANTIGUO Y MÁS RECIENTE):" >> "$OUTPUT_FILE"
echo "--------------------------------------------------------------------------------" >> "$OUTPUT_FILE"
echo "PUNTO MÁS ANTIGUO (INICIO DE LA TOMA):" >> "$OUTPUT_FILE"
docker exec iot_influxdb influx query --org "$INFLUX_ORG" --token "$INFLUX_TOKEN" \
  'from(bucket: "telemetry") |> range(start: -5d) |> filter(fn: (r) => r._measurement == "environment" and r._field == "temperature") |> first()' >> "$OUTPUT_FILE" 2>&1
echo "" >> "$OUTPUT_FILE"
echo "PUNTO MÁS RECIENTE (TIEMPO REAL ACTUAL):" >> "$OUTPUT_FILE"
docker exec iot_influxdb influx query --org "$INFLUX_ORG" --token "$INFLUX_TOKEN" \
  'from(bucket: "telemetry") |> range(start: -15m) |> filter(fn: (r) => r._measurement == "environment" and r._field == "temperature") |> last()' >> "$OUTPUT_FILE" 2>&1
echo "" >> "$OUTPUT_FILE"

echo "4. MUESTRA DE DATOS RECIENTES INGRESADOS VÍA MQTT (ÚLTIMAS 5 MEDICIONES):" >> "$OUTPUT_FILE"
echo "--------------------------------------------------------------------------------" >> "$OUTPUT_FILE"
docker exec iot_influxdb influx query --org "$INFLUX_ORG" --token "$INFLUX_TOKEN" \
  'from(bucket: "telemetry") |> range(start: -10m) |> filter(fn: (r) => r._measurement == "environment") |> tail(n: 5)' >> "$OUTPUT_FILE" 2>&1
echo "" >> "$OUTPUT_FILE"

echo "5. ESTADÍSTICAS GLOBALES DE LA VENTANA DE 4 DÍAS (MEDIA, MÍNIMO, MÁXIMO):" >> "$OUTPUT_FILE"
echo "--------------------------------------------------------------------------------" >> "$OUTPUT_FILE"
echo "--- PROMEDIO (MEAN) ---" >> "$OUTPUT_FILE"
docker exec iot_influxdb influx query --org "$INFLUX_ORG" --token "$INFLUX_TOKEN" \
  'from(bucket: "telemetry") |> range(start: -5d) |> filter(fn: (r) => r._measurement == "environment") |> mean()' >> "$OUTPUT_FILE" 2>&1
echo "" >> "$OUTPUT_FILE"
echo "--- MÁXIMOS (MAX) ---" >> "$OUTPUT_FILE"
docker exec iot_influxdb influx query --org "$INFLUX_ORG" --token "$INFLUX_TOKEN" \
  'from(bucket: "telemetry") |> range(start: -5d) |> filter(fn: (r) => r._measurement == "environment") |> max()' >> "$OUTPUT_FILE" 2>&1
echo "" >> "$OUTPUT_FILE"
echo "--- MÍNIMOS (MIN) ---" >> "$OUTPUT_FILE"
docker exec iot_influxdb influx query --org "$INFLUX_ORG" --token "$INFLUX_TOKEN" \
  'from(bucket: "telemetry") |> range(start: -5d) |> filter(fn: (r) => r._measurement == "environment") |> min()' >> "$OUTPUT_FILE" 2>&1

echo "Consulta completada con éxito. Archivo guardado en: $OUTPUT_FILE"
