# Giai đoạn 2 — Đóng gói image + test bằng docker compose

Mục tiêu: có image `ckan-lakehouse:<version>` gồm CKAN 2.11.6 + theme, cấu hình hoàn toàn bằng biến môi trường, đã chạy thử ở local. Compose file ở giai đoạn này ánh xạ 1-1 sang manifest K8s ở GĐ3.

## Image gốc `ckan/ckan-base:2.11.6` — thông tin đã kiểm chứng

Nguồn: `ckan-docker-base/ckan-2.11/Dockerfile`, `setup/start_ckan.sh`, `setup/prerun.py`, README của repo và Docker Hub, đọc ngày 2026-09-18.

| Mục | Giá trị |
|---|---|
| Tags | `2.11`, `2.11.6`, `2.11-py3.10`, `2.11.6-py3.10` (build 2026-08-27). Bản dev: `ckan/ckan-dev:2.11.6`. **Chỉ có Python 3.10** |
| Base | Một stage, `python:3.10-slim-bookworm`. Image runtime **có sẵn** `git`, `g++`, `libpq-dev`, `wget`, `patch` |
| `APP_DIR` / `SRC_DIR` | `/srv/app` / `/srv/app/src` |
| `CKAN_INI` | `/srv/app/ckan.ini`, sinh lúc build bằng `ckan generate config` |
| `CKAN_STORAGE_PATH` | `/var/lib/ckan` (mount volume vào đây) |
| Users | `ckan-sys` (uid 502) sở hữu `/srv/app`, `/docker-entrypoint.d` **và `/usr/local` (site-packages)**. `ckan` (uid 503) là user runtime, sở hữu `ckan.ini`, `src` và storage |
| Server | uWSGI `--http [::]:5000`, 2 process, `--harakiri` = `UWSGI_HARAKIRI` (image đặt 50). Chỉnh bằng `UWSGI_OPTS`, `EXTRA_UWSGI_OPTS` |
| Plugin mặc định | `CKAN__PLUGINS="image_view text_view datatables_view datastore envvars"`; `ckanext-envvars` v0.0.6 có sẵn |
| Khởi động | `start_ckan.sh` (giống hệt bản 2.12). Nếu `SECRET_KEY` trống thì **tự sinh** `SECRET_KEY`, `WTF_CSRF_SECRET_KEY` và JWT secret. Sau đó chạy `prerun.py`, rồi `/docker-entrypoint.d/*.sh\|*.py`, cuối cùng là uwsgi |
| `prerun.py` | Giống hệt bản 2.12: chờ DB (`CKAN_SQLALCHEMY_URL`) → `ckan db init` (**chạy mỗi lần start**, idempotent, đồng thời upgrade schema) → set plugins → datastore (`CKAN_DATASTORE_WRITE_URL`) + set quyền → kiểm tra Solr (`CKAN_SOLR_URL`) → tạo sysadmin nếu có `CKAN_SYSADMIN_NAME/PASSWORD/EMAIL` |
| Healthcheck (ckan-docker) | `wget -qO /dev/null http://localhost:5000/api/action/status_show` |

Repo tham chiếu `ckan/ckan-docker` (compose mẫu) dùng `FROM ckan/ckan-base:2.11`, đúng nhánh của dự án. Dự án chỉ dùng repo đó làm mẫu cấu trúc; image của mình ghim bản vá cụ thể `FROM ckan/ckan-base:2.11.6`.

Có hai cách cấu hình bằng biến môi trường:
1. **Biến CKAN core hỗ trợ sẵn:** `CKAN_SQLALCHEMY_URL`, `CKAN_DATASTORE_WRITE_URL`, `CKAN_DATASTORE_READ_URL`, `CKAN_SOLR_URL`, `CKAN_REDIS_URL`, `CKAN_SITE_URL`, `CKAN_SITE_ID`, `CKAN_STORAGE_PATH`, `CKAN_MAX_UPLOAD_SIZE_MB`, `CKAN_SMTP_*`.
2. **Qua plugin `envvars`** (phải đứng **cuối** `CKAN__PLUGINS`):
   - `CKAN__A__B` → `ckan.a.b`. Ví dụ `CKAN__LOCALE_DEFAULT=vi` → `ckan.locale_default`.
   - `CKAN___A__B` (ba dấu gạch dưới) → `a.b`, **không** có tiền tố `ckan.`. Ví dụ `CKAN___API_TOKEN__JWT__ENCODE__SECRET`.

