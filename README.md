# ImmichFrame Manager Sidecar

A fully self-hosted Flask sidecar for managing an ImmichFrame `Settings.json` file from a browser instead of repeatedly editing Docker Compose / Portainer stacks.

This version is maintained as a **hobby project**. It is not affiliated with, endorsed by, or supported by Immich, ImmichFrame, or their maintainers. Use it as a homelab helper and keep backups of your configuration.

## Original projects and documentation

- ImmichFrame GitHub: https://github.com/immichFrame/ImmichFrame
- ImmichFrame web install / `Settings.json` mounting: https://github.com/immichFrame/ImmichFrame/blob/main/Install_Web.md
- ImmichFrame documentation site: https://immichframe.dev/
- Immich API documentation: https://api.immich.app/
- Immich album API: https://api.immich.app/endpoints/albums/getAllAlbums

## What this sidecar does

The manager runs next to ImmichFrame and edits the same mounted config folder:

```text
ImmichFrame container       /app/Config/Settings.json
Manager sidecar container   /config/Settings.json
Host path                   /ddata/immichFrame/config/Settings.json
```

It provides:

- Browser UI for ImmichFrame `General` settings.
- Browser UI for ImmichFrame `Accounts` settings.
- Immich API integration for listing albums visible to an account/API key.
- Persistent album cache in `/data/state.json`.
- Automatic initial album load when an account already has an Immich URL and API key.
- Manual album-cache refresh button.
- Background sync.
- Optional automatic ImmichFrame restart through Docker socket.
- Backup of `Settings.json` before every write.
- Raw JSON editor for advanced fields.
- Policy modes for album handling:
  - **Manual**
  - **Allow all**
  - **Show selected**
  - **Hide selected**
- Shared/owned album filters.
- Optional album-name prefix filter.

## Important concept

ImmichFrame expects explicit album IDs in its account configuration. This manager makes that less painful by reading albums from Immich, caching them, and writing the correct IDs to `Settings.json`.

The most natural workflow is:

```text
Create Immich user: frame
Share albums with user: frame
Use frame user's API key in ImmichFrame Manager
Set album mode to Allow all
Enable Auto-sync
```

Then album management happens inside Immich: share an album with the `frame` user to show it on the frame, unshare it to remove it.

## Album modes explained

### Manual

The sidecar does not overwrite `Accounts[n].Albums`. Use this when you want to paste album UUIDs yourself or when testing.

### Allow all

The sidecar writes every cached album that passes the filters into `Accounts[n].Albums`.

Good for:

```text
Albums visible to frame user = albums shown on frame
```

### Show selected

The sidecar writes only checked albums into `Accounts[n].Albums`.

Good for a strict allow-list.

### Hide selected

The sidecar writes all matching albums except checked albums.

Good when you want almost everything visible but want to exclude a few albums.

## Persistent album cache

Album data is stored in the manager state file, usually:

```text
/ddata/immichFrame/data/state.json
```

The cache is used so that when you open an existing account page, the album table is already populated. You do not need to press refresh every time.

The cache is refreshed when:

- You open an account page for the first time and the account already has URL + API key.
- You click **Refresh album cache**.
- You save an account with **After saving, refresh and persist the album list from Immich** checked.
- You click **Apply policy now**.
- Background sync runs for an account with auto-sync enabled.

The cached album data intentionally stores only useful UI fields:

```json
{
  "id": "album-uuid",
  "albumName": "Family",
  "assetCount": 123,
  "shared": true,
  "ownerName": "example@example.com"
}
```

It does not store the full Immich album response.

## Installation on your current host layout

Your current paths:

```text
/ddata/immichFrame/config
/ddata/immichFrame/data
```

Create them:

```bash
sudo mkdir -p /ddata/immichFrame/config
sudo mkdir -p /ddata/immichFrame/data
sudo chmod 755 /ddata /ddata/immichFrame /ddata/immichFrame/config /ddata/immichFrame/data
```

If you already have `Settings.json`, make it readable by ImmichFrame:

```bash
sudo chmod 644 /ddata/immichFrame/config/Settings.json
```

If you do not have one yet, copy the example:

```bash
cp examples/Settings.example.json /ddata/immichFrame/config/Settings.json
sudo chmod 644 /ddata/immichFrame/config/Settings.json
```

## Build the manager image

Portainer stacks usually cannot use `build: .` unless the stack is deployed from a Git repository containing the Dockerfile. Build the image once on the Docker host:

```bash
cd immichframe-manager
docker build -t immich_frame_manager:latest .
```

Then use `image: immich_frame_manager:latest` in Portainer.

## Docker Compose example matching your setup

