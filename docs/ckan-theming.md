# Làm theme cho CKAN 2.11

## Nguyên tắc
- **Không bao giờ sửa file của core** (`~/ckan/default/src/ckan`). Mọi tùy biến đều nằm trong extension `ckanext-lakehouse_theme`.
- Override **đúng đường dẫn** template trong thư mục `templates/` của extension. Dùng `{% ckan_extends %}` và chỉ ghi đè những `block` thực sự cần đổi. Làm vậy thì nâng cấp CKAN ít bị vỡ.
- Template gốc dùng **Bootstrap 5.1.3**. Bootstrap 3 đã bị bỏ từ 2.11.0.

## Theme gốc: classic (Q9)

CKAN 2.11 chỉ có **một** bộ template/asset gốc:

| | Classic |
|---|---|
| Thư mục | `templates` / `public` |
| Config | `ckan.base_templates_folder = templates`, `ckan.base_public_folder = public`. Đây là mặc định và là giá trị hợp lệ **duy nhất** ở 2.11 |
| CSS | `public/base/css/main.css`, biên dịch từ `public/base/scss` với Bootstrap 5.1.3 |

Lịch sử Q9:
- **2026-09-14, trên 2.12.0:** chọn Midnight Blue sau khi so với classic.
- **2026-09-18:** dự án quay về 2.11, mà Midnight Blue chỉ có từ 2.12, nên theme chuyển sang classic.

Những gì phải làm lại khi chuyển:

| Chỗ | Midnight Blue (2.12) | Classic (2.11) → theme làm gì |
|---|---|---|
| Ô tìm kiếm ở header | Không có, theme tự thêm form | Có sẵn block `header_site_search`. Theme chỉ ẩn nó ở trang chủ và `/dataset`, vì hai trang đó đã có ô tìm kiếm trong thân trang |
| Nút đăng nhập | Trong masthead (`header_account_notlogged`) | Nằm ở thanh `account-masthead` riêng phía trên masthead |
| `footer_content` | Chỉ chứa phần link; attribution và chọn ngôn ngữ ở dải `.bg-black` bên ngoài | Chứa **cả** `footer_attribution` và `footer_lang`. Override là mất cả hai, nên theme gọi lại `{{ self.footer_attribution() }}` và `{{ self.footer_lang() }}` |
| `footer_links` | Trang chủ, Dữ liệu, Tổ chức, Nhóm, Thông tin | Chỉ có "Thông tin". Theme tự thêm link Dữ liệu, Tổ chức, Nhóm |
| Trang chủ | Hero + org nổi bật + `featured_datasets` (Recent Datasets) + nhóm | Hero (2 cột: promoted + search) + dải `module-feeds` (2 cột: `featured_group` \| `featured_organization`). Theme đặt "Bộ dữ liệu mới cập nhật" vào cột trái (helper `lakehouse_theme_recent_datasets`), còn org và nhóm nổi bật dồn sang cột phải |
| Số dataset | Tiêu đề ô tìm kiếm (`h.get_dataset_count`, chỉ có ở 2.12) | Theme hiện số dataset và số tổ chức trong hero bằng `h.get_site_statistics()`, helper có ở cả hai bản |
| Màu | Bootstrap 5.3, component có biến `--bs-btn-*`… | Bootstrap 5.1.3 **không có** biến theo component. Phải đặt thẳng `background-color`, `border-color` (gotchas 6r) |

## Hai tầng tùy biến

| Tầng | Cách làm | Ví dụ |
|---|---|---|
| **1. Cấu hình** (không code) | `ckan.ini` hoặc trang `/ckan-admin/config` | `ckan.site_title`, `ckan.site_logo`, `ckan.site_description`, `ckan.favicon`, intro text, custom CSS ngắn |
| **2. Extension** | Override template, thêm CSS/JS, helper, trang mới | Header/footer mới, trang chủ mới, trang dataset có hướng dẫn kết nối Trino |

Giá trị đặt ở `/ckan-admin/config` được lưu trong DB và **ghi đè** `ckan.ini`.

## Cấu trúc extension

Cấu trúc thật của `ckanext-lakehouse_theme` (cập nhật 2026-09-18):

