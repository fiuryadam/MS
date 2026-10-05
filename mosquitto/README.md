## Spuštění

```powershell
docker compose up -d
```

WebSocket pro aplikaci: `localhost:9999`, cesta `/mqtt`.

```powershell
docker run --rm -v c:/X/Y/mosquitto/config:/mosquitto/config eclipse-mosquitto:2 mosquitto_passwd -b /mosquitto/config/passwd novyuzivatel heslo
docker run --rm -v c:/X/Y/mosquitto/config:/mosquitto/config eclipse-mosquitto:2 chmod 644 /mosquitto/config/passwd
```

Po změně configu: `docker compose restart mosquitto`.
