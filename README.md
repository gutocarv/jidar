# jidar

**Mapeamento de territórios acústicos de aves em tempo real**

Sistema que combina detecção de espécies via BirdNET-Pi com localização espacial via ReSpeaker USB 4-Mic Array, plotando em tempo real num mapa orientado da propriedade. Também publica um mapa público via GitHub Pages, atualizado automaticamente a cada 15 minutos.

🗺️ **Mapa público:** https://gutocarv.github.io/jidar/

---

## Como funciona

```
BirdNET-Pi → birds.db
doa_logger.py → doa_log.csv        (azimute contínuo)
correlate.py (cron 5min) → detections_com_azimute.csv
export_json.py (cron 15min) → GitHub Pages (data.json)
dashboard_server.py → WebSocket → dashboard.html (rede local)
```

O `correlate.py` cruza as detecções de espécie com as leituras de azimute por janela de timestamp (±3s), aplica o offset de calibração do ReSpeaker e gera um CSV com espécie + azimute + quadrante + qualidade. O dashboard local recebe via WebSocket em tempo real; o mapa público é atualizado a cada 15 minutos via GitHub API.

---

## Requisitos de hardware

- Raspberry Pi 4 ou 5 (recomendado com cooler ativo — o BirdNET-Pi sozinho já opera próximo ao limite térmico)
- BirdNET-Pi instalado e rodando
- ReSpeaker USB 4-Mic Array
- Rede local (WiFi ou RJ45)

---

## Instalação

### 1. Clone o repositório do ReSpeaker

```bash
cd ~
git clone https://github.com/respeaker/usb_4_mic_array.git
cd usb_4_mic_array
```

### 2. Corrija compatibilidade com Python 3.11+

```bash
nano tuning.py
```

Linha ~109 — troca:
```python
response = struct.unpack(b'ii', response.tostring())
```
Por:
```python
response = struct.unpack(b'ii', response.tobytes())
```

### 3. Instale as dependências

```bash
pip install pyusb websockets --break-system-packages
```

### 4. Configure a permissão USB do ReSpeaker

```bash
sudo nano /etc/udev/rules.d/99-respeaker.rules
```

Adicione:
```
SUBSYSTEM=="usb", ATTRS{idVendor}=="2886", ATTRS{idProduct}=="0018", MODE="0666"
```

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger
# desconecte e reconecte o cabo USB do ReSpeaker
```

### 5. Ative WAL no banco do BirdNET-Pi

Evita conflito de lock entre o BirdNET-Pi (escrita) e o correlate.py (leitura):

```bash
sqlite3 ~/BirdNET-Pi/scripts/birds.db "PRAGMA journal_mode=WAL;"
```

### 6. Copie os arquivos jidar

Copie para `~/usb_4_mic_array/`:
- `config.json`
- `doa_logger.py`
- `dashboard_server.py`
- `dashboard.html`
- `correlate.py`
- `export_json.py`

### 7. Configure o config.json

```bash
nano ~/usb_4_mic_array/config.json
```

Campos obrigatórios a ajustar:

```json
{
  "station_name": "Nome da sua estação",
  "house": {
    "width_m": 12,
    "height_m": 9
  },
  "respeaker": {
    "enabled": true,
    "rotation_offset": 0
  },
  "birdnetpi": {
    "db_path": "/home/guto/BirdNET-Pi/scripts/birds.db",
    "labels_pt": "/home/guto/BirdNET-Pi/model/l18n/labels_pt.json"
  },
  "correlation": {
    "min_voice_fraction": 0.0
  },
  "github": {
    "token": "SEU_TOKEN_AQUI",
    "repo": "seu-usuario/jidar",
    "export_hours": 48
  }
}
```

**Nota:** Se o VAD (`is_voice`) do ReSpeaker não disparar na sua instalação (sempre retorna 0), defina `min_voice_fraction: 0.0`.

### 8. Calibração do offset de rotação

Com o sistema rodando, faça barulho exatamente ao Sul da casa (180°) e observe o azimute reportado. Calcule:

```
offset = 180 - azimute_reportado
```

Exemplo: reportou 304° → offset = 180 - 304 = -124

Ajuste `rotation_offset` no `config.json`.

### 9. Configure os serviços systemd

```bash
sudo nano /etc/systemd/system/jidar-doa.service
```

```ini
[Unit]
Description=jidar DOA logger
After=network.target sound.target