## Cấu trúc repo sau GĐ2

```
ckan_customized/
├── ckanext-evntheme/           # theme (từ 2026-09-19; ckanext-lakehouse_theme cũ đã xóa 2026-09-20)
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
FROM ckan/ckan-base:2.11.6

# /usr/local (site-packages) thuộc ckan-sys, user mặc định là ckan → cài bằng root cho gọn
# (ckan-sys cũng được). Source extension để trong SRC_DIR, chủ ckan-sys như phần còn lại của /srv/app.
USER root
COPY --chown=ckan-sys:ckan-sys ckanext-evntheme ${SRC_DIR}/ckanext-evntheme
# Cài -e (giống cách ckan-docker làm): template/asset đọc thẳng từ source,
# không phụ thuộc vào việc MANIFEST.in/package_data khai báo đủ hay chưa.
# .mo không commit (decision log 2026-09-14) → biên dịch từ .po ngay khi build.
# CSS đã biên dịch sẵn và có commit (assets/css/evn-theme.css) → image không cần Node/sass.
RUN pip3 install --no-cache-dir -e ${SRC_DIR}/ckanext-evntheme && \
    pybabel compile -d ${SRC_DIR}/ckanext-evntheme/ckanext/evntheme/i18n -D ckanext-evntheme && \
    chown -R ckan-sys:ckan-sys ${SRC_DIR}/ckanext-evntheme
# Extension khác (sau khi chốt Q4/Q5/Q10). Image 2.11 có git/g++ nên cài từ git được,
# nhưng vẫn nên ghim tag, ví dụ:
# RUN pip3 install --no-cache-dir -e 'git+https://github.com/ckan/ckanext-xloader.git@<tag>#egg=ckanext-xloader'

COPY --chown=ckan-sys:ckan-sys docker/docker-entrypoint.d/ /docker-entrypoint.d/

USER ckan
# Giống local; datatables_view cần DataStore nên chỉ thêm khi chốt Q4.
ENV CKAN__PLUGINS="evntheme activity tracking text_view image_view envvars"
```

- Migration của plugin: `prerun.py` của ckan-base chỉ chạy `db init` (gotchas 6h), nên phải chạy thêm `ckan db upgrade -p activity`, `-p tracking` và `-p evntheme`. Đặt các lệnh này trong `docker-entrypoint.d/`, hoặc chạy tay một lần sau khi DB lên.
- `tracking` cần chạy `ckan tracking update` hằng đêm (CronJob ở GĐ3).

