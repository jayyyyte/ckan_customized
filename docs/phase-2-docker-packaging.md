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

## Cấu trúc repo sau GĐ2 (đã dựng xong 2026-09-22)

```
ckan_customized/
├── ckanext-evntheme/                     # theme, copy vào image
├── docker/
│   ├── Dockerfile                        # FROM ckan/ckan-base:2.11.6 + xloader + theme
│   ├── compose.yaml                      # db, solr, redis, ckan, ckan-worker
│   ├── .env.example                      # commit; .env thật KHÔNG commit
│   ├── make-env.sh                       # sinh .env với mật khẩu/secret ngẫu nhiên
│   ├── worker-entrypoint.sh              # entrypoint của service ckan-worker
│   ├── docker-entrypoint.d/              # chạy trong container web sau prerun.py
│   │   ├── 10-plugin-migrations.sh       # db upgrade -p activity|tracking|evntheme
│   │   └── 20-xloader-token.sh           # API token cho XLoader
│   └── postgres-init/
│       └── 10-ckan-databases.sh          # role + 2 DB, chạy 1 lần khi tạo volume
├── .dockerignore
└── .gitignore
```

## Chạy ở local

```bash
bash docker/make-env.sh                    # sinh docker/.env (chỉ chạy một lần)
cd docker && docker compose up -d --build  # lần đầu ~2 phút kể cả pull
docker compose ps                          # ckan phải healthy
```

Cổng mặc định là 5000. Nếu `ckan run` của GĐ1 đang chiếm cổng đó thì sửa **cả hai** key trong `.env`: `CKAN_PORT` và cổng trong `CKAN_SITE_URL` (bẫy 10). Bản kiểm thử 2026-09-22 chạy ở 5003.

Dữ liệu demo và DataStore:

```bash
docker compose exec ckan ckan -c /srv/app/ckan.ini evntheme seed-demo
docker compose exec ckan ckan -c /srv/app/ckan.ini xloader submit all
docker compose logs -f ckan-worker          # theo dõi job
```

## Dockerfile — xem [docker/Dockerfile](../docker/Dockerfile)

Bốn điểm quyết định, đều đã kiểm chứng trong image:

1. **`USER root` khi cài, `USER ckan` khi chạy** (bẫy 12).
2. **Extension bên thứ ba cài `-e` từ source.** Trong image, `ckanext.__path__` là `['/srv/app/src/ckan/ckanext', '/srv/app/src/ckanext-evntheme/ckanext']` — không có `site-packages`, nên wheel sẽ vô hình (bẫy 6ak). XLoader ghim tag `2.5.0` qua `ARG XLOADER_VERSION`, cài kèm `requirements.txt` của đúng tag đó. `pip3 check` chạy ngay trong build: bản 2.5.0 không xung đột với requirements của CKAN 2.11.6 trên Python 3.10.
3. **`pybabel compile` lúc build**, vì `.mo` không commit; `.dockerignore` loại luôn `.mo` của bản local để không dính bản cũ. CSS đã commit sẵn nên image không cần Node.
4. **`ckan config-tool` ghi `ckan.plugins` vào ini lúc build.** `prerun.py` chỉ chạy ở container web, mà `ckan.plugins` lại được đọc trước khi nạp plugin nên `envvars` không tự bật plugin được. Không có bước này thì `ckan-worker` chạy CKAN trần (bẫy 15b).

Build, và lệnh kiểm tra lại mỗi khi đổi base tag:

```bash
docker build -f docker/Dockerfile -t ckan-lakehouse:0.1.0 .      # chạy từ gốc repo
docker run --rm ckan/ckan-base:2.11.6 sh -c 'id; python3 -V; env | grep -E "APP_DIR|SRC_DIR|CKAN_INI"'
```

Image `0.1.0` nặng **1.98 GB**. `docker save | gzip -1` ra **537 MiB** (562.6 MB): đây là khối lượng phải `ctr import` lên từng worker ở GĐ3. Đã tập dượt trên kind ngày 2026-09-25: `ctr -n k8s.io images import` nhận tệp này bình thường, dù Docker Desktop dùng containerd image store (xuất định dạng OCI index).

