# ckanext-lakehouse

Extension của Cổng dữ liệu EVN (CKAN 2.11), plugin `lakehouse`. Nó lo ba việc:

- **`ckan lakehouse bootstrap`**: khai báo organization, group, người dùng và vai trò bằng một file YAML; chạy lại nhiều lần vẫn an toàn.
- **`ckan lakehouse om check | sync`**: công bố các bảng của OpenMetadata thành dataset CKAN.
- **Tab "Danh mục kỹ thuật"** trên trang dataset: lineage, kiểm định chất lượng, profile và cột, lấy trực tiếp từ OpenMetadata.

Thiết kế, quy tắc ánh xạ và kết quả kiểm chứng nằm ở [docs/phase-4-content-openmetadata.md](../docs/phase-4-content-openmetadata.md). Tab nằm trong trang dataset của [`ckanext-evntheme`](../ckanext-evntheme/README.md), vì vậy hai plugin luôn được bật cùng nhau: `ckan.plugins = evntheme lakehouse ...`.

## Cài đặt

```bash
pip install -e ckanext-lakehouse
pybabel compile -d ckanext-lakehouse/ckanext/lakehouse/i18n -D ckanext-lakehouse
# ckan.plugins = evntheme lakehouse activity tracking ...
```

Extension không có migration; mọi thứ được lưu bằng extras của core. Cache dùng `ckan.redis.url`.

## Cấu hình `ckanext.lakehouse.*`

Xem đầy đủ bằng `ckan config declaration lakehouse`. Trên K8s, mỗi key tương ứng một biến môi trường, ví dụ `ckanext.lakehouse.om.url` thành `CKANEXT__LAKEHOUSE__OM__URL`.

| Key | Mặc định | Ý nghĩa |
|---|---|---|
| `om.url` | (trống) | Server OpenMetadata, không kèm `/api`. Để trống thì tắt mọi tính năng OpenMetadata |
| `om.ui_url` | = `om.url` | Địa chỉ dùng cho link mở trong trình duyệt |
| `om.api_token` | (trống) | JWT của bot chỉ đọc. **Phải để trong Secret** |
| `om.include` / `om.exclude` | (trống) | Mẫu FQN (fnmatch, cách nhau bằng dấu cách). `include` trống thì không công bố gì |
| `om.require_tags` | (trống) | Chỉ công bố bảng có ít nhất một trong các tag này, ví dụ `Tier.Tier1` |
| `om.default_org` | (trống) | Org nhận các bảng không ai nhận. Để trống thì bỏ qua các bảng đó |
| `om.private` | `true` | Dataset mới được tạo ở chế độ private |
| `om.on_removed` | `delete` | `delete` (soft delete, có khôi phục) hoặc `keep` |
| `om.sync_user` | `om-sync` | User đứng tên trong activity stream |
| `om.fetch_profile` | `true` | Đọc `rowCount` để điền `record_count` |
| `om.trino_jdbc_url` | (trống) | Ví dụ `jdbc:trino://10.1.117.91:30800`; sinh resource `.../catalog/schema` |
| `om.trino_catalogs` | (trống) | Các cặp `service.database=catalog` cho service không phải Trino |
| `om.timeout` / `om.sync_timeout` | 5 / 30 | Thời gian chờ tính bằng giây: khi render trang / khi đồng bộ |
| `om.cache_ttl` | 600 | Số giây cache Redis của tab; `0` để tắt |
| `om.verify_ssl` | `true` | Kiểm tra chứng chỉ khi OpenMetadata chạy `https://` |

Org và group nhận bảng của OpenMetadata qua extras do bootstrap ghi, mỗi extra là một list JSON:
- org: `om_teams`, `om_fqn_patterns`;
- group: `om_domains`.

## Phát triển

- Không vào được OpenMetadata thật thì dùng snapshot + mock: xem [tools/openmetadata/README.md](../tools/openmetadata/README.md).
- Unit test (không cần DB):

  ```bash
  python -m pytest -o addopts="" -p no:ckan -p no:ckan_fixtures ckanext/lakehouse/tests/test_units.py
  ```

- App test (cần `ckan_test` và Solr): `pytest --ckan-ini=test.ini ckanext/lakehouse/tests/test_app.py`. CI chạy ở `.github/workflows/lakehouse.yml`.
- Bản dịch: msgid tiếng Anh, bản dịch nằm trong `i18n/vi/LC_MESSAGES/ckanext-lakehouse.po`.

  ```bash
  pybabel extract -F babel.cfg -k N_ -o /tmp/lh.pot ckanext   # rồi bổ sung .po
  pybabel compile -d ckanext/lakehouse/i18n -D ckanext-lakehouse
  ```
