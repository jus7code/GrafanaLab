#!/usr/bin/env bash
set -euo pipefail

echo "================================================================================"
echo "  DISPARADOR DE ALERTA POR UMBRAL DE TEMPERATURA (> 35.0 °C)"
echo "================================================================================"
echo "Inyectando pico térmico artificial desde el publicador MQTT..."
docker exec iot_publisher python publisher.py --spike --spike-count 10 --spike-interval 2
echo "Pico inyectado. La alerta en Grafana cambiará a FIRING en ~10-15 segundos."
echo "Monitorear con: docker logs -f iot_webhook_receiver"