## compose.yaml — xem [docker/compose.yaml](../docker/compose.yaml)

| Service | Vai trò | Tương ứng ở GĐ3 |
|---|---|---|
| `db` | `postgres:16-alpine`, init tạo 2 role + 2 DB | `postgres-service` dùng chung (chỉ thêm DB) |
| `solr` | `ckan/ckan-solr:2.11-solr9`, không publish cổng | Deployment + Service `ckan-solr` |
| `redis` | `redis:7-alpine` | Deployment + Service `ckan-redis` |
| `ckan` | image tự build, publish `CKAN_PORT` | Deployment 1 replica + NodePort 30500 |
| `ckan-worker` | cùng image, chạy `ckan jobs worker` | Deployment riêng, không cần Service, **không gắn PVC** (XLoader tải file qua HTTP) |

Các manifest tương ứng nằm trong [k8s/base/](../k8s/base), xem [phase-3 §3.5](phase-3-k8s-deploy.md#35-manifest--k8s).

- Các URL kết nối (`CKAN_SQLALCHEMY_URL`, hai URL DataStore, `CKANEXT__XLOADER__JOBS_DB__URI`) được **ghép trong compose** từ mật khẩu trong `.env`, để mỗi mật khẩu chỉ nằm một chỗ. Ở GĐ3 thì viết thẳng URL vào Secret.
- `ckan-worker` **không** chạy `prerun.py`: container web mới là nơi `db init` và chạy migration. `worker-entrypoint.sh` chỉ đồng bộ `ckan.plugins` từ env rồi `exec ckan jobs worker`.
- `depends_on` của worker chờ `ckan` **healthy**, nên schema chắc chắn đã sẵn sàng.
- Healthcheck: `wget` cho CKAN (image có sẵn), `curl` cho Solr, `redis-cli ping` cho Redis, `pg_isready -d ckan_default` cho Postgres — có `-d` để chờ cả script init chứ không chỉ chờ server.

## DataStore + XLoader trong image (Q4)

- `CKAN__PLUGINS` có `datastore xloader datatables_view`, giống local.
- `postgres-init/10-ckan-databases.sh` tạo role `ckan_default` (ghi) và `datastore_default` (chỉ đọc) cùng hai DB, **đều thuộc sở hữu `ckan_default`**. Nhờ vậy `datastore set-permissions` mà `prerun.py` chạy bằng chính user ghi vẫn thành công, không cần superuser (bẫy 15e).
- `CKANEXT__XLOADER__SITE_URL=http://ckan:5000`: worker ở container khác không giải được `localhost:5000` trong payload job (bẫy 15c).
- `CKANEXT__XLOADER__JOBS_DB__URI` trỏ vào DB CKAN thay cho file SQLite `/tmp` mặc định, để web và worker dùng chung nhật ký job.
- API token của XLoader: `20-xloader-token.sh` thu hồi token `xloader-container` cũ rồi tạo token mới mỗi lần start, hoặc dùng `CKANEXT__XLOADER__API_TOKEN` nếu được đặt. Chỉ container web cần token này — nó đi kèm payload job sang worker.

## `.env.example` — xem [docker/.env.example](../docker/.env.example)

`bash docker/make-env.sh` sinh `.env` với mật khẩu và secret ngẫu nhiên (`secrets.token_urlsafe`, chỉ gồm ký tự an toàn trong URL nên không phải percent-encode — bẫy 6e). Script không ghi đè `.env` đã có.

⚠ **Đã xác minh xong (2026-09-22): secret truyền bằng biến môi trường có tác dụng.**

- `start_ckan.sh` vẫn sinh `SECRET_KEY` ngẫu nhiên vào `ckan.ini` mỗi lần start, và giá trị trong ini **khác** giá trị env.
- Nhưng `envvars` là `IConfigurer`, chạy trong `update_config()` trước bước validate, nên env đè lên ini.
- Kiểm chứng: tạo API token, đăng nhập lấy cookie phiên, `docker compose restart ckan` → **cả token lẫn cookie vẫn dùng được** (HTTP 200).
- `SECRET_KEY` và `WTF_CSRF_SECRET_KEY` nằm trong config declaration nên `envvars` giữ nguyên chữ HOA. Key không được khai báo sẽ bị hạ thành chữ thường và trượt.

Một bẫy khác phát hiện khi test: **để trống một biến khác với không đặt nó**. `CKANEXT__XLOADER__API_TOKEN=` làm CKAN chết vì option đó khai báo `not_missing` (bẫy 15a) — trong `.env` phải comment cả dòng.

## Bảng ánh xạ cấu hình

Mỗi key `ckan.ini` đã chỉnh ở local đều có biến env tương ứng. Cột "Env" là tên biến trong `docker/.env` hoặc trong `compose.yaml`.

| Key `ckan.ini` | Local (GĐ1) | Env (GĐ2/3) | Giá trị K8s | Secret? |
|---|---|---|---|---|
| `sqlalchemy.url` | `postgresql://ckan_default:***@localhost/ckan_default` | `CKAN_SQLALCHEMY_URL` (compose ghép từ `CKAN_DB_PASSWORD`) | `postgresql://ckan_default:***@postgres-service.lakehouse:5432/ckan_default` | ✔ |
| `solr_url` | `http://127.0.0.1:8983/solr/ckan` | `CKAN_SOLR_URL` | `http://ckan-solr:8983/solr/ckan` | |
| `ckan.redis.url` | `redis://localhost:6379/0` | `CKAN_REDIS_URL` (compose dùng db 1) | `redis://ckan-redis:6379/0` | |
| `ckan.site_url` | `http://localhost:5000` | `CKAN_SITE_URL` | `http://10.1.117.91:30500` | |
| `ckan.storage_path` | `/home/tlinh/ckan/storage` | *(image đặt sẵn `/var/lib/ckan`)* | `/var/lib/ckan` trên PVC | |
| `ckan.plugins` | `evntheme activity tracking datastore xloader text_view image_view datatables_view` | `CKAN__PLUGINS` (thêm `envvars` ở cuối) | giống GĐ2 | |
| `ckan.base_templates_folder` / `ckan.base_public_folder` | mặc định | *(không đặt)* | mặc định | |
| `ckan.locale_default` / `ckan.locales_offered` | `vi` / `vi en` | `CKAN__LOCALE_DEFAULT` / `CKAN__LOCALES_OFFERED` | giống local | |
| `ckan.site_title` / `ckan.site_description` | `Cổng dữ liệu EVN` / `Chia sẻ dữ liệu dùng chung toàn Tập đoàn` | `CKAN__SITE_TITLE` / `CKAN__SITE_DESCRIPTION` | giống local | |
| `ckan.favicon` | `/evntheme/images/favicon.svg` | `CKAN__FAVICON` | giống local | |
| `ckan.site_logo` | mặc định (theme dùng placeholder) | `CKAN__SITE_LOGO` | đặt khi có logo thật (Q2) | |
| `ckan.views.default_views` | `image_view datatables_view` | `CKAN__VIEWS__DEFAULT_VIEWS` | giống local | |
| `ckan.max_resource_size` | `10` | `CKAN_MAX_UPLOAD_SIZE_MB` | theo dung lượng PVC | |
| `ckan.datastore.write_url` | `postgresql://ckan_default:***@localhost/datastore_default` | `CKAN_DATASTORE_WRITE_URL` | DB `datastore_default` trên `postgres-service` | ✔ |
| `ckan.datastore.read_url` | `postgresql://datastore_default:***@localhost/datastore_default` | `CKAN_DATASTORE_READ_URL` | role chỉ đọc trên cùng DB | ✔ |
| `ckanext.xloader.api_token` | token của `admin` | `CKANEXT__XLOADER__API_TOKEN` (bỏ trống → entrypoint tự tạo) | Secret, hoặc để entrypoint tự tạo | ✔ |
| *(mới ở GĐ2)* `ckanext.xloader.site_url` | không cần | `CKANEXT__XLOADER__SITE_URL` | `http://ckan-service:5000` | |
| *(mới ở GĐ2)* `ckanext.xloader.jobs_db.uri` | mặc định SQLite | `CKANEXT__XLOADER__JOBS_DB__URI` | DB CKAN trên `postgres-service` | ✔ |
| `ckanext.evntheme.domain_groups` | 5 group | `CKANEXT__EVNTHEME__DOMAIN_GROUPS` | tên group thật trên cluster | |
| `ckanext.evntheme.openmetadata_url` | `http://10.1.117.91:30858` | `CKANEXT__EVNTHEME__OPENMETADATA_URL` | `http://10.1.117.91:30858` (`k8s/overlays/lab/config.env`) | |
| `ckanext.evntheme.*` khác | mặc định trong plugin | `CKANEXT__EVNTHEME__<KEY>` | đặt khi có thông tin thật (Q2) | |
| `SECRET_KEY`, `WTF_CSRF_SECRET_KEY`, `api_token.jwt.*.secret` | do `generate config` sinh | `CKAN___SECRET_KEY`, `CKAN___WTF_CSRF_SECRET_KEY`, `CKAN___API_TOKEN__JWT__ENCODE__SECRET` / `__DECODE__SECRET` | Secret | ✔ |
| `debug` | `true` | *(không đặt)* | `false` | |
| *(mới ở GĐ3)* tham số uWSGI `--max-fd` | không có uWSGI | `EXTRA_UWSGI_OPTS` (compose không cần: Docker cấp 1048576 fd) | `--max-fd 65536` trong `k8s/base/config.env` (bẫy 21a) | |

## Kiểm thử — kết quả 2026-09-22

| # | Bước | Kết quả |
|---|---|---|
| 1 | `docker compose up -d --build`, `docker compose ps` | 4/4 service có healthcheck đều **healthy**, worker chạy |
| 2 | Theme đúng ở mọi trang, font tự host | 24/24 kiểm tra qua: 7 trang + 4 tab trả 200, có marker của theme, **không** gọi Google Fonts, `.woff2` và favicon trả 200, tiếng Việt đúng. Ảnh chụp 1440px: trang chủ và tab Xem trước khớp bản local |
| 3 | Smoke test GĐ1: org, dataset, upload, search, API | `status_show` báo 2.11.6; `package_search` ra kết quả với truy vấn tiếng Việt; `organization_list` đủ 9 đơn vị; file CSV upload tải về đúng nội dung; `datastore_search` trả JSON |
| 4 | `docker compose restart ckan` | Dữ liệu, file upload, **cookie phiên và API token cũ** đều còn (xem mục ⚠) |
| 5 | `docker compose down && up -d` (giữ volume) | 12 dataset, 9 tổ chức, 10 bảng DataStore còn nguyên; tab Xem trước vẫn 200 |
| 6 | `docker save \| gzip -1` | 537 MiB |

Riêng DataStore: `seed-demo` rồi `xloader submit all` → **10/10 resource CSV upload đã vào DataStore**, `datastore_active` đúng 10, tab Xem trước hiện bảng thật. 19 resource còn lại là link ngoài giả lập (`data.evn.example`) hoặc định dạng XLoader không nhận (JSON/GeoJSON/PDF), hỏng đúng như ở local. Role chỉ đọc `SELECT` được `_table_metadata` nhưng `CREATE TABLE` bị từ chối: phân quyền DataStore đúng.

## Tiêu chí hoàn thành GĐ2
- [x] Qua hết 6 bước kiểm thử.
- [x] Bảng ánh xạ cấu hình đầy đủ.
- [x] Đã xác minh biến secret và ghi lại kết quả (mục ⚠ ở trên, bẫy 11).
