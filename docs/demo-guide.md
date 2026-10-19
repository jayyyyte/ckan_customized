# Hướng dẫn demo GĐ4 — phân quyền người dùng và OpenMetadata

Kịch bản demo trên **bản cài local** (http://localhost:5000), khoảng 20–25 phút. Có thể demo hai đầu việc:
1. **Org, group, dataset và phân quyền**: cùng một portal, mỗi người thấy và làm được những việc khác nhau.
2. **OpenMetadata**: bảng của Lakehouse tự thành dataset, cùng tab "Danh mục kỹ thuật" lấy dữ liệu trực tiếp.

Mọi người và mọi bảng trong demo đều **hư cấu**: user ở `ckanext-lakehouse/ckanext/lakehouse/demo/portal.yaml`, bảng ở `tools/openmetadata/sample-snapshot.json`. Thiết kế: [phase-4-content-openmetadata.md](phase-4-content-openmetadata.md).

---

## 0. Chuẩn bị (5 phút trước khi demo)

Chạy trong terminal WSL:

```bash
cd /mnt/c/Users/Tlinh/ckan_customized
source ~/ckan/default/bin/activate

# 1. Solr local (Docker Desktop phải đang chạy)
docker start ckan-solr

# 2. OpenMetadata giả lập; để nguyên cửa sổ này hoặc thêm & ở cuối
python3 tools/openmetadata/om_mock.py tools/openmetadata/sample-snapshot.json --port 8585 --token dev-token &

# 3. CKAN, chạy trong một terminal riêng
ckan -c ~/ckan/etc/ckan.ini run -H 0.0.0.0

# 4. Đồng bộ một lần cho chắc dữ liệu mới nhất (thường báo "5 unchanged")
ckan -c ~/ckan/etc/ckan.ini lakehouse om sync
```

**Mật khẩu user demo.** Mật khẩu được sinh **một lần** khi user được tạo (ngày 06/10). Xem bằng:

```bash
column -s, -t < ~/ckan/backup/lakehouse-demo-users-20261006-092506.csv
```

> Vì sao lệnh `bootstrap ... --credentials ~/ckan/backup/users.csv` hôm nay báo `Nothing to change.` và không tạo file? Vì cả 9 user đã tồn tại. Script chỉ ghi mật khẩu cho **user mới tạo**, và không bao giờ đổi mật khẩu user đã có. Muốn đặt lại mật khẩu cho một user: đăng nhập `admin`, mở `/user/edit/<tên>`, nhập mật khẩu mới, rồi nhập **mật khẩu của chính admin** ở ô "Sysadmin Password" để xác nhận.

**Mẹo trình bày:** mở mỗi user trong **một cửa sổ ẩn danh riêng** (Chrome: mỗi profile, hoặc Chrome + Edge + Firefox). Cookie đăng nhập tách nhau, nên có thể đặt các cửa sổ cạnh nhau để so sánh.

---

## 1. Phần A — Người dùng và phân quyền (10 phút)

### A1. Ai đang có trong hệ thống (đăng nhập `admin`)

| Mở | Thấy gì | Nói gì |
|---|---|---|
| `/ckan-admin` | 3 sysadmin: `admin`, **Quản trị Cổng dữ liệu** (`quantri-portal`), `default` | Trang này **chỉ liệt kê sysadmin**. `quantri-portal` là user duy nhất file khai báo nâng lên sysadmin. `default` là **site user nội bộ** của CKAN (trùng tên `ckan.site_id`), các job hệ thống dùng nó; **không xóa** |
| `/user/` | Toàn bộ **11 tài khoản** | 9 user tạo từ file khai báo, cộng `admin` và `default`. Chỉ sysadmin xem được trang này (khách: 403), vì đã đặt `public_user_details = false` |
| `/organization/members/evnnpc` | `npc-quantri` là **Quản trị**, `npc-bientap` là **Biên tập** | Vai trò trong đơn vị được khai báo ở `portal.yaml`, không ai phải bấm tay |
| `/group/members/ky-thuat-an-toan` | `mien-ktat` là Quản trị, `ktsx-bientap` là Thành viên | Group = "miền dữ liệu". Quyền ở group chỉ là gắn/gỡ dataset vào miền, **không** cho sửa dataset |

Nói thêm: toàn bộ cấu trúc này nằm trong **một file YAML**. Sửa file rồi chạy lại lệnh là cập nhật được, chạy bao nhiêu lần cũng an toàn (hôm nay chạy lại → `Nothing to change.`).

### A2. Mỗi người thấy gì

Có 19 dataset, trong đó **5 dataset private** đến từ OpenMetadata. Mở `/dataset/` bằng từng tài khoản:

| Tài khoản | Vai trò | Số dataset thấy | Dataset private thấy được |
|---|---|---|---|
| (khách, chưa đăng nhập) | — | **14** | không |
| `nguoidung-xem` | đã đăng nhập, không thuộc đơn vị nào | **14** | không |
| `npc-bientap` | biên tập EVNNPC | 14 | không (EVNNPC chưa có dataset private) |
| `a0-thanhvien` | **thành viên** Trung tâm Điều độ (A0) | **16** | 2 bảng vận hành của A0 |
| `kd-bientap` | biên tập Ban Kinh doanh | 16 | 2 bảng kinh doanh |
| `npc-quantri` | quản trị EVNNPC + **thành viên** Ban KD | 16 | 2 bảng kinh doanh (chỉ đọc) |
| `ktsx-bientap` | biên tập Ban KTSX **và** A0 | **17** | 3 bảng (trạm biến áp + 2 bảng vận hành) |
| `admin`, `quantri-portal` | sysadmin | **19** | cả 5 |

Điểm nhấn: khách mở thẳng URL của dataset private (ví dụ `/dataset/om-trino_lakehouse-iceberg_curated-van_hanh-curated_outage_summary`) sẽ nhận **404**, không phải 403. CKAN cố ý không xác nhận là dataset đó có tồn tại.

### A3. Thấy ≠ được sửa

Mở dataset **"Tổng hợp sự cố mất điện theo ngày"** (badge **Riêng tư**) bằng hai cửa sổ:

| | `a0-thanhvien` (thành viên) | `ktsx-bientap` (biên tập) |
|---|---|---|
| Xem trang | ✓ | ✓ |
| Nút **Quản lý** ở góc phải | **không có** | **có** |
| Mở `/dataset/edit/<tên>` | 403 | form sửa |

Tương tự với `npc-quantri`: thấy bảng doanh thu của Ban Kinh doanh nhưng **không** có nút Quản lý, vì ở Ban KD người này chỉ là `member`.

### A4. Quản trị đơn vị và quản trị miền

- `npc-quantri`: mở `/organization/member_new/evnnpc` → **thêm được** thành viên vào EVNNPC. Mở `/organization/member_new/ban-kinh-doanh` → **403**.
- `mien-ktat`: mở `/group/members/ky-thuat-an-toan` → quản lý được thành viên của miền, nhưng **không** sửa được dataset nào.
- `nguoidung-xem`: mở `/organization/new` hoặc `/group/new` → **403**, vì đã tắt `user_create_organizations` / `user_create_groups`. Đăng xuất rồi mở `/user/register` → cũng bị chặn (`create_user_via_web = false`): tài khoản chỉ do quản trị tạo.

### A5. Công bố một dataset (kết nối sang phần B)

1. `ktsx-bientap` → dataset "Tổng hợp sự cố…" → **Quản lý** → mục *Hiển thị* chọn **Công khai** → Lưu.
2. Cửa sổ `nguoidung-xem` (hoặc khách) tải lại `/dataset/` → thấy **15** dataset, có thêm bảng sự cố.
3. Terminal: `ckan -c ~/ckan/etc/ckan.ini lakehouse om sync` → vẫn `5 unchanged`. **Đồng bộ không đổi lại quyết định công bố của biên tập viên.**

(Muốn trả về như cũ: Quản lý → Riêng tư.)

---

## 2. Phần B — OpenMetadata (10 phút)

### B1. Kết nối và phạm vi

```bash
ckan -c ~/ckan/etc/ckan.ini lakehouse om check
```

Cần chỉ ra:
- `OpenMetadata 1.6.2`, **7 bảng**, **6 trong phạm vi** (`om.include = trino_lakehouse.iceberg_curated.*`). Bảng raw `iceberg_raw...` bị loại.
- Bảng *Owner teams*: `KinhDoanh → ban-kinh-doanh`… và `DataPlatform → (not mapped)`. Đây chính là phần ánh xạ khai báo trong `portal.yaml` (`openmetadata: teams/domains`).
- *Organizations the sync would use*: 1 bảng `(none: skipped)`. Bảng không có đơn vị nhận thì **không** được đưa lên.

### B2. Đồng bộ

```bash
ckan -c ~/ckan/etc/ckan.ini lakehouse om sync --dry-run   # xem trước, không ghi
ckan -c ~/ckan/etc/ckan.ini lakehouse om sync             # "5 unchanged": chỉ ghi khi có thay đổi
```

Ý cần nói:
- Lần đầu tạo 5 dataset; các lần sau không ghi gì nếu OpenMetadata không đổi, nên **không sinh "nhật ký" rác**.
- Trên cụm K8s, lệnh này chạy tự động **mỗi giờ** (CronJob `ckan-om-sync`, phút 40).
- Dataset mới luôn **private**; đơn vị sở hữu quyết định có công bố hay không (A5).

### B3. Dataset sinh từ OpenMetadata (đăng nhập `ktsx-bientap`)

Mở `/dataset/om-trino_lakehouse-iceberg_curated-van_hanh-curated_outage_summary`:

| Chỗ | Lấy từ OpenMetadata |
|---|---|
| Tiêu đề, mô tả | `displayName`, `description` |
| Đơn vị "Trung tâm Điều độ…" | owner team `DieuDo` |
| Sidebar: Miền dữ liệu "Kỹ thuật – An toàn", **Bảng nguồn** | domain `VanHanh`, FQN của bảng |
| KPI **Số bản ghi 1.284.530**, **Hệ thống nguồn Trino** | profile mới nhất, service |
| Tệp "Trino: …" → nút **Kết nối** | sinh link `jdbc:trino://…/iceberg_curated/van_hanh` |
| Thẻ `DataLayer.Gold` | tag (tag `Tier` chuyển thành thông tin Tier) |

### B4. Tab "Danh mục kỹ thuật"

Bấm tab **Danh mục kỹ thuật**. Tab tải sau, nên OpenMetadata chậm cũng không làm chậm trang:
- **Thông tin kỹ thuật**: đơn vị phụ trách, Tier1, số dòng "đo 15 giờ trước", 412 truy vấn tuần qua.
- **Kiểm định chất lượng**: Đạt 3 / **Không đạt 1**. Test lỗi `province_in_code_list` luôn nằm đầu.
- **Dữ liệu đến từ đâu và đi về đâu** (lineage):
  - *Được tạo từ*: bảng raw + pipeline Airflow `curated_outage_summary`;
  - *Được dùng bởi*: dashboard Superset + bảng `grid_loss_monthly`. Bấm vào `grid_loss_monthly` → mở **trang CKAN** của bảng đó (vì nó cũng đã được đồng bộ và người xem có quyền); các nút khác trỏ sang OpenMetadata.
- **Các cột**: tên, kiểu, mô tả.

So sánh: mở cùng dataset bằng `a0-thanhvien` → vẫn xem được tab. Dataset tạo tay (ví dụ một dataset demo của EVNNPC) thì **không có** tab này.

### B5. Chỉnh tay không bị đồng bộ ghi đè

1. `ktsx-bientap` → Quản lý dataset sự cố → thêm thẻ `do-tin-cay` → Lưu.
2. `ckan ... lakehouse om sync` → `5 unchanged`.
3. Tải lại trang: thẻ `do-tin-cay` **vẫn còn** cạnh `DataLayer.Gold`.

Nguyên tắc: đồng bộ chỉ quản lý những gì nó tự thêm (tiêu đề, đơn vị, tag/miền từ OpenMetadata, các thông tin kỹ thuật). Phần còn lại thuộc về biên tập viên.

### B6. Khi OpenMetadata ngừng hoạt động

```bash
pkill -f "[o]m_mock\.py"                                     # tắt OpenMetadata giả
redis-cli --scan --pattern "ckanext-lakehouse:om:*" | xargs -r redis-cli del   # bỏ cache để thấy ngay
```

- Tải lại tab "Danh mục kỹ thuật": khung đỏ báo *"Hiện không kết nối được OpenMetadata…"*, nhưng **danh sách cột vẫn hiện**, lấy từ lần đồng bộ gần nhất. Trang không bị lỗi.
- `ckan ... lakehouse om sync` → báo lỗi `... nothing was changed`: **không xóa, không sửa gì** khi nguồn đang lỗi.

Bật lại (lệnh ở bước 0.2), rồi tải lại tab để thấy dữ liệu live trở lại. Cache giữ dữ liệu tối đa 60 giây ở local (`om.cache_ttl`).

### B7. (tùy chọn) Bảng rời khỏi phạm vi

```bash
ckan config-tool ~/ckan/etc/ckan.ini "ckanext.lakehouse.om.exclude = *.dim_customer"
ckan -c ~/ckan/etc/ckan.ini lakehouse om sync          # Removed (1): ...dim_customer
ckan config-tool ~/ckan/etc/ckan.ini "ckanext.lakehouse.om.exclude = "
ckan -c ~/ckan/etc/ckan.ini lakehouse om sync          # Updated: ...dim_customer (state) → khôi phục, cùng URL
```

Bảng bị loại thì dataset được ẩn (xóa mềm); bảng quay lại thì **khôi phục đúng dataset cũ**, giữ nguyên lượt xem, người theo dõi và URL.

---

## 3. Câu hỏi hay gặp khi demo

| Câu hỏi | Trả lời ngắn |
|---|---|
| Sao không thấy user ở `/ckan-admin`? | Trang đó chỉ hiện sysadmin. Danh sách đầy đủ ở `/user/` |
| Đăng nhập bằng tài khoản công ty (AD/SSO) được không? | Chưa. Hiện là tài khoản riêng của CKAN (Q5). Có thể thêm LDAP/OIDC sau, phân quyền vẫn giữ nguyên |
| Dữ liệu OpenMetadata ở đây có thật không? | Không, là bảng **hư cấu**. Laptop không vào được OpenMetadata của công ty; dữ liệu thật sẽ lấy qua `tools/openmetadata/om_snapshot.py` chạy trên máy công ty |
| CKAN có chứa dữ liệu bảng không? | Không. Chỉ có **metadata** và link Trino; không lấy sample data hay giá trị cột |
| Thêm đơn vị/người mới thì làm sao? | Sửa `portal.yaml` → chạy lại `bootstrap`. Mật khẩu người mới ghi vào file `--credentials` |
| Ai được công bố dữ liệu ra ngoài? | Biên tập viên / quản trị **của đơn vị sở hữu**. Đồng bộ luôn tạo ở chế độ private |

---

## 4. Demo trên cụm kind (giống môi trường K8s thật)

Cụm `ckan-rehearsal` đang chạy `0.2.0` ở http://localhost:30500, đã có user demo và 5 dataset từ OpenMetadata giả trong cụm.
- Đăng nhập `admin`: mật khẩu là `CKAN_SYSADMIN_PASSWORD` trong `k8s/overlays/kind/secrets.env`.
- Mật khẩu các user demo trên kind **không được lưu** (smoke test in ra rồi bỏ). Muốn dùng thì đặt lại ở `/user/edit/<tên>` như mục 0.
- Chạy lại toàn bộ kiểm tra tự động trong khoảng 1,5 phút:

  ```bash
  bash k8s/overlays/kind/smoke-test-om.sh kind-ckan-rehearsal   # 31 kiểm tra
  ```

## 5. Dọn sau demo

- Đưa dataset về private nếu đã công khai ở A5.
- Thẻ `do-tin-cay` (B5) có thể giữ hoặc xóa trong Quản lý.
- Tắt mock: `pkill -f "[o]m_mock\.py"`. Tắt CKAN: Ctrl+C.
