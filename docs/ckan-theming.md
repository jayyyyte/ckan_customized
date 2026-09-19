# Làm theme cho CKAN 2.11

## Nguyên tắc
- **Không bao giờ sửa file của core** (`~/ckan/default/src/ckan`). Mọi tùy biến đều nằm trong extension `ckanext-evntheme` (từ 2026-09-19, thay `ckanext-lakehouse_theme`; xem [README của extension](../ckanext-evntheme/README.md)).
- Override **mỏng**: file core chỉ override block ngoài cùng rồi gọi snippet riêng trong `templates/evntheme/…`. Khi cần giữ tính năng plugin khác thì gọi lại block core bằng `self.<block>()` (gotchas 6ae).
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

`ckanext-evntheme` (2026-09-19). Chi tiết từng thư mục, dữ liệu theme đọc và cách mở rộng: [README của extension](../ckanext-evntheme/README.md).

| Template core được override | Cách override | Markup thật nằm ở |
|---|---|---|
| `base.html` | `links`, `styles`, `bodytag`, `scripts` (+ `super()`) | — |
| `header.html` | `header_wrapper`. Menu tài khoản gọi lại `self.header_account_logged()` / `header_account_notlogged()` | `evntheme/header/` |
| `footer.html` | viết lại, giữ tên block `footer_links`, `footer_attribution`, `footer_lang` | `evntheme/snippets/language_links.html` |
| `home/index.html` | `content` → 4 block `evn_home_*` | `evntheme/home/` |
| `package/search.html`, `organization/read.html`, `group/read.html` | `content` | `evntheme/search/` (band, facets, results, group_header) |
| `snippets/package_item.html`, `package_list.html`, `facet_list.html` | block ngoài cùng | `evntheme/dataset/card.html`, checkbox facet |
| `package/read.html` | `content` (4 tab render sẵn, `?tab=`) | `evntheme/dataset/` |
| `package/resource_read.html` | `resource_read_url` (hộp Trino) | `evntheme/dataset/trino_connection.html` |
| `organization/index.html` | `content` | `evntheme/organization/` |
| *(mới)* `/mds` | blueprint `evntheme_mds` | `evntheme/mds/index.html` |

- File tĩnh trong `public/` được phục vụ từ gốc site, nên đặt trong thư mục con mang tên theme (`public/evntheme/…`) để không đè `/images/…` của core.
- Cấu hình riêng: `ckanext.evntheme.*`, khai báo trong `config.py` bằng `IConfigDeclaration`, xem bằng `ckan config declaration evntheme`.
- Mọi bảng mã → nhãn → màu (loại dữ liệu, chu kỳ, loại đơn vị, facet, tab, trạng thái MDS) nằm ở **`vocab.py`**; màu ở **`assets/scss/_tokens.scss`**.

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
evntheme-css:
  # KHÔNG dùng filters: cssrewrite: lỗi 500 với thư viện assets/ của extension (gotchas 6j)
  output: ckanext-evntheme/%(version)s-evn-theme.css
  contents:
    - css/evn-theme.css          # biên dịch từ scss/main.scss bằng `npm run build:css`, có commit

evntheme-js:
  filters: rjsmin
  output: ckanext-evntheme/%(version)s-evn-theme.js
  extra:
    preload:
      - base/main                # nạp JS lõi của CKAN trước
  contents:
    - js/evn-utils.js
    - js/modules/evn-tabs.js     # ... mỗi hành vi một module
```

Nạp asset trong `templates/base.html` (block `styles` và `scripts` đều có trong `base.html` của 2.11). Tên asset là `<tên thư viện trong add_resource>/<key trong yml>`, ví dụ `{% asset 'evntheme/evntheme-css' %}`.

- **SCSS:** màu, font, bo góc, đổ bóng chỉ khai báo ở `_tokens.scss` (CSS custom property). Sau đó là `_base`, `_components`, `layout/`, `pages/`.
  - Selector phần tử bọc trong `:where(.evn)` để có specificity thấp nhất.
  - Không dùng `!important` (có test kiểm).
- **Tô lại markup classic** cho các trang theme không vẽ lại (form, hồ sơ, quản trị): `pages/_core.scss`.
  - Classic biên dịch màu thành hex cố định: primary `#206b82`, masthead/footer `#005d7a`…
  - Phải đặt thẳng thuộc tính cho từng trạng thái (gotchas 6r).
  - Tìm selector dùng một mã màu bằng cách grep mã hex trong `~/ckan/default/src/ckan/ckan/public/base/css/main.css`.
- **Tương phản:** token "ink" (màu chữ) được làm đậm vừa đủ để đạt ≥ 4.5:1. Hex của mockup chỉ dùng cho nền và trang trí. Tỷ lệ đo được ghi cạnh từng token.
- Classic tự thêm `:` sau mọi `<label>` (gotchas 6v).