```
ckanext-lakehouse_theme/
├── pyproject.toml                # entry point [ckan.plugins]: lakehouse_theme = ckanext.lakehouse_theme.plugin:LakehouseThemePlugin
└── ckanext/lakehouse_theme/
    ├── plugin.py                 # IConfigurer, IConfigDeclaration, ITemplateHelpers, ITranslation
    ├── helpers.py                # lakehouse_theme_trino_connection, lakehouse_theme_links, lakehouse_theme_recent_datasets
    ├── templates/
    │   ├── base.html             # nạp CSS/JS của theme
    │   ├── header.html           # logo; ẩn ô tìm kiếm header ở trang đã có ô tìm kiếm
    │   ├── footer.html           # 3 cột + attribution + chọn ngôn ngữ
    │   ├── home/index.html       # cột trái: dataset mới; cột phải: org + nhóm nổi bật
    │   ├── home/snippets/promoted.html      # hero + thống kê
    │   ├── package/resource_read.html       # chèn hộp "Cách kết nối" cho jdbc:trino://
    │   └── lakehouse_theme/snippets/        # logo_mark.html, trino_connection.html, recent_datasets.html
    ├── public/lakehouse_theme/images/       # phục vụ tại /lakehouse_theme/images/… (favicon.svg)
    ├── assets/                   # webassets.yml, css/lakehouse_theme.css, js/lakehouse_theme.js
    ├── i18n/vi/LC_MESSAGES/      # ckanext-lakehouse_theme.po (commit) → .mo (build, không commit)
    └── tests/                    # test_helpers.py (thuần), test_plugin.py (cần DB test)
```

- File tĩnh trong `public/` được phục vụ từ gốc site, nên đặt trong thư mục con mang tên theme để không đè `/images/…` của core.
- Cấu hình riêng của theme (`ckanext.lakehouse_theme.organization_name`, `contact_email`, `openmetadata_url`, `trino_docs_url`) được khai báo bằng `IConfigDeclaration`, xem bằng `ckan config declaration lakehouse_theme`.

## plugin.py

```python
import ckan.plugins as plugins
import ckan.plugins.toolkit as toolkit

from ckanext.<theme> import helpers


class <Theme>Plugin(plugins.SingletonPlugin):
    plugins.implements(plugins.IConfigurer)
    plugins.implements(plugins.ITemplateHelpers)

    # IConfigurer
    def update_config(self, config):
        toolkit.add_template_directory(config, "templates")
        toolkit.add_public_directory(config, "public")
        toolkit.add_resource("assets", "<theme>")   # tên thư viện asset: '<theme>/...'

    # ITemplateHelpers
    def get_helpers(self):
        return {"<theme>_popular_datasets": helpers.popular_datasets}
```

- Bật plugin bằng cách thêm `<theme>` vào `ckan.plugins`. Trong container thì dùng `CKAN__PLUGINS`, với `envvars` luôn đứng cuối.
- Thứ tự plugin quan trọng khi nhiều plugin cùng override một template. Đặt theme ở **đầu** danh sách. Nếu nghi ngờ, bật `debug = true` để xem template nào đang được dùng.

## Jinja2 trong CKAN

```jinja
{% ckan_extends %}                          {# kế thừa template cùng tên ở lớp dưới (core) #}

{% block header_logo %}                     {# ghi đè một block #}
  <a class="logo" href="{{ h.url_for('home.index') }}">
    <img src="{{ h.url_for_static('/images/logo.svg') }}" alt="{{ g.site_title }}">
  </a>
{% endblock %}

{% block footer_content %}
  {{ super() }}                             {# giữ nội dung gốc, thêm vào sau #}
  <p class="lh-footer-note">{{ _('Dữ liệu từ Lakehouse') }}</p>
{% endblock %}

{{ self.footer_lang() }}                    {# render lại một block của template cha (kể cả block lồng trong block đã override) #}

{% snippet '<theme>/snippets/trino_hint.html', resource=res %}   {# snippet có biến riêng #}
```

- `h.*` là template helper (của core và của ta). `g.site_title`, `g.site_description` là cấu hình site.
- `_('...')` là chuỗi dịch được; `ungettext('dataset', 'datasets', n)` cho số nhiều.
- Snippet chỉ nhận các biến được truyền vào, không thấy biến của template cha. Dùng tag `{% snippet %}` thay cho `{{ h.snippet() }}` (nhanh hơn, theo changelog 2.11.0).
- **Form trong extension nên có CSRF:** thêm `{{ h.csrf_input() }}` bên trong mọi `<form method="post">`. 2.11 vẫn miễn CSRF cho blueprint của extension (`ckan.csrf_protection.ignore_extensions = true`), nhưng 2.12 thì bắt buộc.

## Tìm template/block để override
1. Bật `debug = true`. **Footer debug** sẽ hiện tên các template đã render trang hiện tại.
2. Mở file gốc để xem block:
   ```bash
   grep -noE '\{%-?\s*block [a-z_]+' ~/ckan/default/src/ckan/ckan/templates/header.html
   ```
   Regex phải bắt cả `{%-`, vì nhiều block viết dạng `{%- block scripts %}`.
3. Tạo file có cùng đường dẫn tương đối trong `ckanext/<theme>/templates/`, rồi **restart** `ckan run`, vì file mới thì reloader không nhận.

