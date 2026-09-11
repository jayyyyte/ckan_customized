# Giai đoạn 2 — Đóng gói image + test bằng docker compose

Mục tiêu: có image `ckan-lakehouse:<version>` gồm CKAN 2.12.0 + theme, cấu hình hoàn toàn bằng biến môi trường, đã chạy thử ở local. Compose file ở giai đoạn này ánh xạ 1-1 sang manifest K8s ở GĐ3.

## Image gốc `ckan/ckan-base:2.12.0` — thông tin đã kiểm chứng

Nguồn: `ckan-docker-base/ckan-2.12/Dockerfile`, `setup/start_ckan.sh`, `setup/prerun.py` và Docker Hub, đọc ngày 2026-09-11.

| Mục | Giá trị |
|---|---|
| Tags | `2.12`, `2.12.0`, `2.12-py3.14`, `2.12.0-py3.14`. Bản dev: `ckan/ckan-dev:2.12.0`. **Chỉ có Python 3.14** (không có biến thể py3.10 như 2.11) |
| Base | Multi-stage: stage `builder` cài CKAN, rồi copy `/usr/local`, `src`, `ckan.ini` sang stage `base` (`python:3.14-slim-bookworm`). Image runtime không còn g++/git |
| `APP_DIR` / `SRC_DIR` | `/srv/app` / `/srv/app/src` |
| `CKAN_INI` | `/srv/app/ckan.ini`, sinh lúc build bằng `ckan generate config` |
| `CKAN_STORAGE_PATH` | `/var/lib/ckan` (mount volume vào đây) |
| Users | `ckan-sys` (uid 502) sở hữu `/srv/app` và `/docker-entrypoint.d`. `ckan` (uid 503) là user runtime, sở hữu `ckan.ini` và storage. **`/usr/local` (site-packages) thuộc `root`**, khác 2.11 |
| Server | uWSGI `--http [::]:5000`, 2 process. Chỉnh bằng `UWSGI_OPTS`, `EXTRA_UWSGI_OPTS`, `UWSGI_HARAKIRI` |
| Plugin mặc định | `CKAN__PLUGINS="image_view text_view datatables_view datastore envvars"`; `ckanext-envvars` v0.0.6 có sẵn |
| Khởi động | `start_ckan.sh` (giống hệt 2.11). Nếu `SECRET_KEY` trống thì **tự sinh** `SECRET_KEY`, `WTF_CSRF_SECRET_KEY` và JWT secret. Sau đó chạy `prerun.py`, rồi `/docker-entrypoint.d/*.sh\|*.py`, cuối cùng là uwsgi |
| `prerun.py` | Giống hệt 2.11: chờ DB (`CKAN_SQLALCHEMY_URL`) → `ckan db init` (**chạy mỗi lần start**, idempotent, đồng thời upgrade schema) → set plugins → datastore (`CKAN_DATASTORE_WRITE_URL`) + set quyền → kiểm tra Solr (`CKAN_SOLR_URL`) → tạo sysadmin nếu có `CKAN_SYSADMIN_NAME/PASSWORD/EMAIL` |
| Healthcheck (ckan-docker) | `wget -qO /dev/null http://localhost:5000/api/action/status_show` |

Repo tham chiếu `ckan/ckan-docker` (compose mẫu) **vẫn đang dùng `FROM ckan/ckan-base:2.11`** tính đến 2026-09-11. Dự án chỉ dùng repo đó làm mẫu cấu trúc; image của mình build `FROM 2.12.0`.

Có hai cách cấu hình bằng biến môi trường:
1. **Biến CKAN core hỗ trợ sẵn:** `CKAN_SQLALCHEMY_URL`, `CKAN_DATASTORE_WRITE_URL`, `CKAN_DATASTORE_READ_URL`, `CKAN_SOLR_URL`, `CKAN_REDIS_URL`, `CKAN_SITE_URL`, `CKAN_SITE_ID`, `CKAN_STORAGE_PATH`, `CKAN_MAX_UPLOAD_SIZE_MB`, `CKAN_SMTP_*`.
2. **Qua plugin `envvars`** (phải đứng **cuối** `CKAN__PLUGINS`):
   - `CKAN__A__B` → `ckan.a.b`. Ví dụ `CKAN__LOCALE_DEFAULT=vi` → `ckan.locale_default`.
   - `CKAN___A__B` (ba dấu gạch dưới) → `a.b`, **không** có tiền tố `ckan.`. Ví dụ `CKAN___API_TOKEN__JWT__ENCODE__SECRET`.

