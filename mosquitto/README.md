## Spuštění

```powershell
docker compose up -d
```

WebSocket pro aplikaci: `localhost:9999`, cesta `/mqtt`, **TLS (WSS)** — v GUI nechte zapnuté „TLS (WSS)“.

### Certifikáty (vlastní CA)

Před prvním startem nebo po smazání certů v `config/certs/`:

```powershell
docker run --rm --entrypoint sh -v c:/School/ChatMS/mosquitto:/mosquitto -w /mosquitto alpine/openssl generate-certs.sh
```

Soubory: `config/certs/ca.crt`, `ca.key`, `server.crt`, `server.key`.

### Důvěra certifikátu ve Windows (prohlížeč)

Prohlížeč musí důvěřovat `ca.crt`, jinak WSS spojení selže (např. `AMQJS0007E Socket error`).

```powershell
Import-Certificate -FilePath .\mosquitto\config\certs\ca.crt -CertStoreLocation Cert:\CurrentUser\Root
```

Poté **úplně ukončete a znovu spusťte** Chrome nebo Edge.

Záložní postup bez importu CA: v prohlížeči otevřete `https://localhost:9999/` a potvrďte výjimku pro tento hostitel (méně spolehlivé než import CA).

Po změně configu nebo certů:

```powershell
docker compose restart mosquitto
```

### Uživatelé MQTT

```powershell
docker run --rm -v c:/School/ChatMS/mosquitto/config:/mosquitto/config eclipse-mosquitto:2 mosquitto_passwd -b /mosquitto/config/passwd novyuzivatel heslo
docker run --rm -v c:/School/ChatMS/mosquitto/config:/mosquitto/config eclipse-mosquitto:2 chmod 644 /mosquitto/config/passwd
```

Po změně hesel: `docker compose restart mosquitto`.

### Ověření TLS

```powershell
docker run --rm -v c:/School/ChatMS/mosquitto/config/certs:/certs alpine/openssl s_client -connect host.docker.internal:9999 -CAfile /certs/ca.crt -servername localhost
```

V logu Mosquitta by měl být listener na portu 9999 s TLS; v DevTools (Network) u WebSocketu URL začíná `wss://`.