[Service]
Type=simple
User=guto
WorkingDirectory=/home/guto/usb_4_mic_array
ExecStart=/usr/bin/python3 /home/guto/usb_4_mic_array/doa_logger.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo nano /etc/systemd/system/jidar-server.service
```

```ini
[Unit]
Description=jidar dashboard WebSocket server
After=network.target jidar-doa.service

[Service]
Type=simple
User=guto
WorkingDirectory=/home/guto/usb_4_mic_array
ExecStart=/usr/bin/python3 /home/guto/usb_4_mic_array/dashboard_server.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo nano /etc/systemd/system/jidar-web.service
```

```ini
[Unit]
Description=jidar HTTP server
After=network.target jidar-server.service

[Service]
Type=simple
User=guto
WorkingDirectory=/home/guto/usb_4_mic_array
ExecStart=/usr/bin/python3 -m http.server 8181
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable jidar-doa jidar-server jidar-web
sudo systemctl start jidar-doa jidar-server jidar-web
sudo systemctl status jidar-doa jidar-server jidar-web
```

### 10. Configure o cron

```bash
crontab -e
```

```
*/5 * * * * cd /home/guto/usb_4_mic_array && python3 correlate.py
*/15 * * * * cd /home/guto/usb_4_mic_array && nice -n 19 python3 export_json.py
```

### 11. Ative o GitHub Pages

No repositório GitHub: Settings → Pages → Source: `main` branch, pasta `/ (root)`.

O mapa público fica em: `https://seu-usuario.github.io/jidar/`

---

## Acesso ao dashboard local

```
http://<ip-do-pi>:8181/dashboard.html
```

---

## Arquivos do projeto

| Arquivo | Função |
|---|---|
| `config.json` | Configuração da estação |
| `doa_logger.py` | Grava azimute em CSV contínuo |
| `correlate.py` | Cruza birds.db + doa_log.csv, aplica offset, gera CSV |
| `dashboard_server.py` | Backend WebSocket, serve detecções em tempo real |
| `dashboard.html` | Dashboard local com mapa ao vivo |
| `export_json.py` | Exporta CSV para GitHub Pages via API |
| `index.html` | Mapa público (GitHub Pages) |
| `doa_log.csv` | Gerado automaticamente pelo doa_logger |
| `detections_com_azimute.csv` | Gerado automaticamente pelo correlate |

---

## Notas de instalação em campo

- **Temperatura:** O BirdNET-Pi sozinho opera o Pi4 próximo a 80°C. Use cooler ativo obrigatoriamente. Com cooler, temperatura cai para 44-47°C.
- **Porta HTTP:** O BirdNET-Pi usa a porta 8080 (gotty). Use 8181 para o jidar-web.
- **Conflito SQLite:** Aplique o WAL (passo 5) para evitar "Database busy" no BirdNET-Pi.
- **IP fixo:** Configure IP estático no Pi para evitar perda de acesso após queda de DHCP do roteador.
- **ReSpeaker distante do cooler:** Instale o ReSpeaker fisicamente separado do Pi/cooler para evitar contaminação do DOA pelo ruído do ventilador.
- **VAD zero:** Em algumas instalações o `is_voice` do ReSpeaker retorna sempre 0. Defina `min_voice_fraction: 0.0` no config.

---

## Roadmap

- [ ] IP estático no Pi
- [ ] Instalação externa do ReSpeaker (cabo USB 4m, encapsulamento IP67)
- [ ] Calibração com Norte geográfico real
- [ ] Segundo ReSpeaker para estimativa de altitude (triangulação 3D)
- [ ] Integração multi-estação com casamento de dados por timestamp
