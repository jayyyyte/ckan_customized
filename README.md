# CKAN Lakehouse Portal — Cổng dữ liệu EVN

Data portal cho kiến trúc Lakehouse, xây trên **CKAN 2.11.6** cài từ source, với theme riêng **`ckanext-evntheme`**. Lộ trình 3 giai đoạn local → Docker → K8s: **GĐ1 (local WSL2) và GĐ2 (đóng gói image) đã xong**. GĐ3 (deploy K8s) đã có manifest và đã tập dượt trọn quy trình trên kind; còn chờ kubeconfig của cluster công ty. Xem chi tiết đầy đủ ở [docs/roadmap.md](docs/roadmap.md).

> File này là hướng dẫn nhanh để **chạy và dùng** project. Muốn hiểu bối cảnh, quyết định kỹ thuật hay đang làm gì tiếp theo, đọc [docs/roadmap.md](docs/roadmap.md) trước.

## Yêu cầu

- Windows 11 + **WSL2 Ubuntu 24.04** (user tự tạo, Python ≥ 3.10)
- **Docker Desktop** với WSL Integration bật cho Ubuntu (chạy Solr)
- PostgreSQL và Redis cài trong WSL (không dùng container, xem script bước 1)

## Cài đặt lần đầu (chỉ chạy một lần)

Cả ba script đều tự chạy trong **WSL**, không phải PowerShell. Script yêu cầu `sudo` thì Claude/agent không tự chạy được — bạn tự mở terminal WSL và chạy.

```bash
# 1. Gói hệ thống: Postgres, Redis, libmagic... (cần sudo)
bash /mnt/c/Users/Tlinh/ckan_customized/setup_step1_system.sh

# 2. Cài CKAN 2.11.6 từ source + config + Solr + DB + theme evntheme (không cần sudo)
bash /mnt/c/Users/Tlinh/ckan_customized/setup_step2_switch_to_2.11.sh

# 3. (Tùy chọn) DataStore + XLoader, để bật tab Xem trước / Thử API (cần sudo)
bash /mnt/c/Users/Tlinh/ckan_customized/setup_step3_datastore.sh
```

Script 2 sẽ mở `nano` để bạn tự điền mật khẩu DB vào `~/ckan/etc/ckan.ini`, và hỏi mật khẩu khi tạo sysadmin `admin`. Chi tiết từng bước: [docs/phase-1-local-source.md](docs/phase-1-local-source.md).

## Chạy hằng ngày

```bash
# 1. Bật Solr (nếu container chưa chạy)
docker start ckan-solr

# 2. Kích hoạt virtualenv
source ~/ckan/default/bin/activate

# 3. Chạy CKAN (reloader tự bật — sửa code/template không cần restart)
ckan -c ~/ckan/etc/ckan.ini run
```

Mở trình duyệt: **http://localhost:5000**

Windows không mở được `localhost:5000`? Chạy `ckan ... run -H 0.0.0.0` rồi vào bằng IP của WSL.

### Xem giao diện kiểu production (không debug toolbar)

```bash
ckan -c ~/ckan/etc/ckan-shot.ini run -p 5002
```

→ **http://localhost:5002**

## Dữ liệu demo

```bash
ckan -c ~/ckan/etc/ckan.ini evntheme seed-demo            # 5 miền, 9 đơn vị, 12 dataset, 10 danh mục chuẩn
ckan -c ~/ckan/etc/ckan.ini evntheme seed-demo --reset    # xóa sạch rồi nạp lại
```

Đăng nhập bằng tài khoản `admin` đã tạo ở bước cài đặt.

## Chạy bằng Docker (GĐ2)

Toàn bộ portal (Postgres + Solr + Redis + CKAN + worker XLoader) chạy bằng `docker compose`, dùng đúng image sẽ deploy lên K8s:

```bash
bash docker/make-env.sh                     # sinh docker/.env, chỉ chạy một lần
cd docker && docker compose up -d --build   # lần đầu ~2 phút
docker compose ps                           # ckan phải healthy
```

Mở **http://localhost:5000** (mật khẩu sysadmin nằm trong `docker/.env`). Nếu `ckan run` của GĐ1 đang chiếm cổng 5000, sửa `CKAN_PORT` **và** cổng trong `CKAN_SITE_URL` của `docker/.env`.

```bash
docker compose exec ckan ckan -c /srv/app/ckan.ini evntheme seed-demo    # dữ liệu demo
docker compose exec ckan ckan -c /srv/app/ckan.ini xloader submit all    # nạp CSV vào DataStore
docker compose logs -f ckan-worker                                       # theo dõi job XLoader
docker compose down                                                      # dừng, vẫn giữ dữ liệu
docker compose down -v                                                   # xóa sạch cả volume
```

