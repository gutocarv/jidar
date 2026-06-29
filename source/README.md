# japidar

Sistema de mapeamento de territórios acústicos de aves em tempo real.
Combina detecção de espécies via BirdNET-Pi com localização espacial via ReSpeaker USB 4-Mic Array.

## O que faz

- Lê detecções de espécies do banco de dados do BirdNET-Pi (`birds.db`)
- Lê azimute de origem do canto via ReSpeaker (Direction of Arrival)
- Correlaciona os dois por timestamp e plota no mapa em tempo real
- Exibe foto e informações da espécie via Wikipedia ao clicar
- Nomes em português via arquivo `labels_pt.json` do próprio BirdNET-Pi
- Funciona com ou sem ReSpeaker (modo sem DOA só registra, não plota)

## Requisitos

- Raspberry Pi 4 ou 5 (recomendado: Pi 5)
- BirdNET-Pi instalado e rodando
- ReSpeaker USB 4-Mic Array (opcional para modo DOA)
- Python 3.11+
- Rede local (WiFi ou RJ45)

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
# linha ~109: troque response.tostring() por response.tobytes()
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

### 5. Copie os arquivos japidar

Copie todos os arquivos do pacote para `~/usb_4_mic_array/`:
- `config.json`
- `doa_logger.py`
- `dashboard_server.py`
- `dashboard.html`

### 6. Configure o config.json

```bash
nano ~/usb_4_mic_array/config.json
```

Ajuste os caminhos conforme sua instalação:

```json
{
  "station_name": "Nome da sua estação",
  "house": {
    "width_m": 12,
    "height_m": 9,
    "axis": "NS"
  },
  "respeaker": {
    "enabled": true,
    "rotation_offset": 0
  },
  "birdnetpi": {
    "db_path": "/home/guto/BirdNET-Pi/scripts/birds.db",
    "labels_pt": "/home/guto/BirdNET-Pi/model/l18n/labels_pt.json"
  },
  "paths": {
    "doa_log": "./doa_log.csv"
  },
  "server": {
    "ws_port": 8765,
    "http_port": 8181
  },
  "correlation": {
    "window_seconds": 6,
    "min_voice_fraction": 0.3,
    "history_hours": 24
  }
}
```

**Sem ReSpeaker:** defina `"enabled": false` em `respeaker`.

### 7. Teste manual (3 terminais)

```bash
# terminal 1 - grava DOA (apenas se tiver ReSpeaker)
cd ~/usb_4_mic_array && python3 doa_logger.py

# terminal 2 - backend WebSocket
cd ~/usb_4_mic_array && python3 dashboard_server.py

# terminal 3 - servidor HTTP
cd ~/usb_4_mic_array && python3 -m http.server 8181
```

Acesse: `http://<ip-do-pi>:8181/dashboard.html`

### 8. Calibração do offset de rotação

Com o sistema rodando:
1. Fique em frente ao ReSpeaker e bata palmas
2. Observe o azimute reportado no `doa_logger` ou no dashboard
3. Calcule a diferença entre o ângulo reportado e o Norte geográfico real
4. Ajuste `rotation_offset` no `config.json` e reinicie o `dashboard_server.py`

### 9. Autostart no boot (systemd)

Crie os serviços para os 3 processos subirem automaticamente:

```bash
sudo nano /etc/systemd/system/japidar-doa.service
```

```ini
[Unit]
Description=japidar DOA logger
After=network.target

[Service]
Type=simple
User=guto
WorkingDirectory=/home/guto/usb_4_mic_array
ExecStart=/usr/bin/python3 /home/guto/usb_4_mic_array/doa_logger.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo nano /etc/systemd/system/japidar-server.service
```

```ini
[Unit]
Description=japidar dashboard server
After=network.target

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
sudo nano /etc/systemd/system/japidar-web.service
```

```ini
[Unit]
Description=japidar HTTP server
After=network.target

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
sudo systemctl enable japidar-doa japidar-server japidar-web
sudo systemctl start japidar-doa japidar-server japidar-web

# verificar status
sudo systemctl status japidar-server
```

## Estrutura de arquivos

```
usb_4_mic_array/
├── tuning.py          # biblioteca ReSpeaker (do repo original)
├── config.json        # configuracao da estacao
├── doa_logger.py      # grava azimute em CSV continuo
├── dashboard_server.py# backend WebSocket
├── dashboard.html     # interface web
└── doa_log.csv        # gerado automaticamente
```

## Uso sem ReSpeaker

Defina `"enabled": false` no `config.json`. Nesse modo:
- O `doa_logger.py` nao precisa rodar
- O dashboard funciona normalmente mas sem pontos no mapa
- Deteccoes aparecem no log com status `sem_dados`
- Util para estacoes de monitoramento sem localizacao espacial

## Notas

- O Caddy do BirdNET-Pi ocupa a porta 80. Use a porta 8181 (ou outra livre) para o japidar.
- A porta 8080 pode estar ocupada pelo BirdNET-Pi. Verifique com `sudo ss -tlnp | grep 8080`.
- O `doa_log.csv` cresce continuamente. Rotacione manualmente ou configure logrotate se necessario.
- Sincronizacao de relogio via NTP e essencial para correlacao correta entre estacoes multiplas.
