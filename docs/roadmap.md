# Roadmap — CKAN 2.11 + theme riêng cho Lakehouse

> **Nguồn sự thật về tiến độ.** Agent: đọc file này đầu mỗi session; cập nhật checklist và decision log khi có thay đổi.

## Bối cảnh

Hai task được giao:
1. **Deploy CKAN from source.**
2. **Customize theme** cho CKAN.

**Phiên bản mục tiêu:** CKAN **2.11.6**, bản vá mới nhất của nhánh 2.11, phát hành 2026-08-26, tag git `ckan-2.11.6`. Dự án đã quay về bản này từ 2.12.0 ngày 2026-09-18 (Decision log).

Trong kiến trúc Lakehouse (báo cáo nội bộ, mục 11.10), CKAN là **data portal cho người dùng cuối**. Nó đứng cạnh OpenMetadata (catalog kỹ thuật) và publish các dataset tầng curated/Gold. Resource của dataset là link Trino JDBC hoặc file CSV do Airflow export qua CKAN API. Hiện trên cluster chỉ có bản stub `ckan/ckan-base:2.10` chưa nối Postgres, Solr hay Redis. Xem [cluster-context.md](cluster-context.md).

## Chiến lược: local trước, cluster sau

```mermaid
flowchart LR
  P1["GĐ1 — Local source install<br/>WSL2: CKAN 2.11.6 từ source<br/>+ Solr trong Docker Desktop<br/>→ phát triển theme"] --> P2["GĐ2 — Đóng gói<br/>Dockerfile FROM ckan-base:2.11.6<br/>+ theme, test docker compose"]
  P2 --> P3["GĐ3 — K8s lab công ty<br/>ns lakehouse, NodePort 30500<br/>Solr/Redis mới + Postgres dùng chung"]
```

Lý do chọn thứ tự này:
- Theme cần sửa rất nhiều vòng. Local cho vòng lặp tính bằng giây.
- Trên K8s, mỗi vòng mất 5–10 phút vì chưa có registry: build → `ctr import` lên 2 worker → rollout.
- Cluster dùng chung, sai là ảnh hưởng người khác.
- Chưa có kubeconfig.

Code theme là một package Python, **giữ nguyên** qua cả ba giai đoạn; chỉ cấu hình thay đổi.

## Trạng thái

### Giai đoạn 1 — Local source install + theme · [chi tiết](phase-1-local-source.md)

> **2026-09-18 — quay về CKAN 2.11.6** (Decision log). Toàn bộ repo đã chuyển sang 2.11.6: docs, script, CI của extension, theme.
>
> Theme đã viết lại cho classic, vì 2.11 không có Midnight Blue.
>
> Local đã chuyển xong:
> - User chạy `setup_step2_switch_to_2.11.sh`: CKAN 2.11.6 (`pip check` sạch), Solr `2.11-solr9`, DB lên head, có `admin`. Backup DB 2.12 nằm ở `~/ckan/backup`.
> - Agent dựng lại dữ liệu mẫu (thêm dataset `demo-outage-summary`); smoke test 22/22 qua.
> - Kiểm tra theme bằng ảnh chụp:
>   - debug và prod-like;
>   - 1366px và 400px;
>   - tương phản các cặp màu chính ≥ 5.5:1.
> - Sửa những gì phát hiện: link trong tiêu đề thẻ, chữ tiếng Việt bị ngắt giữa từ, vài chuỗi dịch; `ckan-shot.ini` thêm section logging (gotchas 6s–6u).
>
> **GĐ1 xong trên 2.11.6, sẵn sàng sang GĐ2.** Còn treo, không chặn GĐ2: bộ nhận diện thật (Q2) và test cần DB.
>
> *Lịch sử 2026-09-14, trên 2.12.0:* GĐ1 đã xong phần kỹ thuật. CKAN 2.12.0 cài từ source, Solr chạy, smoke test 17/17 qua. Đã chốt Q1 (`ckanext-lakehouse_theme`), Q2 (placeholder) và Q9 (Midnight Blue). Theme làm xong checklist và đã kiểm tra ở chế độ debug lẫn prod-like, trên desktop và mobile. `setup_step1_system.sh` đã được sửa: bỏ `git-core` vì gói này không còn trên 24.04, và cho phép chạy lại nhiều lần.

