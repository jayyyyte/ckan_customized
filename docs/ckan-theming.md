# Làm theme cho CKAN 2.12

## Nguyên tắc
- **Không bao giờ sửa file của core** (`~/ckan/default/src/ckan`). Mọi tùy biến đều nằm trong extension `ckanext-<theme>`.
- Override **đúng đường dẫn** template trong thư mục `templates/` của extension. Dùng `{% ckan_extends %}` và chỉ ghi đè những `block` thực sự cần đổi. Làm vậy thì nâng cấp CKAN ít bị vỡ.
- Cả hai bộ template gốc đều dựa trên **Bootstrap 5**. Bootstrap 3 đã deprecated, không dùng.

## Chọn theme gốc: classic hay Midnight Blue (Q9)

CKAN 2.12 có **hai** bộ template/asset gốc:

| | Classic | Midnight Blue |
|---|---|---|
| Thư mục | `templates` / `public` | `templates-midnight-blue` / `public-midnight-blue` |
| Trạng thái | Mặc định trong 2.12 | Mới ở 2.12, **sẽ thành mặc định từ CKAN 3.0** |
| Bật bằng | *(mặc định)* | `ckan.base_templates_folder = templates-midnight-blue` và `ckan.base_public_folder = public-midnight-blue` |

- Hai bộ có hệ block **gần như giống nhau** (kiểm với tag `ckan-2.12.0`).
- Khác biệt đã thấy:
  - `header.html` của Midnight Blue **không có** `header_site_search`, `header_site_search_label`, `header_account_settings_link`.
  - `home/index.html` của Midnight Blue có thêm block `featured_datasets`.
- Theme của ta dùng `{% ckan_extends %}`, nên sẽ kế thừa bộ gốc nào đang được cấu hình. **Chốt Q9 trước khi viết nhiều template**:
  1. Chạy CKAN với từng cấu hình.
  2. Xem trang chủ, trang dataset, trang org.
  3. Chọn một bộ.
- Mặc định đề xuất là Midnight Blue, để khỏi phải làm lại theme khi lên CKAN 3.0.

## Hai tầng tùy biến

| Tầng | Cách làm | Ví dụ |
|---|---|---|
| **1. Cấu hình** (không code) | `ckan.ini` hoặc trang `/ckan-admin/config` | `ckan.site_title`, `ckan.site_logo`, `ckan.site_description`, `ckan.favicon`, intro text, custom CSS ngắn |
| **2. Extension** | Override template, thêm CSS/JS, helper, trang mới | Header/footer mới, trang chủ mới, trang dataset có hướng dẫn kết nối Trino |

Giá trị đặt ở `/ckan-admin/config` được lưu trong DB và **ghi đè** `ckan.ini`.

## Cấu trúc extension

```
ckanext-<theme>/
├── setup.py / pyproject.toml     # entry point [ckan.plugins]: <theme> = ckanext.<theme>.plugin:<Theme>Plugin
└── ckanext/<theme>/
    ├── plugin.py
    ├── helpers.py                # hàm cho template (ITemplateHelpers)
    ├── templates/                # override + snippet riêng
    │   ├── base.html
    │   ├── header.html
    │   ├── footer.html
    │   ├── home/index.html
    │   └── <theme>/snippets/...  # snippet riêng, có tiền tố tên theme để tránh trùng
    ├── public/                   # file tĩnh phục vụ nguyên trạng: /images/logo.svg, favicon
    │   └── images/
    ├── assets/                   # CSS/JS qua webassets
    │   ├── webassets.yml
    │   ├── css/main.css
    │   └── js/<theme>.js
    └── i18n/                     # bản dịch chuỗi của extension (nếu cần)
```

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