- Mỗi asset chỉ chứa **một loại** file (CSS hoặc JS).
- `{% asset %}` không in ra ngay tại chỗ. `base.html` gom lại rồi render ở cuối bằng `h.render_assets('style')` và `h.render_assets('script')`, nên **không** gọi `asset` sau điểm đó.
- Khi bật `debug`, asset được phục vụ riêng lẻ và không minify. Production thì asset được bundle và minify. Luôn viết source ở dạng chưa minify.
- JS theo mô-đun CKAN: `ckan.module('evn-x', function () { return { options: {...}, initialize: function () { ... } }; });`, gắn bằng `data-module="evn-x"`.
  - Option đọc từ `data-module-foo-bar` và đổi thành `this.options.fooBar`. Giá trị rỗng thì thành `true` (gotchas 6ad).
  - Mọi module là progressive enhancement: trang vẫn dùng được khi tắt JS.
- Font Awesome **6.5.2** có sẵn (`fa fa-<tên>`). Theme mới dùng sprite icon nét 1.5px `public/evntheme/icons.svg` qua macro `ui.icon('search')`.

## Helper, trang mới, dịch
- **ITemplateHelpers:** helper của theme tên `h.evn_*`, khai báo một chỗ trong `helpers/__init__.py`, logic chia theo module (`site`, `dataset`, `search`, `organization`, `datastore`, `trino`).
- **IBlueprint:** `/mds` (Danh mục chuẩn) và `/dataset/<id>/download-all`. Trang nội dung đơn giản thì cân nhắc dùng `ckanext-pages` (kiểm tra hỗ trợ 2.11, Q10).
- **Tiếng Việt:**
  - Core có sẵn bản dịch `vi` (`ckan.locale_default = vi`), nhưng catalog 2.11.6 chỉ dịch 617/1123 chuỗi.
  - Theme implement `ITranslation`. `.po` của theme vừa dịch chuỗi riêng, vừa bù những chuỗi core còn thiếu (gotchas 6m).
  - msgid viết bằng tiếng Anh, `_()` trong template, `N_()` cho hằng số Python.
  - Trích chuỗi bằng `pybabel extract -F babel.cfg` (gotchas 6y).
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
- [x] ~~Thay placeholder bằng bộ nhận diện thật~~ → **thay toàn bộ theme bằng `ckanext-evntheme` theo mockup của user (2026-09-19)**. Checklist phía trên là của `lakehouse_theme` cũ.

Checklist `ckanext-evntheme` (2026-09-19). Mỗi mục đều đã kiểm bằng ảnh chụp ở 1440px và 390px:
- [x] Khung trang: utility bar, header sticky với nav pill và số đếm động, menu tài khoản dùng lại block core, drawer trên mobile, footer 4 cột, chọn ngôn ngữ
- [x] Trang chủ: hero có tìm kiếm theo miền, chip gợi ý, 4 số liệu; thẻ miền dữ liệu; "Mới cập nhật" có sắp xếp; thẻ nhà phát triển, đơn vị đóng góp, danh mục chuẩn
- [x] Tìm kiếm: band + chip "Đang lọc", facet checkbox (tự gửi, có fallback "Áp dụng"), danh sách/lưới lưu trong localStorage, phân trang
- [x] Chi tiết: hero (badge, meta, tải tất cả dạng zip, theo dõi, chia sẻ, quản lý), 4 tab, sidebar thông tin/thẻ/liên quan; hộp Trino ở trang resource
- [x] Tổ chức: hero số liệu, tab lọc theo loại, tìm kiếm, đơn vị nổi bật, thẻ đơn vị có độ tươi; trang tổ chức và trang miền dùng layout tìm kiếm
- [x] Danh mục chuẩn: cây nhóm, header danh mục, bảng mã thụt lề theo cấp, lịch sử phiên bản, hệ thống tham chiếu, tải CSV/JSON
- [x] Tương phản ≥ 4.5:1 cho chữ; không tràn ngang ở 390px; hit target ≥ 44px trên mobile
- [x] Logo nhận mọi định dạng qua `ckan.site_logo`, upload ở `/ckan-admin/config` (2026-09-19, gotchas 6ai)
- [ ] Đưa logo EVN chính thức lên (Q2)

## Kiểm thử extension
- Cài `pip install -r ~/ckan/default/src/ckan/dev-requirements.txt`.
- Unit test thuần (không cần DB): `python -m pytest -o addopts="" -p no:ckan -p no:ckan_fixtures ckanext/evntheme/tests/test_units.py`.
- Test cần app: chạy `pytest --ckan-ini=test.ini ckanext/evntheme/tests/test_app.py` sau khi có DB `ckan_test` (`setup_step3_datastore.sh` tạo sẵn).
- CI: `.github/workflows/evntheme.yml` ở **gốc repo** (gotchas 6ag), chạy trong `ckan/ckan-dev:2.11` với `ckan/ckan-solr:2.11-solr9` và `ckan/ckan-postgres-dev:2.11`.
