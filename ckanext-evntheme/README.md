# ckanext-evntheme — giao diện "Cổng dữ liệu EVN"

Extension CKAN dựng lại giao diện trong mockup `CKAN Custom Theme UI Mockup/handoff/`, gồm:
- trang chủ;
- tìm kiếm với facet dạng checkbox;
- chi tiết bộ dữ liệu với 4 tab: Tổng quan, Xem trước, Thử API, Nhật ký;
- danh bạ tổ chức;
- trang **Danh mục chuẩn** (MDS), có bảng dữ liệu riêng.

Extension dùng template Jinja2 override, CSS biên dịch từ SCSS và JS module của CKAN, không nhúng file mockup.

| CKAN | Hỗ trợ |
|---|---|
| 2.11 (classic, Bootstrap 5.1.3) | Có, nhắm tới 2.11.6 |
| 2.12 | Chưa thử. Xem mục [Nâng cấp CKAN](#nâng-cấp-ckan) |

Python ≥ 3.10, vì image `ckan-base:2.11` dùng 3.10.

## Cài đặt

```bash
. ~/ckan/default/bin/activate
pip install -e /path/to/ckanext-evntheme
pybabel compile -d ckanext-evntheme/ckanext/evntheme/i18n -D ckanext-evntheme
```

Trong `ckan.ini`, đặt theme **đầu tiên** để template của nó được ưu tiên:

```ini
ckan.plugins = evntheme activity tracking text_view image_view
ckan.site_title = Cổng dữ liệu EVN
ckan.site_description = Chia sẻ dữ liệu dùng chung toàn Tập đoàn
ckan.favicon = /evntheme/images/favicon.svg
```

Tạo bảng (MDS của theme, bảng tracking của core), rồi restart CKAN:

```bash
ckan -c ckan.ini db upgrade -p tracking
ckan -c ckan.ini db upgrade -p evntheme
```

Plugin `tracking` không bắt buộc. Có nó thì theme hiện "lượt tải" và có thêm lựa chọn sắp xếp "Xem nhiều nhất". Không có thì các chỗ đó tự ẩn. Số liệu tracking được tổng hợp bằng `ckan tracking update`, nên chạy lệnh này theo lịch, ví dụ cron hằng đêm.

Khi bật `datastore` (+ XLoader), các tab "Xem trước dữ liệu" và "Thử API" dùng `datastore_search`. Chưa bật thì tab Xem trước hiện empty state, còn tab Thử API minh họa bằng `package_show`. Trên WSL local, bật bằng `setup_step3_datastore.sh` ở gốc repo.

### Logo và favicon

Theme lấy logo từ key chuẩn **`ckan.site_logo`** của CKAN và nhận mọi định dạng ảnh. Khi key này còn giữ giá trị mặc định của CKAN, theme hiện placeholder `public/evntheme/images/evn-logo.svg`. Không vẽ lại logo.

| Cách | Làm thế nào | Định dạng | Ghi chú |
|---|---|---|---|
| **Upload trên web** (khuyên dùng) | Đăng nhập sysadmin → `/ckan-admin/config` → "Site logo" → Upload → Update Config | PNG, JPEG, GIF, WebP; tối đa `ckan.max_image_size` MB (mặc định 2) | Có hiệu lực ngay, không cần build lại image. File nằm trong `storage/uploads/admin/` (PVC trên K8s), giá trị lưu trong DB và **đè lên `ckan.ini`** |
| Đường dẫn / URL | `ckan.site_logo = /evntheme/images/evn-logo.png` (file đặt trong `public/evntheme/images/`), hoặc một URL `https://…`. Trên K8s dùng env `CKAN__SITE_LOGO` | Mọi định dạng, kể cả SVG | File trong theme được đóng vào image |

- Upload không nhận SVG, vì mở trực tiếp một file SVG là chạy script của nó trên origin của portal. Logo SVG thì dùng cách thứ hai. Danh sách định dạng đổi bằng `ckan.upload.admin.mimetypes` (gotchas 6ai).
- Khung logo cao cố định (header 44px, footer 40px), chiều rộng theo tỉ lệ file, tối đa 176px (88px trên mobile). Logo vuông hiển thị đúng như mockup. Kích thước chỉnh ở các token `--evn-logo-*` trong `_tokens.scss`.
- PNG/WebP nên có nền trong suốt. JPG vẫn đẹp vì header nền trắng, còn footer đặt logo trên ô nền trắng.
- Để trống "Site logo" ở trang admin thì header chỉ hiện tên portal.
- Favicon: `ckan.favicon` nhận đường dẫn hoặc URL tới `.ico`, `.png` hay `.svg`.

## Cấu hình

Xem đầy đủ bằng `ckan config declaration evntheme`. Trên K8s, mỗi key đặt được bằng biến môi trường `CKANEXT__EVNTHEME__<KEY>`.

| Key `ckanext.evntheme.*` | Mặc định | Ý nghĩa |
|---|---|---|
| `owner_name`, `platform_name` | Tập đoàn Điện lực Việt Nam, Nền tảng dữ liệu dùng chung | Chữ trên thanh utility và footer |
| `operator` | EVNICT | "Vận hành bởi …" ở footer |
| `contact_email`, `contact_address` | data@evn.com.vn, 11 Cửa Bắc… | Cột Liên hệ. Để trống thì ẩn |
| `guide_url`, `api_docs_url`, `support_url`, `terms_url` | `/about`, docs CKAN API, (mailto), (trống) | Link utility bar và footer |
| `openmetadata_url`, `trino_docs_url` | (trống), docs Trino JDBC | Cột "Nhà phát triển" ở footer: Danh mục kỹ thuật (OpenMetadata), Kết nối bằng Trino JDBC. Để trống thì ẩn |
| `hot_searches` | 4 cụm từ, cách nhau bằng `;` | Chip "Mọi người đang tìm" |
| `domain_groups` | (tất cả group) | Tên các group là "miền dữ liệu", đúng thứ tự hiển thị |
| `home_datasets` | 4 | Số bộ dữ liệu trong "Mới cập nhật" |
| `api_metrics_url` | (trống) | Endpoint JSON `{"uptime_30d", "calls_today", "latency_ms"}` cho thẻ nhà phát triển. Trống thì ẩn các dòng số liệu |
| `api_rate_limit` | (trống) | Ô "Hạn mức" ở tab Thử API |
| `sidebar_facets` | `organization res_format data_type tags license_id` | Facet hiện ở sidebar, đúng thứ tự |
| `facet_items` | 5 | Số giá trị hiện trước link "Xem thêm N" |
| `preview_rows` | 10 | Số dòng mỗi trang của bảng xem trước |
| `map_tile_url` | (trống) | URL tile Leaflet. Trống thì chỉ vẽ hình, không có nền bản đồ, nên dùng được trong mạng nội bộ |
| `zip_max_mb` | 500 | Giới hạn "Tải tất cả" (zip các tệp upload) |
| `stats_cache_seconds` | 300 | Thời gian cache các bộ đếm toàn portal. `0` là tắt cache |

## Dữ liệu theme đọc

Theme **chỉ hiển thị số liệu có thật**: khối nào không có dữ liệu thì ẩn. Các trường dưới đây là *extras*, nhập ở mục "Custom field" khi sửa dataset, tổ chức hoặc group. Nếu sau này dùng ckanext-scheming thì theme đọc được cả trường top-level cùng tên.

| Đối tượng | Key | Giá trị | Dùng ở |
|---|---|---|---|
| Dataset | `data_type` | `master` / `transaction` / `reference` | Badge loại dữ liệu, facet "Loại dữ liệu" |
| Dataset | `update_frequency` | `realtime`, `hourly`, `daily`, `weekly`, `monthly`, `quarterly`, `yearly`, `irregular` | "Chu kỳ", tỷ lệ "Công bố đúng hạn" |
| Dataset | `record_count`, `source_system` | số, chữ | Ô KPI |
| Dataset | `quality_completeness`, `quality_uniqueness`, `quality_validity`, `quality_timeliness` | 0–100 | Thẻ "Chất lượng dữ liệu" |
| Dataset | `golden_record`, `metadata_standard` | `true`, "DCAT-AP 2.1" | Badge ở hero |
| Dataset | `spatial_coverage`, `temporal_coverage`, `open_level` (0–5) | chữ, số | Sidebar "Thông tin bộ dữ liệu" |
| Dataset | `rating_average`, `rating_count` | số | ★ đánh giá, nếu có extension điền |
| Tổ chức | `org_type` | `department` / `corporation` / `affiliate` / `other` | Nhãn và tab lọc ở /organization |
| Tổ chức | `abbreviation`, `domain` | "QLĐT", tên group | Avatar, dòng miền dữ liệu |
| Group | `tone` | `blue` / `orange` / `green` / `sky` / `sand` | Màu thẻ miền dữ liệu |

Cách tính các số liệu suy ra:
- **API**: số dataset có resource định dạng `API` hoặc đã nạp DataStore.
- **Công bố đúng hạn**: tỷ lệ dataset có `update_frequency` được cập nhật (`metadata_modified`) trong chu kỳ đó, cộng thêm biên độ khai báo trong `vocab.FREQUENCIES`.
- **Đơn vị nổi bật tháng này**: đơn vị có nhiều dataset cập nhật nhất trong 30 ngày.
- **Độ tươi**: tuổi của dataset mới nhất của đơn vị. Xanh khi ≤ 12 giờ, cam khi ≤ 2 ngày, đỏ khi lâu hơn.

## Danh mục chuẩn (MDS)

Trang `/mds` và `/mds/<mã>`, cùng file tải về `/mds/<mã>/download.csv|json`. Dữ liệu nằm ở các bảng `mds_catalog`, `mds_code`, `mds_version`, `mds_consumer`. Nạp và xuất bằng CLI:

```bash
ckan -c ckan.ini evntheme mds load danh-muc.json    # tạo mới hoặc thay thế theo mã danh mục
ckan -c ckan.ini evntheme mds export MDS-VT-001 --format csv
```

Định dạng JSON xem ở `ckanext/evntheme/demo/mds.json`. Trạng thái hợp lệ nằm trong `vocab.MDS_*_STATUSES`.

## Dữ liệu demo (chỉ dùng local)

```bash
ckan -c ckan.ini evntheme seed-demo            # 5 miền, 9 đơn vị, 12 bộ dữ liệu, 10 danh mục chuẩn
ckan -c ckan.ini evntheme seed-demo --reset    # xóa sạch rồi nạp lại
```

Lệnh chạy với quyền `admin` để các thay đổi hiện trong nhật ký. Khi có plugin tracking, lệnh còn giả lập lượt xem và lượt tải, cho đi qua đúng pipeline `tracking update`.

## Phát triển

```
ckanext/evntheme/
  plugin.py            chỉ nối interface
  config.py            khai báo config + accessor
  vocab.py             MỌI bảng mã → nhãn/màu: loại dữ liệu, chu kỳ, loại đơn vị, facet, tab, trạng thái
  stats.py, cache.py   số liệu toàn portal (một lần quét package_search, có cache)
  formatting.py        số, ngày, % theo locale (1.204 / 98,4%)
  helpers/             h.evn_*: site, dataset, search, organization, datastore, trino
  mds/                 model, service, views của Danh mục chuẩn
  downloads.py         /dataset/<id>/download-all
  cli.py, demo/        lệnh `ckan evntheme …`, dữ liệu demo
  templates/           override mỏng của core + markup trong templates/evntheme/
  assets/scss/         _tokens.scss (màu, font…), _base, _components, layout/, pages/
  assets/css/          evn-theme.css đã biên dịch (có commit)
  assets/js/           evn-utils.js + modules/evn-*.js (ckan.module)
  public/evntheme/     font tự host, icons.svg, logo, vendor/ (Chart.js, Leaflet, chỉ nạp khi cần)
  i18n/vi/             .po (commit) → .mo (build, không commit)
  tests/               test_units.py (thuần), test_app.py (cần DB test, chạy trong CI)
```

**CSS.** Sửa SCSS xong thì build lại và commit file CSS. Image CKAN không cần Node.

```bash
npm install && npm run build:css      # hoặc: npm run watch:css
```

- Màu chỉ khai báo trong `_tokens.scss`. Lớp "ink" đã được làm đậm để đạt WCAG AA, xem chú thích tỷ lệ tương phản cạnh từng giá trị.
- Không dùng `!important`, không dùng inline style.
- Selector phần tử đi qua `:where(.evn)` để luôn có specificity thấp nhất.

**JS.** Mỗi hành vi là một `ckan.module('evn-…')`. Tất cả là progressive enhancement: trang vẫn dùng được khi tắt JS (tab qua `?tab=`, facet có nút "Áp dụng", sắp xếp có nút).

**Dịch.** Chuỗi trong template viết `{{ _('English msgid') }}`. Chuỗi trong Python là hằng số thì đánh dấu bằng `N_()` (xem `vocab.py`) và dịch lúc render.

```bash
pybabel extract -F babel.cfg -k N_ -k ungettext:1,2 -o /tmp/evntheme.pot ckanext
pybabel update -i /tmp/evntheme.pot -d ckanext/evntheme/i18n -D ckanext-evntheme   # rồi dịch msgstr mới
pybabel compile -d ckanext/evntheme/i18n -D ckanext-evntheme
```

Test `test_units.py` kiểm tra mọi nhãn trong `vocab.py` đều đã dịch, và placeholder `{n}`, `%(x)s` được giữ nguyên trong bản dịch.

**Test.**

```bash
python -m pytest -o addopts="" -p no:ckan -p no:ckan_fixtures ckanext/evntheme/tests/test_units.py   # local, không cần DB
pytest --ckan-ini=test.ini ckanext/evntheme/tests/test_app.py                                        # cần DB ckan_test
```

CI nằm ở `.github/workflows/evntheme.yml` (gốc repo), gồm ruff và cả hai bộ test.

### Mở rộng thường gặp

- **Thêm loại dữ liệu, chu kỳ hoặc loại đơn vị**: thêm một `Term` trong `vocab.py`, thêm bản dịch vào `.po`. Nếu cần màu riêng thì thêm vào map tương ứng trong `_tokens.scss`.
- **Thêm facet**: thêm vào `vocab.FACETS` (tiêu đề) và config `sidebar_facets` (hiển thị). Nếu cần nhãn riêng cho giá trị thì sửa `helpers/search.py:facet_value_label`.
- **Đổi hoặc bỏ một khối trang chủ**: override block tương ứng (`evn_home_hero`, `evn_home_domains`, `evn_home_latest`, `evn_home_aside`) trong một plugin khác, hoặc sửa snippet ở `templates/evntheme/home/`.
- **Thêm tab cho trang dataset**: thêm `Term` vào `vocab.DATASET_TABS` và snippet `templates/evntheme/dataset/<code>.html`.

### Nâng cấp CKAN

Những phần phụ thuộc phiên bản CKAN:
- Template override các block của classic 2.11: `header_wrapper`, `content`, `package_item`, `package_list`, `facet_list`, `resource_read_url`. Khi nâng cấp, so lại tên block bằng `grep -noE '\{%-?\s*block [a-z_]+'`.
- `pages/_core.scss` tô màu lại markup classic cho Bootstrap 5.1.3. Ở 2.12 (Bootstrap 5.3) có thể thay bằng biến `--bs-*`.
- Nút "Theo dõi" gọi thẳng endpoint `dataset.follow/unfollow`. Endpoint này ở 2.11 trả fragment htmx.
- `downloads.py` chỉ nén được tệp trên đĩa local. Nếu chuyển upload sang MinIO/S3 (IUploader) thì cần sửa `local_files()`.

## Tài nguyên bên thứ ba

| Thành phần | Giấy phép | Vị trí |
|---|---|---|
| Nunito, Nunito Sans (subset latin, latin-ext, vietnamese) | SIL OFL 1.1 | `public/evntheme/fonts/` |
| Chart.js 4.4.6 | MIT | `public/evntheme/vendor/chartjs/` |
| Leaflet 1.9.4 | BSD-2-Clause | `public/evntheme/vendor/leaflet/` |
| Icon nét (vẽ theo Feather Icons) | MIT | `public/evntheme/icons.svg` |

## Giấy phép

AGPL-3.0, giống CKAN.