{% snippet '<theme>/snippets/trino_hint.html', resource=res %}   {# snippet có biến riêng #}
```

- `h.*` là template helper (của core và của ta). `g.site_title`, `g.site_description` là cấu hình site.
- `_('...')` là chuỗi dịch được.
- Snippet chỉ nhận các biến được truyền vào, không thấy biến của template cha.
- **Form trong extension phải có CSRF:** thêm `{{ h.csrf_input() }}` bên trong mọi `<form method="post">`. Migration note của 2.12 yêu cầu điều này.

## Tìm template/block để override
1. Bật `debug = true`. **Footer debug** sẽ hiện tên các template đã render trang hiện tại.
2. Mở file gốc để xem block. Thay `templates` bằng `templates-midnight-blue` nếu Q9 chọn Midnight Blue:
   ```bash
   grep -noE '\{%-?\s*block [a-z_]+' ~/ckan/default/src/ckan/ckan/templates/header.html
   ```
   Regex phải bắt cả `{%-`, vì nhiều block viết dạng `{%- block scripts %}`.
3. Tạo file có cùng đường dẫn tương đối trong `ckanext/<theme>/templates/`, rồi **restart** `ckan run`, vì file mới thì reloader không nhận.

### Template hay override (block đã kiểm với tag `ckan-2.12.0`, bộ classic)

| Template | Vai trò | Block |
|---|---|---|
| `base.html` | Khung HTML ngoài cùng | `htmltag`, `headtag`, `meta`, `title`, `subtitle`, `links`, `styles`, `custom_styles`, `head_extras`, `bodytag`, `page`, `scripts`, `body_extras` |
| `page.html` | Bố cục trang | `skip`, `maintag`, `main_content`, `flash`, `toolbar`, `breadcrumb`, `breadcrumb_content`, `wrapper_class`, `pre_primary`, `secondary`, `secondary_content`, `primary`, `primary_content`, `page_header`, `content_action`, `content_primary_nav`, `page_primary_action`, `primary_content_inner`, `scripts` |
| `header.html` | Thanh trên cùng | `header_wrapper`, `header_account`, `header_account_logged`, `header_account_notlogged`, `header_dashboard`, `header_debug`, `header_logo`, `header_site_navigation`, `header_site_navigation_tabs`, `header_site_search` (không có ở Midnight Blue) |
| `footer.html` | Chân trang | `footer_content`, `footer_nav`, `footer_links`, `footer_links_ckan`, `footer_attribution`, `footer_lang` |
| `home/index.html` | Trang chủ | `primary_content`, `promoted`, `search`, `featured_group`, `featured_organization` (+ `featured_datasets` ở Midnight Blue) |
| `home/snippets/*.html` | Các phần của trang chủ | `promoted.html`, `search.html`, `featured_group.html`, `featured_organization.html` |
| `package/search.html` | Trang tìm kiếm dataset | 2.12 chỉ còn `primary_content`, `package_search_results_api`, `secondary_content`… Các block `page_primary_action`, `form`, `package_search_results_list` **đã chuyển đi chỗ khác**, xem file gốc |
| `snippets/package_item.html` | Thẻ dataset trong danh sách | |
| `package/read.html`, `package/resource_read.html` | Chi tiết dataset / resource | Chỗ hợp lý để thêm hướng dẫn kết nối Trino |

Những thay đổi 2.12 ảnh hưởng tới theme:
- `home/index.html` không còn chọn layout (`layout1/2/3`) như các bản rất cũ.
- `package/new_package_form.html` đã gộp vào template cha.
- Module `activity-stream.js` đã bị bỏ.
- Trang tìm kiếm dataset giờ tải kết quả **không reload trang** (htmx). Khi override kết quả tìm kiếm, cần giữ các thuộc tính/khối mà htmx dựa vào.

## CSS/JS với webassets

`assets/webassets.yml`:

```yaml
main-css:
  output: <theme>/%(version)s_main.css
  filters: cssrewrite
  contents:
    - css/main.css

main-js:
  output: <theme>/%(version)s_main.js
  filters: rjsmin
  extra:
    preload:
      - base/main          # phụ thuộc: nạp JS lõi của CKAN trước
  contents:
    - js/<theme>.js
```

Nạp asset trong `templates/base.html` (block `styles` và `scripts` đều có trong `base.html` của 2.12):

```jinja
{% ckan_extends %}
{% block styles %}
  {{ super() }}
  {% asset '<theme>/main-css' %}
{% endblock %}
{% block scripts %}
  {{ super() }}
  {% asset '<theme>/main-js' %}
{% endblock %}
```

- Mỗi asset chỉ chứa **một loại** file (CSS hoặc JS).
- `{% asset %}` không in ra ngay tại chỗ. `base.html` gom lại rồi render ở cuối bằng `h.render_assets('style')` và `h.render_assets('script')`, nên **không** gọi `asset` sau điểm đó.
- Asset được phục vụ riêng lẻ, không minify khi bật debug. 2.12 có thêm key riêng `ckan.webassets.debug` (mặc định `false`). Production thì asset được bundle và minify. Luôn viết source ở dạng chưa minify.
- JS theo mô-đun CKAN: `ckan.module('<theme>-x', function ($) { return { initialize: function () { ... } }; });`, gắn bằng `data-module="<theme>-x"`.
- Branding: override các selector chính (`.masthead`, `.site-footer`, `.btn-primary`, `.hero`…) và gom màu vào CSS custom properties ở `:root`. Midnight Blue có sẵn SCSS nguồn trong `public-midnight-blue/base/scss`, nên đọc để biết biến và class nó dùng.

## Helper, trang mới, dịch
- **ITemplateHelpers:** logic nhỏ phục vụ hiển thị, ví dụ dataset phổ biến hay định dạng URL Trino. Gọi `{{ h.<theme>_popular_datasets(5) }}`. Đặt tên có tiền tố theme.
- **IBlueprint:** thêm route Flask mới (ví dụ `/gioi-thieu`) render template `<theme>/about.html`. Trang nội dung đơn giản thì cân nhắc dùng `ckanext-pages` (kiểm tra hỗ trợ 2.12, Q10).
- **Tiếng Việt:** core có sẵn bản dịch `vi` (`ckan.locale_default = vi`). Chuỗi mới trong theme dùng `_()`. Nếu cần file dịch riêng: implement `ITranslation` và dùng babel (`extract_messages` / `compile_catalog`).
- **htmx** có sẵn cho các tương tác nhỏ mà không cần viết JS module.

## Checklist theme dự kiến
Điều chỉnh theo yêu cầu thật (Q2).
- [ ] Chốt theme gốc classic hay Midnight Blue (Q9)
- [ ] Logo + favicon (`public/images/`), `ckan.site_title`, `ckan.site_description`
- [ ] Bảng màu / font (CSS variables) cho nút, link, header, footer
- [ ] Header: logo, menu (Datasets, Organizations, Groups, Giới thiệu), ô tìm kiếm
- [ ] Trang chủ: hero giới thiệu Lakehouse portal, ô tìm kiếm, dataset nổi bật / thống kê
- [ ] Footer: thông tin đơn vị, liên hệ, liên kết tới OpenMetadata / tài liệu Trino
- [ ] Trang dataset/resource: hộp "Cách kết nối" cho resource Trino JDBC
- [ ] Tiếng Việt mặc định, rà các chuỗi chưa dịch
- [ ] Responsive (mobile) và contrast cơ bản

## Kiểm thử extension (tùy chọn)
- Cài `pip install -r ~/ckan/default/src/ckan/dev-requirements.txt`.
- Chạy `pytest --ckan-ini=test.ini ckanext/<theme>/tests`.
- Test tối thiểu: plugin load được, trang chủ trả về 200 và có phần tử của theme.