### Template hay override (block đã kiểm với tag `ckan-2.11.6`)

| Template | Vai trò | Block |
|---|---|---|
| `base.html` | Khung HTML ngoài cùng | `htmltag`, `headtag`, `meta`, `title`, `subtitle`, `links`, `styles`, `custom_styles`, `head_extras`, `bodytag`, `page`, `scripts`, `body_extras` |
| `page.html` | Bố cục trang | `skip`, `header`, `content`, `maintag`, `main_content`, `flash`, `toolbar`, `breadcrumb`, `breadcrumb_content`, `wrapper_class`, `pre_primary`, `secondary`, `secondary_content`, `primary`, `primary_content`, `page_header`, `content_action`, `content_primary_nav`, `page_primary_action`, `primary_content_inner`, `footer`, `scripts` |
| `header.html` | Thanh tài khoản + masthead | `header_wrapper`, `header_account`, `header_account_container_content`, `header_account_logged`, `header_account_profile`, `header_dashboard`, `header_account_settings_link`, `header_account_log_out_link`, `header_account_notlogged`, `header_debug`, `header_logo`, `header_site_navigation`, `header_site_navigation_tabs`, `header_site_search`, `header_site_search_label` |
| `footer.html` | Chân trang | `footer_content` ⊃ (`footer_nav` ⊃ `footer_links`, `footer_links_ckan`), `footer_attribution`, `footer_lang` |
| `home/index.html` | Trang chủ | `primary_content` ⊃ `promoted`, `search`, `featured_group`, `featured_organization` |
| `home/snippets/*.html` | Các phần của trang chủ | `promoted.html`, `search.html`, `featured_group.html`, `featured_organization.html`, `about_text.html` |
| `package/search.html` | Trang tìm kiếm dataset | `primary_content`, `page_primary_action`, `form`, `package_search_results_list`, `page_pagination`, `package_search_results_api`, `secondary_content` |
| `snippets/package_item.html` | Thẻ dataset trong danh sách | `package_item`, `content`, `heading`, `heading_title`, `heading_meta`, `notes`, `resources` |
| `package/read.html`, `package/resource_read.html` | Chi tiết dataset / resource | `resource_read_url` (theme chèn hộp Trino ở đây), `resource_additional_information`… |

## CSS/JS với webassets

`assets/webassets.yml`:

```yaml
lakehouse_theme-css:
  # KHÔNG dùng filters: cssrewrite — lỗi 500 với thư viện assets/ của extension (gotchas 6j)
  output: ckanext-lakehouse_theme/%(version)s-lakehouse_theme.css
  contents:
    - css/lakehouse_theme.css

lakehouse_theme-js:
  filters: rjsmin
  output: ckanext-lakehouse_theme/%(version)s-lakehouse_theme.js
  contents:
    - js/lakehouse_theme.js
  extra:
    preload:
      - base/main          # phụ thuộc: nạp JS lõi của CKAN trước
```

Nạp asset trong `templates/base.html` (block `styles` và `scripts` đều có trong `base.html` của 2.11). Tên asset là `<tên thư viện trong add_resource>/<key trong yml>`:

```jinja
{% ckan_extends %}
{% block styles %}
  {{ super() }}
  {% asset 'lakehouse_theme/lakehouse_theme-css' %}
{% endblock %}
{% block scripts %}
  {{ super() }}
  {% asset 'lakehouse_theme/lakehouse_theme-js' %}
{% endblock %}
```

- **Đổi màu classic:**
  - Classic biên dịch màu thành mã hex cố định:
    - primary `#206b82`: link, nút, pagination, nav pills;
    - masthead và footer `#005d7a`, thanh tài khoản `#003647`;
    - accent `#187794`: view list, followee;
    - `#647a82`: menu bên trái đang chọn.
  - `lakehouse_theme.css` gom màu vào token `--lh-*` ở `:root`, rồi viết lại đúng các selector đó bằng thuộc tính trực tiếp.
  - Muốn đổi bộ nhận diện thì chỉ sửa các token.
  - Tìm selector dùng một mã màu: grep mã hex trong `~/ckan/default/src/ckan/ckan/public/base/css/main.css`.
- Classic phủ ảnh nền `bg.png` lên masthead, footer và dải `module-feeds`. Theme dùng shorthand `background:` để bỏ ảnh đó.
- Chữ trắng trên nền màu dùng token `--lh-500` trở xuống (đậm hơn), để đạt tương phản ≥ 4.5:1.

