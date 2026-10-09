import os
import sys
import time
import json
import math
import random
import argparse
import logging
from datetime import datetime, timezone, timedelta
import paho.mqtt.client as mqtt

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [MQTT-PUBLISHER] %(message)s"
)
logger = logging.getLogger("publisher")

MQTT_BROKER = os.getenv("MQTT_BROKER", "mosquitto")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "sensors/datacenter/telemetry")
DEVICE_ID = os.getenv("DEVICE_ID", "sensor_node_alpha")
LOCATION = os.getenv("LOCATION", "rack_server_room_01")
INTERVAL_SECONDS = float(os.getenv("INTERVAL_SECONDS", "10"))

def generate_telemetry_point(dt_utc: datetime, force_spike: bool = False):
    """
    Simulates realistic environmental data with diurnal cycles:
    - Temperature: 19°C (night/dawn) to 28°C (afternoon), plus noise.
    - Humidity: 40% (afternoon) to 68% (dawn), inverse to temperature.
    - Illuminance: 0 lx at night, rising to 600-850 lx in middle of day.
    """
    if force_spike:
        temp = round(random.uniform(45.0, 52.0), 2)  # High temperature spike > 35°C threshold
        hum = round(random.uniform(18.0, 25.0), 2)
        lux = round(random.uniform(900.0, 1100.0), 2)
        return temp, hum, lux

    hour_fraction = dt_utc.hour + dt_utc.minute / 60.0 + dt_utc.second / 3600.0

    # Solar diurnal cycle: peak around 14:00 (hour 14), lowest around 05:00 (hour 5)
    # Cosine shifted so max is at hour 14
    phase = (hour_fraction - 14.0) * (2 * math.pi / 24.0)
    cycle = math.cos(phase)  # ranges from -1 to 1

    # Base temperature: 23.5°C mean, amplitude 4.0°C (range 19.5 - 27.5°C)
    base_temp = 23.5 + 4.0 * cycle
    temp_noise = random.gauss(0, 0.35)
    temp = round(max(15.0, min(34.0, base_temp + temp_noise)), 2)

    # Base humidity: inversely proportional to temperature
    base_hum = 54.0 - 12.0 * cycle
    hum_noise = random.gauss(0, 1.2)
    hum = round(max(30.0, min(80.0, base_hum + hum_noise)), 2)

    # Illuminance: daylight between 06:00 and 19:00
    if 6.0 <= hour_fraction <= 19.0:
        sun_phase = (hour_fraction - 6.0) / 13.0 * math.pi
        sun_intensity = math.sin(sun_phase)
        base_lux = 750.0 * (sun_intensity ** 1.3)
        lux_noise = random.gauss(0, 25.0)
        lux = round(max(10.0, base_lux + lux_noise), 1)
    else:
        # Artificial night standby light / dark
        lux = round(random.uniform(0.0, 5.0), 1)

    return temp, hum, lux

def build_payload(dt_utc: datetime, temp: float, hum: float, lux: float, alert_flag: bool = False):
    return {
        "timestamp": dt_utc.timestamp(),
        "datetime": dt_utc.isoformat(),
        "device_id": DEVICE_ID,
        "location": LOCATION,
        "temperature": temp,
        "humidity": hum,
        "illuminance": lux,
        "forced_alert": alert_flag
    }

def connect_mqtt():
    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"pub_{DEVICE_ID}_{int(time.time())}")
    except AttributeError:
        client = mqtt.Client(client_id=f"pub_{DEVICE_ID}_{int(time.time())}")

    logger.info(f"Connecting to MQTT Broker at {MQTT_BROKER}:{MQTT_PORT}...")
    max_retries = 30
    for attempt in range(1, max_retries + 1):
        try:
            client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
            client.loop_start()
            logger.info("Connected to MQTT Broker!")
            return client
        except Exception as e:
            logger.warning(f"Connection attempt {attempt}/{max_retries} failed ({e}). Retrying in 2s...")
            time.sleep(2)
    logger.error("Could not connect to MQTT Broker.")
    sys.exit(1)