## Cấu trúc repo sau GĐ2

```
ckan_customized/
├── ckanext-<theme>/            # từ GĐ1
├── docker/
│   ├── Dockerfile
│   ├── compose.yaml
│   ├── .env.example            # commit; .env thật KHÔNG commit
│   ├── docker-entrypoint.d/    # script init bổ sung (nếu cần)
│   └── postgres-init/          # tạo role/DB cho container db local
├── .dockerignore
└── .gitignore
```

## Dockerfile (khung)

```dockerfile
FROM ckan/ckan-base:2.12.0

# 2.12: /usr/local (site-packages) thuộc root → pip install phải chạy bằng root.
# Source extension để trong SRC_DIR, chủ sở hữu ckan-sys như phần còn lại của /srv/app.
USER root
COPY --chown=ckan-sys:ckan-sys ckanext-<theme> ${SRC_DIR}/ckanext-<theme>
# Cài -e (giống cách ckan-docker làm): template/asset đọc thẳng từ source,
# không phụ thuộc vào việc MANIFEST.in/package_data khai báo đủ hay chưa.
RUN pip3 install --no-cache-dir -e ${SRC_DIR}/ckanext-<theme> && \
    chown -R ckan-sys:ckan-sys ${SRC_DIR}/ckanext-<theme>
# Extension khác (sau khi chốt Q4/Q5/Q10). Image runtime KHÔNG có git/g++,
# nên ưu tiên cài từ PyPI/wheel, ví dụ:
# RUN pip3 install --no-cache-dir 'ckanext-file-keeper-cloud[s3]'

COPY --chown=ckan-sys:ckan-sys docker/docker-entrypoint.d/ /docker-entrypoint.d/

USER ckan
ENV CKAN__PLUGINS="<theme> activity image_view text_view datatables_view envvars"
```

- Build context là **gốc repo**: `docker build -f docker/Dockerfile -t ckan-lakehouse:0.1.0 .`
- Tag luôn theo phiên bản (`0.1.0`, `0.1.1`…), **không dùng `latest`** (xem gotchas về pull policy).
- Nếu extension cần build từ git hoặc C: runtime 2.12 không có `git`/`g++`, nên phải `apt-get install` tạm hoặc dùng multi-stage riêng.
- Kiểm tra lại user/đường dẫn mỗi khi đổi base tag:
  ```bash
  docker run --rm ckan/ckan-base:2.12.0 sh -c 'id; python3 -V; env | grep -E "APP_DIR|SRC_DIR|CKAN_INI"; ls -ld /usr/local/lib/python3*/site-packages'
  ```

## compose.yaml (khung)

```yaml
services:
  db:
    image: postgres:16-alpine            # cùng major với postgres-service trên cluster
    environment: [POSTGRES_PASSWORD=${POSTGRES_PASSWORD}]
    volumes: [pg_data:/var/lib/postgresql/data, ./postgres-init:/docker-entrypoint-initdb.d:ro]
    healthcheck: {test: ["CMD", "pg_isready", "-U", "postgres"], interval: 5s}
  solr:
    image: ckan/ckan-solr:2.12-solr9
    volumes: [solr_data:/var/solr]
  redis:
    image: redis:7-alpine
  ckan:
    build: {context: .., dockerfile: docker/Dockerfile}
    image: ckan-lakehouse:0.1.0
    env_file: .env
    ports: ["5000:5000"]                 # không cần nginx: cluster cũng không có ingress
    volumes: [ckan_storage:/var/lib/ckan]
    depends_on: {db: {condition: service_healthy}, solr: {condition: service_started}, redis: {condition: service_started}}
    healthcheck: {test: ["CMD", "wget", "-qO", "/dev/null", "http://localhost:5000/api/action/status_show"], interval: 30s, start_period: 120s}
volumes: {pg_data: {}, solr_data: {}, ckan_storage: {}}
```

- Runtime 2.12 cài `curl` chứ không chắc có `wget`. Chạy thử `docker exec <ckan> which wget curl` rồi đổi lệnh healthcheck cho phù hợp (ví dụ `curl -fsS http://localhost:5000/api/action/status_show`).
- Container Solr của GĐ1 (`ckan-solr`, cổng 8983) có thể trùng cổng. Hoặc dừng nó, hoặc không publish cổng Solr trong compose (như khung trên đang làm).

## `.env.example` (khung, không chứa giá trị thật)