```yaml
services:
  immichframe:
    container_name: immichframe2
    image: ghcr.io/immichframe/immichframe:latest
    restart: unless-stopped
    ports:
      - "7891:8080"
    volumes:
      - immichframe_config:/app/Config
    environment:
      TZ: Europe/Amsterdam

  immichframe-manager:
    container_name: immichframe-manager
    image: immich_frame_manager:latest
    restart: unless-stopped
    depends_on:
      - immichframe
    ports:
      - "7892:8099"
    volumes:
      - immichframe_config:/config
      - immichframe_manager_data:/data
      - /var/run/docker.sock:/var/run/docker.sock
    environment:
      TZ: Europe/Amsterdam
      ADMIN_USERNAME: admin
      ADMIN_PASSWORD: change-this-password
      SETTINGS_FILE: /config/Settings.json
      STATE_FILE: /data/state.json
      IMMICHFRAME_CONTAINER: immichframe2
      ENABLE_DOCKER_RESTART: "true"
      AUTO_RESTART_ON_SYNC: "true"
      ENABLE_BACKGROUND_SYNC: "true"
      SYNC_INTERVAL_SECONDS: "300"
      INITIAL_ALBUM_LOAD: "true"
      FLASK_HOST: 0.0.0.0
      FLASK_PORT: "8099"

volumes:
  immichframe_config:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /ddata/immichFrame/config

  immichframe_manager_data:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /ddata/immichFrame/data
```

Open:

```text
http://your-docker-host:7892
```

ImmichFrame itself is exposed at:

```text
http://your-docker-host:7891
```

## First-use workflow

1. Build the manager image.
2. Deploy the compose stack.
3. Open the manager UI on port `7892`.
4. Log in with the configured username/password.
5. Open the account.
6. Set:
   - Immich server URL
   - Immich API key
7. Save the account.
8. The manager will refresh and persist the album cache.
9. Select an album mode.
10. Click **Apply policy now**.
11. ImmichFrame is restarted automatically if Docker socket restart is enabled.

## Recommended Immich setup

Create a separate Immich user, for example:

```text
frame@example.local
```

Create an API key for this user.

Then choose one of these models.

### Model A: Share-to-frame user

Best daily workflow.

```text
Share album with frame user = album appears on frame
Unshare album from frame user = album disappears from frame
```

Manager settings:

```text
Album mode: Allow all
Include shared albums: yes
Include owned albums: yes or no, depending on your preference
Auto-sync: enabled
```

### Model B: Prefix albums

Best when you do not want a separate user.

Name albums like:

```text
Frame - Family
Frame - Holidays
Frame - Kids
```

Manager settings:

```text
Album mode: Allow all
Name prefix filter: Frame - 
Auto-sync: enabled
```

### Model C: Manual checkbox curation

Best when you want strict control.

Manager settings:

```text
Album mode: Show selected
Refresh album cache
Check wanted albums
Save account & policy
Apply policy now
```

## Environment variables

| Variable | Default | Purpose |
|---|---:|---|
| `ADMIN_USERNAME` | empty | Optional login username. If set, login requires this username. |
| `ADMIN_PASSWORD` | empty | Enables login when set. Empty means no authentication. |
| `SECRET_KEY` | development default | Flask session secret. Set a long random value if exposing outside a trusted LAN/VPN. |
| `SETTINGS_FILE` | `/config/Settings.json` | ImmichFrame settings file to read/write. |
| `STATE_FILE` | `/data/sidecar-state.json` | Manager state file: album cache, selected albums, hidden albums, sync state. |
| `BACKUP_DIR` | `/config/backups` | Backup directory for `Settings.json` snapshots. |
| `IMMICHFRAME_CONTAINER` | `immichframe` | Docker container name to restart after applying changes. In your compose this is `immichframe2`. |
| `ENABLE_DOCKER_RESTART` | `true` | Compatibility alias for enabling restart behavior. |
| `AUTO_RESTART_ON_SYNC` | `true` | Restart ImmichFrame after a changed sync/apply. |
| `ENABLE_BACKGROUND_SYNC` | `true` | Enables the background sync worker. |
| `SYNC_INTERVAL_SECONDS` | `300` | Compatibility alias for sync interval. |
| `AUTO_SYNC_INTERVAL_SECONDS` | `300` | Background sync interval. Minimum effective interval is 30 seconds. |
| `INITIAL_ALBUM_LOAD` | `true` | Automatically load album cache when opening an account that has URL + API key and no cache yet. |
| `IMMICH_TIMEOUT_SECONDS` | `15` | Timeout for Immich API calls. |
| `FLASK_HOST` | `0.0.0.0` | Host for local Flask dev server. Gunicorn binds to all interfaces in Docker. |
| `FLASK_PORT` | `8099` | Web UI port inside the container. |
| `PORT` | `8099` | Alternative port variable; `FLASK_PORT` wins when both are set. |
| `GUNICORN_WORKERS` | `1` | Gunicorn worker count. One worker is recommended because this sidecar uses simple file-based state. |
| `GUNICORN_THREADS` | `4` | Gunicorn threads. |
| `GUNICORN_TIMEOUT` | `120` | Gunicorn request timeout. |

## Docker socket warning

This volume:

```yaml
- /var/run/docker.sock:/var/run/docker.sock
```

