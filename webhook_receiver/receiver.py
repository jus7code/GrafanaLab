import os
import json
import logging
from datetime import datetime, timezone
from flask import Flask, request, jsonify

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [WEBHOOK-ALERT] %(message)s"
)
logger = logging.getLogger("webhook")

app = Flask(__name__)

EVIDENCIAS_DIR = os.getenv("EVIDENCIAS_DIR", "/evidencias")
os.makedirs(EVIDENCIAS_DIR, exist_ok=True)

@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "healthy", "service": "grafana-alert-webhook-receiver"}), 200

@app.route("/webhook", methods=["POST"])
@app.route("/alerts", methods=["POST"])
def receive_alert():
    try:
        data = request.get_json(force=True, silent=True) or {}
        now_str = datetime.now(timezone.utc).isoformat()
        
        status = data.get("status", "unknown")
        alerts = data.get("alerts", [])
        title = data.get("title", "No Title")
        
        logger.warning("==================================================")
        logger.warning(f"!!! ALERTA RECIBIDA DESDE GRAFANA [Estado: {status.upper()}] !!!")
        logger.warning(f"Título: {title}")
        logger.warning(f"Total Alertas en el payload: {len(alerts)}")
        
        for idx, alert in enumerate(alerts, 1):
            alert_status = alert.get("status", "unknown")
            labels = alert.get("labels", {})
            annotations = alert.get("annotations", {})
            values = alert.get("values", {})
            logger.warning(
                f"  -> Alerta #{idx}: Estado={alert_status.upper()} | "
                f"Labels={labels} | Anotaciones={annotations} | Valores={values}"
            )
        logger.warning("==================================================")

        # Save to evidencias file
        output_file = os.path.join(EVIDENCIAS_DIR, "03_alerta_webhook_payload.json")
        with open(output_file, "w") as f:
            json.dump({
                "received_at": now_str,
                "status": status,
                "payload": data
            }, f, indent=2)

        # Also write readable log summary
        log_file = os.path.join(EVIDENCIAS_DIR, "03_alerta_disparada.txt")
        with open(log_file, "a") as f:
            f.write(f"\n[{now_str}] ALERTA DISPARADA POR GRAFANA\n")
            f.write(f"Estado: {status}\n")
            f.write(f"Título: {title}\n")
            for a in alerts:
                f.write(f"  Regla: {a.get('labels', {}).get('alertname', 'N/A')}\n")
                f.write(f"  Estado: {a.get('status')}\n")
                f.write(f"  Valores: {a.get('values')}\n")
                f.write(f"  Descripción: {a.get('annotations', {}).get('description', 'N/A')}\n")
            f.write("---------------------------------------------------\n")

        return jsonify({"message": "Alert received and logged successfully", "status": "ok"}), 200

    except Exception as e:
        logger.error(f"Error handling alert webhook: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    logger.info(f"Starting alert webhook listener on 0.0.0.0:{port}...")
    app.run(host="0.0.0.0", port=port)