```dotenv
POSTGRES_PASSWORD=change-me
CKAN_SQLALCHEMY_URL=postgresql://ckan_default:change-me@db/ckan_default
CKAN_SOLR_URL=http://solr:8983/solr/ckan
CKAN_REDIS_URL=redis://redis:6379/1
CKAN_SITE_URL=http://localhost:5000
CKAN_SITE_ID=default
CKAN_STORAGE_PATH=/var/lib/ckan
CKAN_SYSADMIN_NAME=admin
CKAN_SYSADMIN_PASSWORD=change-me
CKAN_SYSADMIN_EMAIL=admin@example.com
CKAN__LOCALE_DEFAULT=vi
CKAN__LOCALES_OFFERED=vi en
# Theme gốc (Q9) — bỏ comment nếu chọn Midnight Blue
# CKAN__BASE_TEMPLATES_FOLDER=templates-midnight-blue
# CKAN__BASE_PUBLIC_FOLDER=public-midnight-blue
# Cố định secret để restart không làm mất session / vô hiệu API token (xem gotchas)
CKAN___SECRET_KEY=generate-me
CKAN___WTF_CSRF_SECRET_KEY=generate-me
CKAN___API_TOKEN__JWT__ENCODE__SECRET=string:generate-me
CKAN___API_TOKEN__JWT__DECODE__SECRET=string:generate-me
```

Sinh secret bằng lệnh: `python3 -c 'import secrets; print(secrets.token_urlsafe())'`

⚠ **Cần xác minh trong GĐ2:** các biến `CKAN___SECRET_KEY` và `CKAN___WTF_CSRF_SECRET_KEY` có thật sự ghi đè được giá trị do `start_ckan.sh` tự sinh không.

Cách kiểm tra:
1. Tạo một API token.
2. Chạy `docker compose restart ckan`.
3. Gọi API bằng token cũ. Nếu vẫn dùng được là đạt.

Ghi kết quả vào gotchas.

## Bảng ánh xạ cấu hình

Điền dần từ GĐ1. Mỗi key `ckan.ini` đã chỉnh ở local phải có biến env tương ứng cho GĐ2/3.

| Key `ckan.ini` | Local (GĐ1) | Env (GĐ2/3) | Giá trị K8s | Secret? |
|---|---|---|---|---|
| `sqlalchemy.url` | `postgresql://ckan_default:***@localhost/ckan_default` | `CKAN_SQLALCHEMY_URL` | `postgresql://ckan_default:***@postgres-service.lakehouse:5432/ckan_default` | ✔ |
| `solr_url` | `http://localhost:8983/solr/ckan` | `CKAN_SOLR_URL` | `http://ckan-solr:8983/solr/ckan` | |
| `ckan.redis.url` | `redis://localhost:6379/0` | `CKAN_REDIS_URL` | `redis://ckan-redis:6379/0` | |
| `ckan.site_url` | `http://localhost:5000` | `CKAN_SITE_URL` | `http://10.1.117.91:30500` | |
| `ckan.storage_path` | `/home/tlinh/ckan/storage` | `CKAN_STORAGE_PATH` | `/var/lib/ckan` | |
| `ckan.plugins` | `<theme> activity ...` | `CKAN__PLUGINS` | giống local, `envvars` ở cuối | |
| `ckan.base_templates_folder` / `ckan.base_public_folder` | theo Q9 | `CKAN__BASE_TEMPLATES_FOLDER` / `CKAN__BASE_PUBLIC_FOLDER` | theo Q9 | |
| `ckan.locale_default` | `vi` | `CKAN__LOCALE_DEFAULT` | `vi` | |
| `debug` | `true` | *(không đặt)* | `false` | |
| *(thêm khi phát sinh)* | | | | |

## Kiểm thử trước khi sang GĐ3
1. `docker compose up -d --build`, sau đó `docker compose ps` phải thấy `ckan` ở trạng thái **healthy**.
2. Theme hiển thị đúng: logo, màu, trang chủ, footer, tiếng Việt.
3. Chạy lại smoke test của GĐ1: org, dataset, upload, search, API.
4. `docker compose restart ckan`: dữ liệu, file upload, đăng nhập và API token vẫn còn.
5. `docker compose down && docker compose up -d` (giữ volume): mọi thứ vẫn còn.
6. Xuất image: `docker save ckan-lakehouse:0.1.0 | gzip > ckan-lakehouse_0.1.0.tar.gz` (tarball **không** commit).

## Tiêu chí hoàn thành GĐ2
- [ ] Qua hết 6 bước kiểm thử.
- [ ] Bảng ánh xạ cấu hình đầy đủ.
- [ ] Đã xác minh biến secret (xem ⚠ ở trên) và ghi lại kết quả.
