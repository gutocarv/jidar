# -*- coding: utf-8 -*-
"""
japidar - correlate.py
Casa deteccoes do birds.db com azimute do doa_log.csv,
aplica rotation_offset do config.json e gera detections_com_azimute.csv.

Uso:
    python3 correlate.py [config.json]

Ideal para rodar via cron a cada 30s:
    * * * * * cd /home/guto/usb_4_mic_array && python3 correlate.py
    * * * * * sleep 30 && cd /home/guto/usb_4_mic_array && python3 correlate.py
"""
import csv, json, math, os, sqlite3, sys
from datetime import datetime, timedelta

def load_config(path="config.json"):
    with open(path) as f: return json.load(f)

def load_labels_pt(path):
    if not path or not os.path.exists(path): return {}
    with open(path, encoding="utf-8") as f: return json.load(f)

def circular_mean(angles):
    if not angles: return None
    s = sum(math.sin(math.radians(a)) for a in angles)
    c = sum(math.cos(math.radians(a)) for a in angles)
    return round(math.degrees(math.atan2(s, c)) % 360, 1)

def circular_std(angles):
    if len(angles) < 2: return None
    s = sum(math.sin(math.radians(a)) for a in angles)
    c = sum(math.cos(math.radians(a)) for a in angles)
    R = math.sqrt(s**2 + c**2) / len(angles)
    return round(min(math.degrees(math.sqrt(max(-2*math.log(R+1e-9), 0))), 180.0), 1)

def apply_offset(az, offset):
    if az is None: return None
    return round((az + offset) % 360, 1)

def quadrant(az):
    if az is None: return "?"
    a = az % 360
    if   a < 22.5 or a >= 337.5: return "N"
    elif a < 67.5:  return "NE"
    elif a < 112.5: return "L"
    elif a < 157.5: return "SE"
    elif a < 202.5: return "S"
    elif a < 247.5: return "SO"
    elif a < 292.5: return "O"
    else:           return "NO"

def load_doa(path):
    rows = []
    if not os.path.exists(path): return rows
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                rows.append({"dt": datetime.fromisoformat(row["timestamp_iso"]),
                             "azimute": int(row["azimute"]),
                             "is_voice": int(row["is_voice"])})
            except: continue
    return rows

def fetch_detections(db_path, since_dt, labels_pt):
    if not os.path.exists(db_path): return []
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        SELECT Date, Time, Sci_Name, Com_Name, Confidence, File_Name
        FROM detections
        WHERE datetime(Date||'T'||Time) > datetime(?)
        ORDER BY Date, Time
    """, (since_dt.isoformat(),))
    rows = []
    for r in cur.fetchall():
        try:
            dt = datetime.fromisoformat(f"{r['Date']}T{r['Time']}")
            sci = r["Sci_Name"]
            rows.append({"datetime": dt, "sci_name": sci,
                         "com_name": r["Com_Name"],
                         "name_pt": labels_pt.get(sci, r["Com_Name"]),
                         "confidence": float(r["Confidence"]),
                         "file_name": r["File_Name"]})
        except: continue
    conn.close()
    return rows

def correlate_one(dt, doa_rows, window_sec, min_vf):
    half = window_sec / 2
    w = [r for r in doa_rows if abs((r["dt"]-dt).total_seconds()) <= half]
    if not w: return None, None, "sem_dados"
    angles = [r["azimute"] for r in w]
    vf = sum(1 for r in w if r["is_voice"]) / len(w)
    az  = circular_mean(angles)
    std = circular_std(angles)
    if vf < min_vf:        q = "baixa_atividade"
    elif std and std > 45: q = "azimute_disperso"
    else:                  q = "ok"
    return az, std, q

def main():
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else "config.json"
    cfg      = load_config(cfg_path)
    db_path  = cfg["birdnetpi"]["db_path"]
    labels_pt= load_labels_pt(cfg["birdnetpi"].get("labels_pt", ""))
    doa_path = cfg["paths"]["doa_log"]
    out_path = cfg["paths"].get("detections_csv", "./detections_com_azimute.csv")
    win_sec  = cfg["correlation"]["window_seconds"]
    min_vf   = cfg["correlation"]["min_voice_fraction"]
    hist_h   = cfg["correlation"]["history_hours"]
    offset   = cfg["respeaker"].get("rotation_offset", 0)

    since = datetime.now() - timedelta(hours=hist_h)
    dets  = fetch_detections(db_path, since, labels_pt)
    doa   = load_doa(doa_path)

    fields = ["datetime","sci_name","com_name","name_pt","confidence",
              "azimute","azimute_std","quadrante",
              "n_leituras_doa","voice_fraction","qualidade","file_name"]

    rows = []
    for d in dets:
        az_raw, std, q = correlate_one(d["datetime"], doa, win_sec, min_vf)
        az_cal = apply_offset(az_raw, offset)
        rows.append({
            "datetime":        d["datetime"].isoformat(),
            "sci_name":        d["sci_name"],
            "com_name":        d["com_name"],
            "name_pt":         d["name_pt"],
            "confidence":      round(d["confidence"], 3),
            "azimute":         az_cal,
            "azimute_std":     std,
            "quadrante":       quadrant(az_cal),
            "n_leituras_doa":  len([r for r in doa if abs((r["dt"]-d["datetime"]).total_seconds()) <= win_sec/2]),
            "voice_fraction":  round(sum(1 for r in doa if abs((r["dt"]-d["datetime"]).total_seconds()) <= win_sec/2 and r["is_voice"]) / max(1, len([r for r in doa if abs((r["dt"]-d["datetime"]).total_seconds()) <= win_sec/2])), 2),
            "qualidade":       q,
            "file_name":       d["file_name"],
        })

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    ok = sum(1 for r in rows if r["qualidade"] == "ok")
    print(f"[correlate] {len(rows)} deteccoes | {ok} ok | offset={offset} | -> {out_path}")

if __name__ == "__main__":
    main()
