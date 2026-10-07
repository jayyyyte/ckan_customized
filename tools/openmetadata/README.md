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

   ```powershell
   $env:OM_TOKEN = "<dán JWT>"
   python om_snapshot.py --url http://<địa chỉ OM>:8585 `
       --include "trino_lakehouse.iceberg_curated.*" --out lakehouse.om-snapshot.json
   Remove-Item Env:OM_TOKEN
   ```

   - Không đặt `OM_TOKEN` thì script sẽ hỏi token, và token không hiện ra khi gõ.
   - Muốn xem mọi bảng thì bỏ `--include`. Mặc định script dừng ở 300 bảng (`--max-tables`).
   - Dòng đầu script in ra cho biết bản OpenMetadata đang dùng `owners`/`domains` hay `owner`/`domain`.
3. Chép `lakehouse.om-snapshot.json` về laptop, đặt **ngoài git**, ví dụ `tools/openmetadata/snapshots/` (đã có trong `.gitignore` và `.dockerignore`). Xong việc thì xóa file.

**Có trong file:**
- bảng: mô tả, cột, owner, domain, tag, số lượt truy vấn;
- số dòng và số cột của lần profile gần nhất;
- lineage một bậc;
- trạng thái các test chất lượng.

**Không có trong file:**
- token;
- sample data;
- profile cột (min/max/mean là giá trị thật);
- thông điệp kết quả test;
- tên người follow;
- custom property.

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

Mock trả lời đúng các endpoint mà extension gọi:
- `system/version`;
- `tables` (có phân trang và lọc theo `databaseSchema`);
- `tables/name/{fqn}`;
- `tables/{fqn}/tableProfile/latest`;
- `lineage/table/name/{fqn}`;
- `dataQuality/testCases`.

Với `fields` lạ, mock trả 400 "Invalid field name" giống OpenMetadata thật. Endpoint nào khác đều trả 404.