allows the manager to restart the ImmichFrame container. It also gives the container powerful access to Docker.

For a trusted homelab LAN this may be acceptable. For anything exposed to the internet, do not do this.

If you remove the Docker socket mount:

- The manager can still edit `Settings.json`.
- Automatic restart will fail or be skipped.
- You restart ImmichFrame manually:

```bash
docker restart immichframe2
```

## Permissions

ImmichFrame must be able to read:

```text
/app/Config/Settings.json
```

On the host this means:

```bash
sudo chmod 755 /ddata /ddata/immichFrame /ddata/immichFrame/config
sudo chmod 644 /ddata/immichFrame/config/Settings.json
```

The manager now sets saved `Settings.json` files to `0644` where the filesystem allows it. This avoids the common ImmichFrame error:

```text
Access to the path '/app/Config/Settings.json' is denied.
```

## Backup behavior

Before every `Settings.json` write, the previous file is copied to:

```text
/ddata/immichFrame/config/backups/
```

Example:

```text
Settings.json.20260511-190235.bak
```

To roll back:

```bash
cp /ddata/immichFrame/config/backups/Settings.json.YYYYMMDD-HHMMSS.bak /ddata/immichFrame/config/Settings.json
docker restart immichframe2
```

## What is stored where

### `Settings.json`

Owned by ImmichFrame. The manager edits known fields but preserves unknown fields.

Typical structure:

```json
{
  "General": {},
  "Accounts": [
    {
      "Name": "Living room frame",
      "ImmichServerUrl": "http://immich-server:2283",
      "ApiKey": "...",
      "Albums": ["album-id-1", "album-id-2"],
      "ExcludedAlbums": [],
      "People": [],
      "Tags": []
    }
  ]
}
```

### `state.json`

Owned by the manager.

Stores:

- album mode
- selected album IDs
- hidden album IDs
- cached album list
- last refresh timestamp
- last applied album IDs
- last error

## API behavior

The manager calls the Immich album endpoint using the configured account API key.

To be tolerant of Immich version differences around shared albums, it merges these calls:

```text
GET /api/albums
GET /api/albums?shared=true
GET /api/albums?shared=false
```

If `/api/albums` is not available, it also tries `/albums`.

The manager does **not** create, modify, share, or delete Immich albums. It only reads album metadata.

## Troubleshooting

### Portainer says `failed to read dockerfile: open Dockerfile: no such file or directory`

You used:

```yaml
build: .
```

inside a Portainer stack that does not have a Dockerfile context. Build the image manually:

```bash
docker build -t immich_frame_manager:latest .
```

Then use:

```yaml
image: immich_frame_manager:latest
```

### ImmichFrame cannot read Settings.json

Run:

```bash
sudo chmod 755 /ddata /ddata/immichFrame /ddata/immichFrame/config
sudo chmod 644 /ddata/immichFrame/config/Settings.json
```

Then:

```bash
docker restart immichframe2
```

### Manager cannot restart ImmichFrame

Check:

```yaml
IMMICHFRAME_CONTAINER: immichframe2
```

This must match:

```yaml
container_name: immichframe2
```

Also check that the Docker socket is mounted:

```yaml
- /var/run/docker.sock:/var/run/docker.sock
```

### Albums do not appear in the manager

Check these items:

1. Immich URL is reachable from the manager container.
2. API key is valid.
3. API key's user can see the albums.
4. If using a separate `frame` user, the albums are shared with that user.
5. Click **Test Immich**.
6. Click **Refresh album cache**.

### Albums appear in the manager but not in ImmichFrame

Click **Apply policy now**. The manager must write the chosen album list into `Settings.json`.

Then restart ImmichFrame manually if automatic restart is disabled:

```bash
docker restart immichframe2
```

## Development

Run locally:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export SETTINGS_FILE="$PWD/config/Settings.json"
export STATE_FILE="$PWD/manager-data/state.json"
export ADMIN_USERNAME=admin
export ADMIN_PASSWORD=change-this-password
python -m app.main
```

Build container:

```bash
docker build -t immich_frame_manager:latest .
```

Run container manually:

```bash
docker run --rm -p 7892:8099 \
  -v /ddata/immichFrame/config:/config \
  -v /ddata/immichFrame/data:/data \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -e ADMIN_USERNAME=admin \
  -e ADMIN_PASSWORD='change-this-password' \
  -e SETTINGS_FILE=/config/Settings.json \
  -e STATE_FILE=/data/state.json \
  -e IMMICHFRAME_CONTAINER=immichframe2 \
  immich_frame_manager:latest
```

## Safety notes

- Do not expose this UI directly to the public internet.
- Use a strong `ADMIN_PASSWORD`.
- Set a strong `SECRET_KEY` if you expose it beyond a trusted LAN/VPN.
- Treat Docker socket access as highly privileged.
- Keep `Settings.json` backups.
- Remember this is a hobby-maintained sidecar, not an official ImmichFrame component.
