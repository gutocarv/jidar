# -*- coding: utf-8 -*-
"""
japidar - dashboard_server.py
Le detections_com_azimute.csv (ja correlacionado e com offset aplicado pelo correlate.py)
e transmite via WebSocket para o dashboard.html.

Uso: python3 dashboard_server.py [config.json]
"""
import asyncio, csv, json, os, sys
from datetime import datetime, timedelta
from websockets.asyncio.server import serve
import websockets

def load_config(path="config.json"):
    with open(path) as f: return json.load(f)

def load_detections(path, since_dt):
    rows = []
    if not os.path.exists(path): return rows
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                dt = datetime.fromisoformat(row["datetime"])
                if dt < since_dt: continue
                rows.append({
                    "datetime":    row["datetime"],
                    "sci_name":    row["sci_name"],
                    "com_name":    row["com_name"],
                    "name_pt":     row.get("name_pt", row["com_name"]),
                    "confidence":  float(row["confidence"]),
                    "azimute":     float(row["azimute"]) if row["azimute"] else None,
                    "azimute_std": float(row["azimute_std"]) if row["azimute_std"] else None,
                    "quadrante":   row["quadrante"],
                    "qualidade":   row["qualidade"],
                    "file_name":   row.get("file_name",""),
                })
            except: continue
    return rows

def load_doa_last(path):
    if not os.path.exists(path): return None
    last = None
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                last = {"azimute": int(row["azimute"]),
                        "is_voice": int(row["is_voice"]),
                        "ts": row["timestamp_iso"]}
            except: continue
    return last

async def run(cfg_path="config.json"):
    cfg       = load_config(cfg_path)
    csv_path  = cfg["paths"].get("detections_csv", "./detections_com_azimute.csv")
    doa_path  = cfg["paths"]["doa_log"]
    ws_port   = cfg["server"]["ws_port"]
    hist_h    = cfg["correlation"]["history_hours"]
    has_doa   = cfg["respeaker"]["enabled"]
    poll      = 3.0

    connected = set()
    last_seen = [None]  # datetime da ultima deteccao enviada

    async def broadcast(msg):
        data = json.dumps(msg, default=str)
        dead = set()
        for ws in list(connected):
            try: await ws.send(data)
            except websockets.ConnectionClosed: dead.add(ws)
        connected.difference_update(dead)

    async def ws_handler(websocket):
        connected.add(websocket)
        print(f"[server] cliente conectado ({len(connected)})")
        try:
            since = datetime.now() - timedelta(hours=hist_h)
            dets  = load_detections(csv_path, since)
            events = [{"type":"detection", "historic": True, **d} for d in dets]
            await websocket.send(json.dumps({
                "type":    "snapshot",
                "events":  events,
                "station": cfg["station_name"],
                "has_doa": has_doa,
                "house":   cfg["house"],
            }, default=str))
            if dets:
                last_seen[0] = datetime.fromisoformat(dets[-1]["datetime"])
            await websocket.send(json.dumps({"type":"hello"}))
            async for _ in websocket: pass
        except websockets.ConnectionClosed: pass
        finally:
            connected.discard(websocket)
            print(f"[server] cliente desconectado ({len(connected)})")

    async def poll_loop():
        while True:
            try:
                since = last_seen[0] or (datetime.now() - timedelta(hours=hist_h))
                new   = load_detections(csv_path, since)
                # filtra so as realmente novas (depois do last_seen)
                new   = [d for d in new if datetime.fromisoformat(d["datetime"]) > since] if last_seen[0] else []
                for d in new:
                    await broadcast({"type":"detection", "historic": False, **d})
                    last_seen[0] = datetime.fromisoformat(d["datetime"])

                # pulso DOA ao vivo
                if has_doa:
                    last = load_doa_last(doa_path)
                    if last:
                        await broadcast({"type":"doa_live",
                                         "azimute":  last["azimute"],
                                         "is_voice": last["is_voice"],
                                         "ts":       last["ts"]})
            except Exception as e:
                print(f"[server] erro: {e}")
            await asyncio.sleep(poll)

    print(f"[server] ws://0.0.0.0:{ws_port} | {cfg['station_name']}")
    async with serve(ws_handler, "0.0.0.0", ws_port):
        await poll_loop()

if __name__ == "__main__":
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else "config.json"
    try: asyncio.run(run(cfg_path))
    except KeyboardInterrupt: print("[server] encerrado.")
