import json
import ssl
import threading
from flask import Flask, request, abort, Response
from datetime import datetime, timedelta
import websocket
import xml.etree.ElementTree as ET

app = Flask(__name__)

API_TOKEN = "SLPRIVATE"  # Replace with your secure token
active_client = {"ip": None, "last_seen": None}
lock = threading.Lock()
latest_data = []

def is_browser_request():
    ua = request.headers.get("User-Agent", "").lower()
    return any(b in ua for b in ["mozilla", "chrome", "safari", "edge", "firefox"])

@app.route("/rates", methods=["GET"])
def serve_rates_xml():
    token = request.headers.get("Authorization")
    if token != f"Bearer {API_TOKEN}":
        return abort(403, description="Forbidden")

    if is_browser_request():
        return abort(403, description="Browser access not allowed")

    client_ip = request.remote_addr
    now = datetime.utcnow()

    with lock:
        if active_client["ip"] and active_client["ip"] != client_ip:
            if active_client["last_seen"] and now - active_client["last_seen"] < timedelta(seconds=30):
                return abort(409, description="Another Excel session is active")
        active_client["ip"] = client_ip
        active_client["last_seen"] = now

    with lock:
        root = ET.Element("Rates")
        for row in latest_data:
            item = ET.SubElement(root, "Rate")
            for key, value in row.items():
                sub = ET.SubElement(item, key)
                sub.text = str(value)

        xml_bytes = ET.tostring(root, encoding="utf-8", xml_declaration=True)
        return Response(xml_bytes, mimetype='application/xml')

# === WebSocket Client ===
def on_message(ws, message):
    try:
        data = json.loads(message)
        if data.get("type") == "message" and "datajson" in data:
            items = json.loads(data["datajson"])
            if isinstance(items, list):
                processed = []
                for item in items:
                    try:
                        processed.append({
                            "Symbol": item["Symbol"],
                            "Bid": float(item["Bid"]),
                            "Ask": float(item["Ask"]),
                            "High": float(item["High"]),
                            "Low": float(item["Low"]),
                            "DateTime": item.get("DateTime", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                        })
                    except Exception:
                        continue
                with lock:
                    global latest_data
                    latest_data = processed
    except Exception as e:
        print("Error processing message:", e)

def on_error(ws, error):
    print("WebSocket error:", error)

def on_close(ws, close_status_code, close_msg):
    print("WebSocket closed")

def on_open(ws):
    print("WebSocket opened")

def start_websocket():
    websocket.enableTrace(False)
    ws_url = "wss://hindplat.in:3003"  # Replace with your WebSocket URL
    ws_app = websocket.WebSocketApp(
        ws_url,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
    )
    ws_app.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE})

if __name__ == "__main__":
    threading.Thread(target=start_websocket, daemon=True).start()
    app.run(host="0.0.0.0", port=5000)