Chi tiết cấu hình, bảng ánh xạ env var và kết quả kiểm thử: [docs/phase-2-docker-packaging.md](docs/phase-2-docker-packaging.md).

## Triển khai Kubernetes (GĐ3)

Manifest dùng kustomize: `k8s/base` (chung) + `k8s/overlays/lab` (cluster công ty) / `k8s/overlays/kind` (tập dượt local). Mọi script bắt buộc `--context` để không chạy nhầm cluster.

Tập dượt trên kind: cluster riêng `ckan-rehearsal`, portal ở **http://localhost:30500**.

```bash
kind create cluster --config k8s/overlays/kind/kind-cluster.yaml   # rồi use-context lại context cũ
# đưa image lên 2 worker: docs/phase-3-k8s-deploy.md §3.10
bash k8s/scripts/make-secrets.sh kind
kubectl --context kind-ckan-rehearsal apply -f k8s/overlays/kind/namespace.yaml
kubectl --context kind-ckan-rehearsal apply -k k8s/overlays/kind
bash k8s/scripts/prepare-postgres.sh --context kind-ckan-rehearsal kind --apply
bash k8s/overlays/kind/smoke-test.sh
kind delete cluster --name ckan-rehearsal                          # dọn
```

Cluster công ty (dùng chung, **mọi lệnh ghi cần xác nhận**): làm đúng thứ tự audit → DB → image → dry-run → apply ở [docs/phase-3-k8s-deploy.md](docs/phase-3-k8s-deploy.md#36-triển-khai--kiểm-tra-trên-cluster-công-ty).

## Cấu trúc repo

| Đường dẫn | Nội dung |
|---|---|
| `docs/` | Roadmap, tài liệu từng giai đoạn, gotchas — xem [mục lục](docs/README.md) |
| `ckanext-evntheme/` | Theme "Cổng dữ liệu EVN" — xem [README](ckanext-evntheme/README.md) |
| `docker/` | Dockerfile, compose, entrypoint và script sinh `.env` cho GĐ2 |
| `k8s/` | Manifest kustomize (base + overlay `lab`/`kind`), script audit / sinh secret / tạo DB, smoke test cho GĐ3 |
| `setup_step*.sh` | Script cài đặt/chuyển đổi môi trường local (user tự chạy) |
| `~/ckan/` (ngoài repo, trong WSL) | venv, source CKAN, config `ckan.ini`, storage upload |

Code CKAN gốc và `ckan.ini` (chứa mật khẩu) nằm ngoài repo này, dưới `~/ckan/` trong WSL — không commit.

## Sau khi sửa theme

```bash
cd /mnt/c/Users/Tlinh/ckan_customized/ckanext-evntheme
npm run build:css              # sau khi sửa SCSS — bắt buộc commit lại CSS đã build
pybabel compile -d ckanext/evntheme/i18n -D ckanext-evntheme   # sau khi sửa .po
```

Chi tiết phát triển theme (cấu trúc code, cách thêm facet/tab, quy ước dịch...): [ckanext-evntheme/README.md](ckanext-evntheme/README.md).

## Test

```bash
cd ckanext-evntheme
python -m pytest -o addopts="" -p no:ckan -p no:ckan_fixtures ckanext/evntheme/tests/test_units.py   # local, không cần DB
```

`test_app.py` cần DB `ckan_test`, chỉ chạy trong CI (`.github/workflows/evntheme.yml`).

## Gặp lỗi?

Tra [docs/gotchas.md](docs/gotchas.md) trước — hầu hết lỗi từng gặp (Solr schema sai, `ckan.ini` thiếu section logging, `db check` không có ở 2.11...) đã ghi cách xử lý ở đó.

## Quy tắc khi đóng góp

- Không commit `.env`, `ckan.ini`, `*.kubeconfig`, `secrets.env` / `*-secrets.env`, file `.mo` đã build.
- Cluster K8s dùng chung với đồng nghiệp — không tự tạo/sửa/xóa tài nguyên khi chưa xác nhận. Xem [docs/phase-3-k8s-deploy.md](docs/phase-3-k8s-deploy.md) và [CLAUDE.md](CLAUDE.md).
- Xong việc gì → tick checklist trong [docs/roadmap.md](docs/roadmap.md); quyết định mới → thêm vào Decision log; gặp bẫy mới → thêm vào [docs/gotchas.md](docs/gotchas.md).