def seed_4_days(client, days=4, step_minutes=3):
    """
    Backfills 4 days of history up to the current moment.
    4 days * 24 hours * (60 / 3) = 1920 points.
    Published via MQTT so all points are ingested through the exact broker -> TSDB pipeline.
    """
    now = datetime.now(timezone.utc)
    start_time = now - timedelta(days=days)
    delta_step = timedelta(minutes=step_minutes)

    total_points = int((now - start_time) / delta_step)
    logger.info(f"--- STARTING 4-DAY HISTORICAL SEEDING ---")
    logger.info(f"From: {start_time.isoformat()} To: {now.isoformat()}")
    logger.info(f"Total points to publish: {total_points} (every {step_minutes} min)")

    current = start_time
    count = 0
    while current <= now:
        temp, hum, lux = generate_telemetry_point(current)
        payload = build_payload(current, temp, hum, lux)
        client.publish(MQTT_TOPIC, json.dumps(payload), qos=1)
        count += 1
        
        if count % 200 == 0 or count == total_points:
            logger.info(f"Seeded {count}/{total_points} points ({count/total_points*100:.1f}%) [Latest: {current.isoformat()} - T:{temp}°C, H:{hum}%, L:{lux}lx]")
        
        current += delta_step
        # Small sleep so Mosquitto and subscriber keep up without message drops
        time.sleep(0.005)

    logger.info(f"--- 4-DAY HISTORICAL SEEDING COMPLETE ({count} points) ---")
    time.sleep(1)

def run_live_loop(client, interval=INTERVAL_SECONDS):
    logger.info(f"Starting continuous live telemetry publisher (Interval: {interval}s, Topic: {MQTT_TOPIC})...")
    iteration = 0
    try:
        while True:
            now = datetime.now(timezone.utc)
            temp, hum, lux = generate_telemetry_point(now)
            payload = build_payload(now, temp, hum, lux)
            
            client.publish(MQTT_TOPIC, json.dumps(payload), qos=1)
            iteration += 1
            logger.info(
                f"[LIVE PUB #{iteration}] Sent telemetry: Temp={temp:.2f}°C, Hum={hum:.2f}%, Lux={lux:.1f}lx "
                f"at {now.strftime('%Y-%m-%d %H:%M:%S UTC')}"
            )
            time.sleep(interval)
    except KeyboardInterrupt:
        logger.info("Publisher stopped by user.")

def trigger_spike(client, count=6, interval=3):
    """
    Forces elevated values (temp > 35°C) to trigger the Grafana alert.
    """
    logger.info(f"!!! TRIGGERING ALERT SPIKE ({count} points, Temp > 45°C) !!!")
    for i in range(1, count + 1):
        now = datetime.now(timezone.utc)
        temp, hum, lux = generate_telemetry_point(now, force_spike=True)
        payload = build_payload(now, temp, hum, lux, alert_flag=True)
        client.publish(MQTT_TOPIC, json.dumps(payload), qos=1)
        logger.warning(
            f"[SPIKE INJECTION #{i}/{count}] Temp={temp:.2f}°C (>35°C threshold!), "
            f"Hum={hum:.2f}%, Lux={lux:.1f}lx at {now.isoformat()}"
        )
        time.sleep(interval)
    logger.info("Spike injection complete. Reverting to normal readings.")

def main():
    parser = argparse.ArgumentParser(description="IoT Telemetry MQTT Publisher")
    parser.add_argument("--auto-seed", action="store_true", help="Seed 4 days if empty then run live loop")
    parser.add_argument("--seed-only", action="store_true", help="Only seed 4 days of history and exit")
    parser.add_argument("--live-only", action="store_true", help="Run live loop without seeding")
    parser.add_argument("--spike", action="store_true", help="Inject threshold-violating spike to test alert")
    parser.add_argument("--spike-count", type=int, default=8, help="Number of spike messages to send")
    parser.add_argument("--spike-interval", type=float, default=2.0, help="Interval between spikes in seconds")
    parser.add_argument("--interval", type=float, default=INTERVAL_SECONDS, help="Live publish interval in seconds")

    args = parser.parse_args()

    client = connect_mqtt()

    if args.spike:
        trigger_spike(client, count=args.spike_count, interval=args.spike_interval)
        client.loop_stop()
        client.disconnect()
        return

    if args.seed_only:
        seed_4_days(client)
        client.loop_stop()
        client.disconnect()
        return

    if args.auto_seed:
        # Give Mosquitto and subscriber 3 seconds to stabilize
        time.sleep(3)
        seed_4_days(client)
        run_live_loop(client, interval=args.interval)
        return

    # Default to live loop
    run_live_loop(client, interval=args.interval)

if __name__ == "__main__":
    main()
