# OpenMetadata: snapshot và mock

OpenMetadata thật chỉ vào được từ máy công ty (Remote Desktop). Hai script dưới đây cho phép phát triển và kiểm thử `ckanext-lakehouse` trên laptop bằng **metadata thật** mà không cần mạng công ty. Cả hai chỉ dùng thư viện chuẩn, chạy được trên Python 3.8+ (Windows hoặc Linux).

| File | Chạy ở đâu | Làm gì |
|---|---|---|
| `om_snapshot.py` | Máy công ty (RDP) | Đọc API OpenMetadata, ghi ra một file JSON |
| `om_mock.py` | Laptop (WSL) | Giả lập API OpenMetadata từ file JSON đó |
| `sample-snapshot.json` | — | 7 bảng **hư cấu**, dùng khi chưa có snapshot thật và trong test |

## 1. Ghi snapshot trên máy công ty

1. Lấy token chỉ đọc. Trên OpenMetadata vào **Settings → Bots**, chọn hoặc tạo một bot có quyền đọc, rồi copy JWT. Hoặc vào **Profile → Access Tokens** để dùng token cá nhân.
2. Chép `om_snapshot.py` sang máy công ty (copy/paste qua RDP), rồi mở PowerShell:

   Kiểm tra Python trên **máy RDP** trước (Python trong WSL của laptop không dùng được ở đây):

   ```powershell
   py --version
   python --version
   Test-Path .\om_snapshot.py
   ```

   Chỉ cần một trong hai lệnh phiên bản chạy được. Nếu `python` không được nhận diện nhưng `py` chạy được, dùng `py` thay cho `python` ở lệnh dưới. Nếu cả hai đều không có, cài Python từ [python.org](https://www.python.org/downloads/windows/) trên máy RDP rồi mở lại PowerShell. Nếu máy RDP không có Internet, tải bộ cài trên laptop rồi chép sang. Script chỉ dùng thư viện chuẩn, không cần `pip install` hay cài CKAN. Nếu `Test-Path` trả `False`, chuyển đến thư mục đã chép script trước khi chạy.

   Cách chạy đơn giản nhất là để script hỏi token (nhập ẩn, không lưu JWT vào lịch sử PowerShell):

   ```powershell
   py .\om_snapshot.py --url https://openmetadata-stag.evn.com.vn --include "trino_lakehouse.iceberg_curated.*" --out lakehouse.om-snapshot.json
   ```

   Nếu đã dùng biến môi trường thì chạy như sau:

   ```powershell
   $env:OM_TOKEN = "<dán JWT>"
   python om_snapshot.py --url https://openmetadata-stag.evn.com.vn `
       --include "trino_lakehouse.iceberg_curated.*" --out lakehouse.om-snapshot.json
   Remove-Item Env:OM_TOKEN -ErrorAction SilentlyContinue
   ```

   - `openmetadata-stag.evn.com.vn` chỉ phân giải được trên máy có dòng tương ứng trong file hosts (máy RDP, 2026-10-15).
   - Báo `CERTIFICATE_VERIFY_FAILED` thì thêm `--insecure`: chứng chỉ do CA nội bộ cấp mà Python không tin, dù trình duyệt có thể vẫn tin.

   - Không đặt `OM_TOKEN` thì script sẽ hỏi token, và token không hiện ra khi gõ.
   - Muốn xem mọi bảng thì bỏ `--include`. Mặc định script dừng ở 300 bảng (`--max-tables`).
   - Dòng đầu script in ra cho biết bản OpenMetadata đang dùng `owners`/`domains` hay `owner`/`domain`.
3. Chép `lakehouse.om-snapshot.json` về laptop, đặt **ngoài git**, ví dụ `tools/openmetadata/snapshots/` (đã có trong `.gitignore` và `.dockerignore`). Xong việc thì xóa file.

**Có trong file:**
- bảng: mô tả, cột, owner, domain, tag, số lượt truy vấn;
- số dòng và số cột của lần profile gần nhất;
- lineage một bậc;
- trạng thái các test chất lượng;
- **team** (cây cha/con, thành viên, owner, default role), **domain/subdomain** (owner, expert), **người** (tên, email, team, role). `ckan lakehouse om scaffold` dùng phần này để sinh org/group/vai trò. Bỏ phần này bằng `--no-people`.

**Không có trong file:**
- token;
- sample data;
- profile cột (min/max/mean là giá trị thật);
- thông điệp kết quả test;
- tên người follow;
- custom property;
- bot.

## 2. Phát lại trên laptop

```bash
python3 tools/openmetadata/om_mock.py tools/openmetadata/snapshots/lakehouse.om-snapshot.json \
    --port 8585 --token dev-token          # --legacy: giả lập OpenMetadata < 1.5
```

Cấu hình CKAN local trong `~/ckan/etc/ckan.ini`:

```ini
ckanext.lakehouse.om.url = http://127.0.0.1:8585
ckanext.lakehouse.om.api_token = dev-token
ckanext.lakehouse.om.include = trino_lakehouse.iceberg_curated.*
```

Rồi chạy `ckan -c ~/ckan/etc/ckan.ini lakehouse om check` và `... om sync`. Với container (compose, kind) thì chạy mock với `--host 0.0.0.0` và trỏ tới `http://host.docker.internal:8585`.

### Khi lệnh CKAN local bị lỗi

- `Connection refused` ở `127.0.0.1:8983`: mở Docker Desktop, chạy `docker start ckan-solr`, rồi kiểm tra `curl -fsS 'http://127.0.0.1:8983/solr/ckan/admin/ping?wt=json'` phải có `"status":"OK"` (có thể có khoảng trắng). Đây là Solr của bản cài WSL, khác service Solr trong compose.
- `You need to specify the CKAN config`: dùng `ckan -c ~/ckan/etc/ckan.ini lakehouse om check`, hoặc `export CKAN_INI="$HOME/ckan/etc/ckan.ini"` trong terminal WSL hiện tại.
- `cannot reach OpenMetadata` khi cấu hình trỏ `127.0.0.1:8585`: chạy mock ở một terminal WSL riêng và giữ terminal đó mở. Chưa có snapshot thật thì có thể dùng `tools/openmetadata/sample-snapshot.json` (dữ liệu demo hư cấu).
- Traceback còn trỏ thư mục repo cũ: sau khi activate venv, chạy `python -m pip install --no-deps --no-build-isolation -e /mnt/c/Users/Tlinh/ckan_customized/ckanext-lakehouse`, rồi restart tiến trình CKAN đang mở. Kiểm tra bằng `python -m pip show ckanext-lakehouse`.
- Bootstrap lỗi giữa chừng có thể đã tạo một số user; giữ lại CSV mật khẩu của lần đó. Khi cần tạo user còn thiếu, dùng tên file `--credentials` mới vì bootstrap không ghi đè CSV cũ.

Mock trả lời đúng các endpoint mà extension gọi:
- `system/version`;
- `tables` (có phân trang và lọc theo `databaseSchema`);
- `tables/name/{fqn}`;
- `tables/{fqn}/tableProfile/latest`;
- `lineage/table/name/{fqn}`;
- `dataQuality/testCases`;
- `teams`, `domains`, `users`, `users/name/{name}` (cho `om scaffold` và bảng do một người đứng tên).

Với `fields` lạ, mock trả 400 "Invalid field name" giống OpenMetadata thật. Endpoint nào khác đều trả 404.