- Mỗi asset chỉ chứa **một loại** file (CSS hoặc JS).
- `{% asset %}` không in ra ngay tại chỗ. `base.html` gom lại rồi render ở cuối bằng `h.render_assets('style')` và `h.render_assets('script')`, nên **không** gọi `asset` sau điểm đó.
- Khi bật `debug`, asset được phục vụ riêng lẻ và không minify. Production thì asset được bundle và minify. Luôn viết source ở dạng chưa minify.
- JS theo mô-đun CKAN: `ckan.module('<theme>-x', function ($) { return { initialize: function () { ... } }; });`, gắn bằng `data-module="<theme>-x"`.
- Font Awesome **6.5.2** có sẵn: dùng `fa fa-<tên>`.

## Helper, trang mới, dịch
- **ITemplateHelpers:** logic nhỏ phục vụ hiển thị, ví dụ dataset mới nhất hay định dạng URL Trino. Gọi `{{ h.lakehouse_theme_recent_datasets(5) }}`. Đặt tên có tiền tố theme.
- **IBlueprint:** thêm route Flask mới (ví dụ `/gioi-thieu`) render template `<theme>/about.html`. Trang nội dung đơn giản thì cân nhắc dùng `ckanext-pages` (kiểm tra hỗ trợ 2.11, Q10).
- **Tiếng Việt:**
  - Core có sẵn bản dịch `vi` (`ckan.locale_default = vi`), nhưng catalog 2.11.6 chỉ dịch 617/1123 chuỗi.
  - Theme implement `ITranslation`. `.po` của theme vừa dịch chuỗi riêng, vừa bù những chuỗi core còn thiếu ở các trang chính (gotchas 6m).
  - Chuỗi mới trong theme dùng `_()`.
- **htmx** có sẵn cho các tương tác nhỏ mà không cần viết JS module.

## Checklist theme dự kiến
Điều chỉnh theo yêu cầu thật (Q2). Các mục dưới đây đều đã kiểm tra lại trên classic 2.11.6 bằng ảnh chụp ngày 2026-09-18.
- [x] Theme gốc (Q9) → ~~Midnight Blue (2026-09-14)~~ → **classic** (2026-09-18, 2.11 chỉ có classic)
- [x] Logo + favicon (placeholder SVG), `ckan.site_title`, `ckan.site_description`, `ckan.favicon` (2026-09-14)
- [x] Bảng màu teal gom vào token `--lh-*` (2026-09-14). CSS viết lại cho Bootstrap 5.1.3 của classic (2026-09-18); font dùng font hệ thống của classic
- [x] Header: thanh tài khoản, logo, menu có sẵn (Dữ liệu, Tổ chức, Nhóm, Thông tin), ô tìm kiếm dạng pill (của classic), ẩn ở trang đã có ô tìm kiếm (2026-09-18)
- [x] Trang chủ: hero giới thiệu portal + số dataset/tổ chức, ô tìm kiếm của classic, "Bộ dữ liệu mới cập nhật", org/nhóm nổi bật (2026-09-18)
- [x] Footer: giới thiệu, đơn vị/liên hệ (cấu hình), link Khám phá, OpenMetadata, Trino JDBC, CKAN API, attribution, chọn ngôn ngữ (2026-09-18)
- [x] Trang resource: hộp "Cách kết nối" cho `jdbc:trino://` (JDBC URL, Trino CLI, Python, nút sao chép) (2026-09-14; block `resource_read_url` có ở 2.11)
- [x] Tiếng Việt: `ITranslation` + `.po` bù chuỗi thiếu hoặc dịch vụng của catalog `vi` 2.11.6 ở header, trang chủ, dataset, resource, tổ chức (2026-09-18). Còn sót nhãn tiếng Anh ở trang quản trị/form, rà tiếp khi dùng
- [x] Responsive + tương phản trên classic: 400px và 1366px không tràn ngang; các cặp màu chính từ 5.54:1 trở lên (2026-09-18)
- [ ] Thay placeholder bằng bộ nhận diện thật khi có (Q2): logo SVG trong `logo_mark.html` + `favicon.svg`, token `--lh-*`, `ckanext.lakehouse_theme.organization_name` / `contact_email`

## Kiểm thử extension (tùy chọn)
- Cài `pip install -r ~/ckan/default/src/ckan/dev-requirements.txt`.
- Unit test thuần (không cần DB): `python -m pytest -o addopts="" -p no:ckan -p no:ckan_fixtures ckanext/lakehouse_theme/tests/test_helpers.py`.
- Chạy `pytest --ckan-ini=test.ini ckanext/<theme>/tests` cho test cần app, sau khi có DB test.
- CI (`.github/workflows/test.yml`) chạy trong `ckan/ckan-dev:2.11` với `ckan/ckan-solr:2.11-solr9` và `ckan/ckan-postgres-dev:2.11`.
- Test tối thiểu: plugin load được, trang chủ trả về 200 và có phần tử của theme.