- [x] WSL2 Ubuntu 24.04 sẵn sàng (Python 3.12.3, systemd bật, docker CLI trong WSL)
- [x] **User tự chạy** `setup_step1_system.sh`: cài Postgres/Redis/libmagic, tạo DB `ckan_default`, tạo `~/ckan/etc` và `~/ckan/storage` (2026-09-14; giống nhau cho 2.11 và 2.12)
- [x] Scaffold `ckanext-lakehouse_theme` trong repo, `pip install -e`, bật plugin đứng đầu `ckan.plugins` (2026-09-14)
- [x] Ghi mọi key `ckan.ini` đã đổi vào bảng config ở [phase-2](phase-2-docker-packaging.md#bảng-ánh-xạ-cấu-hình) (2026-09-14, rà lại cho 2.11 ngày 2026-09-18)
- [x] Chuyển repo sang 2.11.6 (2026-09-18):
  - docs;
  - `setup_step2_switch_to_2.11.sh`;
  - CI extension dùng `ckan-dev:2.11`;
  - Q9 → classic;
  - theme viết lại cho classic, thêm helper `lakehouse_theme_recent_datasets`, unit test 9/9.
- [x] **User tự chạy** `setup_step2_switch_to_2.11.sh` ([phase-1 bước 1.1b](phase-1-local-source.md#bước-11b--chuyển-bản-cài-2120-sang-2116-user-tự-chạy-không-cần-sudo)) (2026-09-18). Script đã làm:
  - venv mới với CKAN **2.11.6** từ source;
  - sinh lại `ckan.ini` bằng 2.11, user tự điền mật khẩu DB;
  - Solr `ckan/ckan-solr:2.11-solr9`;
  - backup rồi xóa schema 2.12, sau đó `db init` + `db upgrade -p activity`;
  - tạo sysadmin `admin`.
- [x] Smoke test lại trên 2.11.6, qua API, 22/22 (2026-09-18):
  - `status_show` báo 2.11.6;
  - org `lakehouse-demo`;
  - dataset `demo-curated-orders` (CSV upload tải về khớp nội dung, URL `jdbc:trino://…`) và `demo-outage-summary`;
  - tìm kiếm `orders`, `đơn hàng`, `tags:gold`;
  - 10 trang web trả 200 và có marker của theme;
  - ô tìm kiếm header bị ẩn ở `/` và `/dataset/`.

  Token API tạm (`user token add`) đã thu hồi.
- [x] Kiểm tra theme classic bằng ảnh chụp headless Chrome (2026-09-18):
  - chế độ debug (:5000) và prod-like (:5002);
  - bề rộng 1366px và 400px;
  - trang chủ, `/dataset/`, resource Trino, `/organization/`;
  - tương phản các cặp màu chính từ 5.54:1 trở lên.

  Đã sửa:
  - link "Xem tất cả" bị lệch vì clearfix trong flex (gotchas 6t);
  - mô tả org bị ngắt giữa từ (6u);
  - "số bộ dữ liệu tìm thấy" / "Member" chưa dịch hoặc dịch vụng;
  - thiếu section logging trong `ckan-shot.ini` (6s).

### Giai đoạn 2 — Đóng gói Docker · [chi tiết](phase-2-docker-packaging.md)
- [ ] `.gitignore` (bỏ qua `.env`, `secrets.env`, `*.kubeconfig`, `ckan.ini`, `*.tar*`)
- [ ] `docker/Dockerfile` (FROM `ckan/ckan-base:2.11.6` + theme)
- [ ] `docker/compose.yaml` + `.env.example` (db, solr, redis, ckan)
- [ ] Build `ckan-lakehouse:<version>`, `docker compose up`, theme hiển thị đúng
- [ ] Kiểm tra sau khi restart vẫn còn dữ liệu, session và API token
- [ ] `docker save` ra tarball cho GĐ3

### Giai đoạn 3 — K8s lab công ty · [chi tiết](phase-3-k8s-deploy.md)
- [ ] Nhận kubeconfig (lưu **ngoài** repo)
- [ ] Audit read-only, ghi kết quả vào [cluster-context.md](cluster-context.md)
- [ ] Chốt với chủ cluster: xử lý stub `ckan`/`ckan-service`, tạo DB trên `postgres-service`
- [ ] Import image lên 2 worker (hoặc push registry nếu infra có)
- [ ] Apply manifest `k8s/`: Solr, Redis, CKAN (+ worker nếu cần)
- [ ] Verify tại http://10.1.117.91:30500 và tạo sysadmin
- [ ] Tích hợp: Airflow publish qua API, link Trino, đồng bộ OpenMetadata (sau go-live)

## Decision log

| Ngày | Quyết định | Lý do |
|---|---|---|
| 2026-09-11 | ~~CKAN 2.11.6 → CKAN 2.12.0~~ (**bị thay** bởi quyết định 2026-09-18) | 2.12.0 là bản stable mới nhất. Cài mới hoàn toàn, chưa cài bản 2.11 nào nên không cần nâng cấp |
| 2026-09-11 | Local dev dùng **WSL2 source install**, Solr chạy bằng Docker Desktop | Đúng nghĩa "from source". Image Solr của CKAN có sẵn schema |
| 2026-09-11 | Mọi thứ local đặt dưới `~/ckan/`, không dùng `/usr/lib/ckan`, `/etc/ckan` như docs gốc | Không cần sudo mỗi lần |
| 2026-09-11 | Code theme nằm trong repo này (`/mnt/c/...`), cài bằng `pip install -e` vào venv WSL | Quản lý phiên bản và sửa được từ VS Code phía Windows. Nếu chậm hoặc reloader không nhận thay đổi thì chuyển repo vào `~` |
| 2026-09-11 | Image production dùng `FROM ckan/ckan-base:<bản CKAN đang dùng>` + theme, hiện là `2.11.6` (ban đầu `2.12.0`). Không dùng Helm chart cộng đồng | Cluster đang quản lý bằng raw YAML + kubectl. Chart cộng đồng không chính thức |
| 2026-09-11 | Trên K8s **dùng lại `postgres-service`** với DB/user riêng. Solr và Redis dựng mới, riêng cho CKAN | Theo pattern đã có (OpenMetadata, mục 7.2.3) |
| 2026-09-11 | Expose bằng **NodePort 30500**, `ckan.site_url = http://10.1.117.91:30500` | Không có Ingress/LB. Giữ đúng cổng trong báo cáo |
| 2026-09-14 | ~~**Q9 → Midnight Blue**: `ckan.base_templates_folder = templates-midnight-blue`, `ckan.base_public_folder = public-midnight-blue`~~ (**bị thay** 2026-09-18: 2.11 không có Midnight Blue) | User chọn sau khi xem song song classic (:5000) và Midnight Blue (:5001) với cùng dữ liệu. Giao diện hiện đại hơn, là mặc định từ CKAN 3.0. Đổi lại: header không có ô tìm kiếm, nhiều chuỗi chưa có bản dịch `vi` (theme tự bù), extension bên thứ ba phải có template Midnight Blue (Q10) |
| 2026-09-14 | **Q1 → `ckanext-lakehouse_theme`**, plugin `lakehouse_theme`, chỉ chứa theme | Theo mặc định. Logic nghiệp vụ sau này (API, tích hợp Trino/Airflow) tách thành extension riêng |
| 2026-09-14 | **Q2 → placeholder**: logo dạng chữ, màu gom vào CSS custom properties | Chưa có bộ nhận diện chính thức. Khi có, chỉ cần thay file logo và vài biến màu |
| 2026-09-14 | Bản dịch theme: **commit `.po`, không commit `.mo`**; `.mo` build bằng `pybabel compile` ở local và trong Dockerfile | Tránh file nhị phân bị cũ so với `.po`. Babel có sẵn trong image vì là dependency của CKAN |
| 2026-09-14 | Nội dung footer (tên đơn vị, email, URL OpenMetadata, URL tài liệu Trino) là **config key `ckanext.lakehouse_theme.*`**, không hard-code | Đổi theo môi trường bằng env var trên K8s mà không phải build lại image |
| 2026-09-11 | Storage `local-path` RWO nên CKAN chạy **1 replica**, `strategy: Recreate`. Upload lưu trên PVC trước; MinIO để sau | Không có RWX. Từ 2026-09-18: 2.11 không có tầng `ckan.files.*`, nên MinIO phải qua extension upload S3 kiểu `IUploader` thay cho `ckanext-file-keeper-cloud` (chỉ 2.12); chọn khi làm (Q10) |
| 2026-09-18 | **Quay về CKAN 2.11.6** cho mọi thứ: source tag `ckan-2.11.6`, `ckan/ckan-base:2.11.6` (Python 3.10), `ckan/ckan-solr:2.11-solr9`, CI extension `ckan/ckan-dev:2.11` | User quyết định sau khi cân nhắc; chưa ghi lý do chi tiết. Đổi lại mất: Midnight Blue, tầng file `ckan.files.*`, `ckan db check`. 2.11.6 phát hành cùng ngày với 2.12.0 và có 8 bản vá bảo mật |
| 2026-09-18 | **Q9 → classic**. Theme viết lại block và CSS cho classic 2.11 (Bootstrap 5.1.3) | 2.11 chỉ nhận `templates` / `public`. Đặt Midnight Blue thì CKAN không khởi động (gotchas 6i) |
| 2026-09-18 | Trang chủ classic: hero có số dataset/tổ chức; dải dưới hero có cột trái "Bộ dữ liệu mới cập nhật" (helper `lakehouse_theme_recent_datasets`), cột phải org và nhóm nổi bật | Giữ lại những phần Midnight Blue có sẵn mà classic không có, bằng override ít block nhất (`featured_group`, `featured_organization`) |
| 2026-09-18 | Local chuyển bằng **cài lại sạch** (backup `pg_dump` → `db clean` → `db init`), không dùng `db downgrade` | Hạ schema cần code 2.12 và mật khẩu DB, mà `ckan.ini` đã mất mật khẩu. DB chỉ có dữ liệu mẫu, dựng lại được qua API (gotchas 6q) |
| 2026-09-18 | Đổi local cũng làm qua **script do user chạy** (`setup_step2_switch_to_2.11.sh`), không để agent làm | Có bước xóa venv/DB/volume Solr (agent bị chặn) và bước cần mật khẩu (DB, admin) |

## Câu hỏi còn mở

| # | Câu hỏi | Ai trả lời | Mặc định nếu chưa có câu trả lời |
|---|---|---|---|
| Q1 | ~~Tên theme/extension?~~ | User | **Đã chốt 2026-09-14:** `ckanext-lakehouse_theme`, plugin `lakehouse_theme` |
| Q2 | Bộ nhận diện: logo, màu, font, favicon, nội dung footer? | User / công ty | **Tạm dùng placeholder (2026-09-14)**, màu gom vào token `--lh-*`. Vẫn chờ bộ nhận diện thật |
| Q3 | "Deploy" có nghĩa là chạy trên cluster công ty cho mọi người dùng? | Người giao task | Có, nên GĐ3 là bắt buộc |
| Q4 | Có cần DataStore + xloader (preview dữ liệu, Data API)? | User | Không bật ở mốc đầu, thêm sau GĐ2 |
| Q5 | Có cần metadata schema riêng (ckanext-scheming), DCAT, SSO/LDAP? | User | Chưa |
| Q6 | Ngôn ngữ mặc định `vi` hay `en`? | User | `ckan.locale_default = vi`, cho phép chọn `en` |
| Q7 | Kubeconfig, quyền (`auth can-i`), registry nội bộ? | Infra | Chờ. Không có registry thì import tarball |
| Q8 | Ai sở hữu stub `ckan` trên cluster, được xóa hoặc thay không? | Chủ cluster | Không động vào khi chưa hỏi |
| Q9 | ~~Theme dựa trên classic hay Midnight Blue?~~ | User, sau khi xem thử cả hai ở GĐ1 | ~~Midnight Blue (2026-09-14)~~ → **classic (2026-09-18)**, vì 2.11 chỉ có classic. Cân nhắc lại nếu sau này lên 2.12+ |
| Q10 | Extension bên thứ ba cần dùng có hỗ trợ 2.11 không, bản nào? | Agent kiểm tra khi chốt Q4/Q5 | Kiểm tra README/CHANGELOG/CI của từng extension; ghim bản cuối còn hỗ trợ 2.11 |