- Build context là **gốc repo**: `docker build -f docker/Dockerfile -t ckan-lakehouse:0.1.0 .`
- Tag luôn theo phiên bản (`0.1.0`, `0.1.1`…), **không dùng `latest`** (xem gotchas về pull policy).
- Kiểm tra lại user/đường dẫn mỗi khi đổi base tag:
  ```bash
  docker run --rm ckan/ckan-base:2.11.6 sh -c 'id; python3 -V; env | grep -E "APP_DIR|SRC_DIR|CKAN_INI"; ls -ld /usr/local/lib/python3*/site-packages; which git wget curl'
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
    image: ckan/ckan-solr:2.11-solr9
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

- Image 2.11 có `wget` (cài trong Dockerfile gốc), nên healthcheck giống ckan-docker dùng được luôn.
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
# Theme gốc: 2.11 chỉ có classic (mặc định), không đặt CKAN__BASE_TEMPLATES_FOLDER / CKAN__BASE_PUBLIC_FOLDER
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

Điền dần từ GĐ1. Mỗi key `ckan.ini` đã chỉnh ở local phải có biến env tương ứng cho GĐ2/3. Script `setup_step2_switch_to_2.11.sh` đặt đúng các giá trị ở cột "Local".

| Key `ckan.ini` | Local (GĐ1) | Env (GĐ2/3) | Giá trị K8s | Secret? |
|---|---|---|---|---|
| `sqlalchemy.url` | `postgresql://ckan_default:***@localhost/ckan_default` | `CKAN_SQLALCHEMY_URL` | `postgresql://ckan_default:***@postgres-service.lakehouse:5432/ckan_default` | ✔ |
| `solr_url` | `http://127.0.0.1:8983/solr/ckan` (cũng là giá trị `generate config` 2.11 đặt sẵn) | `CKAN_SOLR_URL` | `http://ckan-solr:8983/solr/ckan` | |
| `ckan.redis.url` | `redis://localhost:6379/0` | `CKAN_REDIS_URL` | `redis://ckan-redis:6379/0` | |
| `ckan.site_url` | `http://localhost:5000` | `CKAN_SITE_URL` | `http://10.1.117.91:30500` | |
| `ckan.storage_path` | `/home/tlinh/ckan/storage` | `CKAN_STORAGE_PATH` | `/var/lib/ckan` | |
| `ckan.plugins` | `evntheme activity tracking text_view image_view` | `CKAN__PLUGINS` | giống local, `envvars` ở cuối (thêm `datastore xloader datatables_view` khi chốt Q4) | |
| `ckan.base_templates_folder` / `ckan.base_public_folder` | `templates` / `public` (mặc định; 2.11 chỉ nhận hai giá trị này) | *(không đặt)* | mặc định | |
| `ckan.locale_default` | `vi` | `CKAN__LOCALE_DEFAULT` | `vi` | |
| `ckan.locales_offered` | `vi en` | `CKAN__LOCALES_OFFERED` | `vi en` | |
| `ckan.site_title` | `Cổng dữ liệu EVN` | `CKAN__SITE_TITLE` | giống local | |
| `ckan.site_description` | `Chia sẻ dữ liệu dùng chung toàn Tập đoàn` | `CKAN__SITE_DESCRIPTION` | giống local | |
| `ckan.favicon` | `/evntheme/images/favicon.svg` | `CKAN__FAVICON` | giống local | |
| `ckanext.evntheme.domain_groups` | `kinh-doanh-dvkh ky-thuat-an-toan dau-tu-xay-dung tai-chinh-vat-tu to-chuc-nhan-su` | `CKANEXT__EVNTHEME__DOMAIN_GROUPS` | tên group thật trên cluster | |
| `ckanext.evntheme.*` khác (logo, liên hệ, link, `api_metrics_url`, `map_tile_url`…) | mặc định trong plugin (xem README của extension) | `CKANEXT__EVNTHEME__<KEY>` | Đặt khi có thông tin thật (Q2). Để trống `map_tile_url` nếu cluster không ra được Internet | |
| `ckan.datastore.write_url` / `read_url`, `ckanext.xloader.api_token` | chưa đặt (Q4, `setup_step3_datastore.sh`) | `CKAN_DATASTORE_WRITE_URL` / `CKAN_DATASTORE_READ_URL` / `CKANEXT__XLOADER__API_TOKEN` | DB `datastore_default` trên `postgres-service` | ✔ |
| `debug` | `true` (trong `[DEFAULT]`) | *(không đặt)* | `false` | |
| *(thêm khi phát sinh)* | | | | |

## Kiểm thử trước khi sang GĐ3
1. `docker compose up -d --build`, sau đó `docker compose ps` phải thấy `ckan` ở trạng thái **healthy**.
2. Theme hiển thị đúng ở mọi trang: trang chủ, tìm kiếm, chi tiết (4 tab), tổ chức, `/mds`. Kiểm cả logo, màu, footer và tiếng Việt. Font lấy từ bản tự host, không gọi Google Fonts.
3. Chạy lại smoke test của GĐ1: org, dataset, upload, search, API.
4. `docker compose restart ckan`: dữ liệu, file upload, đăng nhập và API token vẫn còn.
5. `docker compose down && docker compose up -d` (giữ volume): mọi thứ vẫn còn.
6. Xuất image: `docker save ckan-lakehouse:0.1.0 | gzip > ckan-lakehouse_0.1.0.tar.gz` (tarball **không** commit).

## Tiêu chí hoàn thành GĐ2
- [ ] Qua hết 6 bước kiểm thử.
- [ ] Bảng ánh xạ cấu hình đầy đủ.
- [ ] Đã xác minh biến secret (xem ⚠ ở trên) và ghi lại kết quả.
