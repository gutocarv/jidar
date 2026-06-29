# -*- coding: utf-8 -*-
"""
japidar - doa_logger.py
Le azimute do ReSpeaker USB 4-Mic Array e grava em CSV continuo.
Requer: pyusb, usb_4_mic_array/tuning.py no mesmo diretorio.

Uso: python3 doa_logger.py [config.json]
"""
import csv, json, os, signal, sys, time
from datetime import datetime
import usb.core
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tuning import Tuning

VENDOR_ID  = 0x2886
PRODUCT_ID = 0x0018
running    = True

def load_config(path="config.json"):
    with open(path) as f: return json.load(f)

def handle_sigint(sig, frame):
    global running; running = False

def main():
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else "config.json"
    cfg = load_config(cfg_path)
    log_path = cfg["paths"]["doa_log"]

    dev = usb.core.find(idVendor=VENDOR_ID, idProduct=PRODUCT_ID)
    if not dev:
        print("[doa_logger] ReSpeaker nao encontrado.")
        sys.exit(1)
    mic = Tuning(dev)
    print(f"[doa_logger] ReSpeaker conectado. Log: {log_path}")

    signal.signal(signal.SIGINT, handle_sigint)
    new_file = not os.path.exists(log_path)
    f = open(log_path, "a", newline="", encoding="utf-8")
    w = csv.writer(f)
    if new_file:
        w.writerow(["timestamp_iso","timestamp_unix","azimute","is_voice"])
        f.flush()

    count = 0
    t0 = time.time()
    while running:
        try:
            az = mic.direction
            iv = mic.is_voice()
            now = time.time()
            w.writerow([datetime.fromtimestamp(now).isoformat(), f"{now:.3f}", az, int(iv)])
            count += 1
            if count % 100 == 0:
                f.flush()
                print(f"[doa_logger] {count} leituras | {count/(now-t0):.1f}/s | az={az}")
        except Exception as e:
            print(f"[doa_logger] erro: {e}")
            time.sleep(1)
        time.sleep(0.1)

    f.flush(); f.close()
    print(f"[doa_logger] encerrado. {count} leituras gravadas.")

if __name__ == "__main__":
    main()
