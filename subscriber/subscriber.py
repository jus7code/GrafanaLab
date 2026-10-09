import os
import sys
import time
import json
import logging
from datetime import datetime, timezone
import paho.mqtt.client as mqtt
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [MQTT-SUBSCRIBER] %(message)s"
)
logger = logging.getLogger("subscriber")

MQTT_BROKER = os.getenv("MQTT_BROKER", "mosquitto")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "sensors/+/telemetry")

INFLUXDB_URL = os.getenv("INFLUXDB_URL", "http://influxdb:8086")
INFLUXDB_TOKEN = os.getenv("INFLUXDB_TOKEN", "iot-lab-super-secret-auth-token-2024")
INFLUXDB_ORG = os.getenv("INFLUXDB_ORG", "iot-lab")
INFLUXDB_BUCKET = os.getenv("INFLUXDB_BUCKET", "telemetry")

write_api = None
client_influx = None

def init_influxdb():
    global client_influx, write_api
    logger.info(f"Connecting to InfluxDB at {INFLUXDB_URL} (org: {INFLUXDB_ORG}, bucket: {INFLUXDB_BUCKET})...")
    max_retries = 30
    for attempt in range(1, max_retries + 1):
        try:
            client_influx = InfluxDBClient(
                url=INFLUXDB_URL,
                token=INFLUXDB_TOKEN,
                org=INFLUXDB_ORG,
                timeout=10000
            )
            # Verify health
            health = client_influx.health()
            if health.status == "pass":
                logger.info(f"InfluxDB is ready! (Attempt {attempt})")
                write_api = client_influx.write_api(write_options=SYNCHRONOUS)
                return True
            else:
                logger.warning(f"InfluxDB health status: {health.status}, waiting...")
        except Exception as e:
            logger.warning(f"InfluxDB connection attempt {attempt}/{max_retries} failed: {e}")
        time.sleep(2)
    logger.error("Failed to connect to InfluxDB after maximum retries.")
    sys.exit(1)

def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        logger.info(f"Connected successfully to MQTT Broker at {MQTT_BROKER}:{MQTT_PORT}")
        client.subscribe(MQTT_TOPIC)
        logger.info(f"Subscribed to topic pattern: '{MQTT_TOPIC}'")
    else:
        logger.error(f"Failed to connect to MQTT broker with return code {rc}")

def on_message(client, userdata, msg):
    try:
        payload_str = msg.payload.decode("utf-8")
        data = json.loads(payload_str)

        device_id = str(data.get("device_id", "unknown_device"))
        location = str(data.get("location", "default_location"))
        
        # Parse timestamp
        raw_ts = data.get("timestamp")
        if raw_ts is not None:
            if isinstance(raw_ts, (int, float)):
                ts_dt = datetime.fromtimestamp(raw_ts, tz=timezone.utc)
            else:
                try:
                    ts_dt = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
                except Exception:
                    ts_dt = datetime.now(timezone.utc)
        else:
            ts_dt = datetime.now(timezone.utc)

        temp = float(data["temperature"]) if "temperature" in data else None
        hum = float(data["humidity"]) if "humidity" in data else None
        lux = float(data["illuminance"]) if "illuminance" in data else None

        point = Point("environment") \
            .tag("device_id", device_id) \
            .tag("location", location) \
            .time(ts_dt, WritePrecision.S)

        fields_logged = []
        if temp is not None:
            point.field("temperature", temp)
            fields_logged.append(f"temp={temp:.2f}°C")
        if hum is not None:
            point.field("humidity", hum)
            fields_logged.append(f"hum={hum:.2f}%")
        if lux is not None:
            point.field("illuminance", lux)
            fields_logged.append(f"lux={lux:.2f}lx")

        if write_api is not None:
            write_api.write(bucket=INFLUXDB_BUCKET, org=INFLUXDB_ORG, record=point)
            logger.info(
                f"[INGESTION SUCCESS] Topic: {msg.topic} | Device: {device_id} | "
                f"Fields: [{', '.join(fields_logged)}] | Timestamp: {ts_dt.isoformat()}"
            )
        else:
            logger.error("write_api is not initialized; cannot write point.")

    except json.JSONDecodeError as jde:
        logger.error(f"Malformed JSON payload on {msg.topic}: {jde}")
    except Exception as e:
        logger.error(f"Error processing message on {msg.topic}: {e}", exc_info=True)

def main():
    init_influxdb()

    # Use MQTT v5 / v3.1.1 compatible client
    try:
        mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="iot_telemetry_subscriber")
    except AttributeError:
        mqtt_client = mqtt.Client(client_id="iot_telemetry_subscriber")

    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message

    logger.info(f"Connecting to MQTT Broker at {MQTT_BROKER}:{MQTT_PORT}...")
    while True:
        try:
            mqtt_client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
            break
        except Exception as e:
            logger.warning(f"MQTT broker not ready ({e}). Retrying in 2 seconds...")
            time.sleep(2)

    logger.info("Starting MQTT listener loop...")
    mqtt_client.loop_forever()

if __name__ == "__main__":
    main()
