# Bẫy đã biết & cách tránh

Thêm mục mới khi gặp bẫy mới. Ghi rõ **triệu chứng → nguyên nhân → cách xử lý**.

## Môi trường Windows / WSL / agent
1. **Git Bash tự đổi đường dẫn `/mnt/c/...`** thành `C:/Program Files/Git/mnt/c/...`.
   Thêm `MSYS_NO_PATHCONV=1` trước lệnh `wsl.exe`.
2. **Biến `$x` bị mất khi gọi `wsl.exe ... bash -c "..."`** vì escape nhiều lớp.
   Viết script `.sh` vào scratchpad rồi chạy file đó.
3. **sudo trong WSL cần mật khẩu**, agent không chạy non-interactive được.
   Viết script và để user tự chạy. Không hỏi mật khẩu.
3a. **Restart server bằng `wsl.exe -e bash -c 'pkill -f "etc/ckan.ini run"; exec ckan -c ~/ckan/etc/ckan.ini run'` thoát với exit code 15.** `pkill -f` so pattern với cả dòng lệnh, mà dòng lệnh của chính `bash -c` cũng chứa `etc/ckan.ini run`, nên nó tự kill mình.
   Tách thành hai lệnh: lệnh kill chạy trước (pattern kiểu `"etc/ckan\.in[i] run"` để không khớp chính nó), rồi mới start ở một lệnh khác.
3b. **Ảnh chụp mobile bằng Chrome headless `--window-size=400,…` bị cắt lề phải, trông như trang tràn ngang.** Chrome không dàn trang hẹp hơn khoảng 500px, nhưng ảnh vẫn chỉ rộng 400px.
   Nhúng trang vào `<iframe style="width:400px">` trong một trang rộng hơn rồi chụp trang đó.
4. **Cluster kind local (`kind-lakehouse`, `kind-lakehouse-lab`) báo connection refused.**
   Docker Desktop đang tắt; mở Docker Desktop trước.
5. **Code trên `/mnt/c` chậm hơn filesystem Linux.** Reloader của `ckan run` thường **không** nhận thay đổi file `.py` (inotify không chạy qua `/mnt/c`). Template và CSS/JS ở chế độ debug thì vẫn nạp lại.
   Restart `ckan run` sau mỗi lần sửa Python. Nếu vẫn khó chịu, chuyển repo vào `~/` và mở bằng VS Code Remote-WSL.
6. **Windows không mở được `localhost:5000`.**
   Chạy `ckan ... run -H 0.0.0.0` và dùng IP của WSL (`hostname -I`).
6a. **`apt install` báo `Package 'git-core' has no installation candidate`** trên Ubuntu 24.04, script `set -e` dừng giữa chừng.
   `git-core` đã bị bỏ, dùng `git`. Tương tự `libmagic1` giờ là gói ảo, gói thật là `libmagic1t64`. Kiểm tra bằng `apt-cache policy <gói>` trước khi thêm gói vào script.
6b. **Docker Desktop đang chạy nhưng trong WSL `docker ps` báo `dial unix /var/run/docker.sock: no such file`.**
   Chưa bật WSL Integration cho distro. Docker Desktop → Settings → Resources → WSL Integration → bật Ubuntu → Apply & restart, rồi mở lại terminal WSL.
   Biến thể: **`docker: command not found`** dù `ls -l /usr/bin/docker` vẫn thấy file. Đó là symlink tới `/mnt/wsl/docker-desktop/cli-tools/usr/bin/docker`, mà mount này chỉ tồn tại khi **Docker Desktop đang chạy**; tắt app là symlink treo. Triệu chứng kéo theo: mọi lệnh `ckan -c` in một đống traceback `pysolr.SolrError … Connection refused` ở cổng 8983 (container Solr chết theo). Các traceback đó chỉ là **cảnh báo** — CKAN vẫn chạy tiếp — nhưng portal thì không tìm kiếm được. Mở Docker Desktop rồi `docker start ckan-solr`.

## CKAN
6c. **`pip install -e 'git+...#egg=ckan[requirements]'` báo `error: invalid-egg-fragment`.** Pip ≥ 25 không còn cho đặt extras trong egg fragment, mà docs CKAN vẫn hướng dẫn cú pháp này.
   `git clone --depth 1 --branch ckan-2.11.6 ... ~/ckan/default/src/ckan`, rồi `pip install -e "$HOME/ckan/default/src/ckan[requirements]"`. Muốn lên bản vá thì `git fetch --depth 1 origin tag ckan-2.11.x` và checkout tag đó.
6d. **`ckan config-tool ckan.ini "debug = true"` mà vẫn thấy `debug = false`.** Lệnh này mặc định ghi vào `[app:main]`, còn `debug` nằm ở `[DEFAULT]`, nên file có hai dòng trái nhau.
   Dùng `ckan config-tool ckan.ini -s DEFAULT "debug = true"`, rồi xóa dòng trùng trong `[app:main]`.
6e. **Mọi lệnh `ckan -c ...`, kể cả `--help`, đều crash `password authentication failed`.** CLI nạp app và kết nối DB trước khi chạy lệnh con, còn `ckan generate config` đặt sẵn mật khẩu mẫu trong `sqlalchemy.url`.
   Điền mật khẩu thật trước khi gọi bất kỳ lệnh `-c` nào. Nếu mật khẩu có ký tự `@ : / # % ?` thì phải **URL-encode**, ví dụ `@` thành `%40`.
6f. **Mất activity stream sau khi đặt lại `ckan.plugins`.** `ckan generate config` của 2.11 đặt sẵn `ckan.plugins = activity` (2.12 để trống). Ghi đè dòng đó mà quên `activity` thì trang dataset không còn tab hoạt động.
   Đặt tường minh, ví dụ `ckan.plugins = evntheme activity tracking text_view image_view`.
6g. **`ModuleNotFoundError: No module named 'flask_debugtoolbar'`** ở mọi lệnh `ckan -c` sau khi bật `debug = true`. `make_flask_stack` import toolbar khi debug bật, mà gói này chỉ có trong `dev-requirements.txt`.
   `pip install -r ~/ckan/default/src/ckan/dev-requirements.txt` (có cả `cookiecutter` cho `ckan generate extension` và `pytest`). Image production không bật debug nên không cần.
6h. **`db init` in `2 unapplied migrations for activity`** (gặp ở 2.12.0, 2.11 cũng vậy). `db init` chỉ xử lý schema lõi; mỗi plugin có migration riêng. Quên chạy thì trang dataset hoặc dashboard lỗi thiếu bảng `activity`.
   `ckan db upgrade -p activity`, rồi kiểm tra bằng `ckan db pending-migrations`. Bật thêm plugin có bảng riêng thì làm lại. Trên K8s, `prerun.py` của ckan-base cũng phải xử lý việc này (kiểm tra ở GĐ2).
6i. **CKAN không khởi động, `CkanConfigurationException: You provided an invalid value for ckan.base_public_folder`** (rồi tới `…base_templates_folder`) khi `ckan.ini` còn `public-midnight-blue` / `templates-midnight-blue` (cấu hình từ thời 2.12). `environment.py` của 2.11 chỉ nhận `public` / `templates`; Midnight Blue chỉ có từ 2.12.
   Xóa hai key đó hoặc đặt về `templates` / `public`. Ở 2.12 thì ngược lại: docstring vẫn ghi "chỉ nhận `templates`" nhưng code nhận cả Midnight Blue.
6j. **Mọi trang trả 500 `ValueError: Cannot determine url for …/assets/css/lakehouse_theme.css`** sau khi thêm bundle CSS có `filters: cssrewrite`. Ví dụ comment sẵn trong `webassets.yml` do `ckan generate extension` sinh ra có dòng này. `cssrewrite` chỉ biết URL của các thư mục public (`add_public_path` → `env.append_path`), còn thư viện `assets/` tạo bằng `toolkit.add_resource` thì không được map.
   Bỏ `cssrewrite` khỏi bundle của extension. Ảnh và font đặt trong `public/<theme>/…` và tham chiếu bằng đường dẫn tuyệt đối.
6k. **`pytest` báo `INTERNALERROR … password authentication failed for user "ckan_default"` kể cả với test không dùng DB.** Plugin pytest `ckan`/`ckan_fixtures` nạp `test-core.ini` và kết nối DB `ckan_test` ngay khi bắt đầu session.
   Test thuần (helper) chạy với `python -m pytest -o addopts="" -p no:ckan -p no:ckan_fixtures …`. Test cần app hoặc DB thì phải tạo DB test riêng (user tự chạy vì cần sudo). Việc này chưa làm.
6l. **Placeholder `<user>` biến mất trong đoạn code hiển thị trên trang.** Chữ viết thẳng trong `{% set x %}…{% endset %}` được coi là HTML an toàn nên không bị escape, và trình duyệt hiểu `<user>` là một thẻ.
   Truyền qua biểu thức: `{% set user = '<user>' %}` rồi dùng `{{ user }}`.
6m. **Còn chuỗi tiếng Anh khi `locale = vi`**, ví dụ "Search data" và "E.g. environment" ở trang chủ, "Last Updated" ở trang dataset. Catalog `vi` của 2.11.6 chỉ dịch 617/1123 chuỗi; 2.12.0 cũng chỉ khoảng một nửa. Một số chuỗi dịch sai hoặc vụng, ví dụ "CKAN API" thành "Giao diện người sử dụng CKAN", "{number} datasets found" thành "2 số bộ dữ liệu tìm thấy". Một số chuỗi chưa dịch, ví dụ "{num} Member" trên thẻ tổ chức.
   Theme implement `ITranslation` (`DefaultTranslation`). CKAN nạp catalog của plugin sau core, nên bản dịch trong `ckanext-lakehouse_theme.po` vừa lấp chỗ trống vừa sửa được chuỗi dịch sai. Sửa `.po` xong phải chạy `pybabel compile` và restart. Tìm chuỗi thiếu: trích `_('…')` từ template của trang rồi đối chiếu với `ckan/i18n/vi/LC_MESSAGES/ckan.po`, lấy những msgid có `msgstr ""`.
6n. **`ckan.ini` "tự" về mặc định**: `ckan.plugins` trống, `locale_default = en`, `sqlalchemy.url` về mật khẩu mẫu `pass`. Nguyên nhân là `ckan generate config <file>` **ghi đè không hỏi** khi file đã tồn tại. Đã xảy ra ngày 2026-09-17: mất cấu hình ngày 14/09.
   Không chạy `generate config` vào file đang dùng. Muốn xem mẫu mới thì sinh ra file khác rồi so sánh. Script `setup_step2_switch_to_2.11.sh` backup trước khi sinh lại.
6o. **Sau khi đổi sang 2.11, mọi lệnh `ckan -c` đều crash `SearchError`** vì phiên bản schema Solr. Lúc nạp app, CKAN gọi `check_solr_schema_version()`: 2.11 chỉ nhận schema `2.8`–`2.11`, còn core Solr cũ là schema 2.12. Nếu Solr tắt thì chỉ có cảnh báo, nên lỗi chỉ hiện khi container cũ đang chạy.
   Thay Solr **trước** khi chạy lệnh `ckan -c` nào: xóa container `ckan-solr` và volume `ckan_solr_data` (core lưu cấu hình trong volume), chạy `ckan/ckan-solr:2.11-solr9`, rồi `search-index rebuild`.
6p. **Override `footer_content` ở classic làm mất dòng "Powered by CKAN" và ô chọn ngôn ngữ.** Ở classic, `footer_attribution` và `footer_lang` nằm **bên trong** `footer_content`; Midnight Blue thì để chúng ngoài.
   Trong block override, gọi lại `{{ self.footer_attribution() }}` và `{{ self.footer_lang() }}`. `self.<block>()` render được cả block lồng trong block đã override.
6q. **Code 2.11 không chạy được trên DB đã lên schema 2.12.** Alembic của 2.11 không biết các revision 106–109, gồm bảng `file`, `file_owner`, `file_owner_transfer_history` và việc gộp `package_extra`/`group_extra`, nên `db init`/`db upgrade` không hạ xuống được.
   Hai cách:
   - Hạ bằng **code 2.12**, khi vẫn còn venv 2.12 và mật khẩu DB: `ckan db downgrade -v <revision head của 2.11>`. Các migration 106–109 đều có `downgrade()`.
   - Backup (`pg_dump -Fc`) → `ckan db clean --yes` → `db init` bằng 2.11. `db clean` reflect **mọi** bảng trong DB rồi drop, kể cả bảng 2.12 và `alembic_version`.

   Dự án chọn cách thứ hai (2026-09-18) vì DB chỉ có dữ liệu mẫu.
6r. **Đổi màu nút, pagination bằng `--bs-btn-bg`, `--bs-pagination-*` mà không có tác dụng** trên classic 2.11. 2.11.6 build bằng Bootstrap **5.1.3** (`package.json`: `^5.1.3`), trong khi biến CSS theo component chỉ có từ Bootstrap 5.2. 2.12 dùng `^5.3.6` cho cả classic lẫn Midnight Blue. Ở 5.1, `.btn-primary` đặt thẳng `background-color: #206b82`. Đừng tin comment đầu `main.css`: bản 2.12 vẫn ghi "v5.1.3". Kiểm tra bằng `grep -c -- '--bs-btn-bg' main.css`.
   Đặt thẳng thuộc tính cho từng trạng thái (`:hover`, `:focus`, `:active`, `.btn-check:checked + …`). Chỉ biến `--bs-primary-rgb` là còn tác dụng, vì các utility `.text-primary`/`.bg-primary` dùng nó. Tìm selector bằng cách grep mã hex trong `public/base/css/main.css`.
6s. **`ckan -c ~/ckan/etc/ckan-shot.ini run` crash `KeyError: 'formatters'`** ở 2.11, trong khi ở 2.12 vẫn chạy. CLI 2.11 (`ckan/cli/__init__.py` `load_config`) gọi `logging.config.fileConfig()` thẳng trên file truyền vào `-c`. File đó là ini con kế thừa bằng `use = config:…` nên không có section logging.
   Thêm vào ini con các section `[loggers]`, `[handlers]`, `[formatters]`, `[logger_root]`, `[logger_ckan]`, `[handler_console]`, `[formatter_generic]` (chép từ `ckan.ini`). Đã thêm vào `ckan-shot.ini` ngày 2026-09-18.
6t. **Link đặt trong `.module-heading` với `display: flex; justify-content: space-between` không sát lề phải mà nằm lơ lửng giữa.** Classic gắn clearfix `::after` (content rỗng) cho `.module-heading`. Trong flex container, pseudo-element đó thành flex item thứ ba, nên `space-between` chia khoảng cho cả nó.
   Đẩy phần tử cuối bằng `margin-left: auto` thay vì `space-between`, hoặc đặt `::after { display: none }`.
6u. **Mô tả tổ chức/nhóm tiếng Việt bị ngắt giữa âm tiết** ("kiểm tr / a portal"). Classic đặt `word-break: break-all` cho `.media-description` và `.context-info .description`.
   `word-break: normal; overflow-wrap: anywhere;`: xuống dòng ở khoảng trắng, chỉ bẻ những chuỗi quá dài không có khoảng trắng.
6v. **Dấu `:` thừa sau ô tìm kiếm, sau "Sắp xếp theo"…** Classic `main.css` có rule `label:after { content: ":" }` cho mọi `<label>`, kể cả label bọc input.
   Tắt nó cho các label của theme (`::after { content: none }`); evntheme gom việc này ở `_base.scss`.
6w. **Số liệu gom theo tổ chức toàn 0 dù tổng số dataset đúng.** `package_search` với `fl=owner_org` không trả `owner_org`: field này indexed nhưng **không stored**. Field được lưu là `organization`, tức *tên* tổ chức.
   Đặt `fl` gồm `organization` và gom theo tên. Cùng bẫy: xin `extras_<key>` trong `fl` thì kết quả trả về dưới tên `<key>` (CKAN bỏ tiền tố `extras_`).
6x. **Facet trên `extras_<key>` ra từ bị cắt kiểu `transact`, `refer`.** `extras_*` là field *text*: bị tách từ và stem.
   Facet trên chính `<key>`: CKAN cũng index mỗi extra thành field *string* cùng tên, qua dynamic field `*`. Ví dụ facet `data_type` của evntheme.
6y. **`pybabel extract` báo `Unknown extraction method 'ckan'`**, nên template không được trích. Có hai nguyên nhân:
   - Khi `pyproject.toml` có bảng `[project]`, setuptools bỏ qua `[options.entry_points]` trong `setup.cfg`.
   - Babel 2.15 tra entry point bằng `pkg_resources`, vốn không thấy bản cài editable kiểu mới.
   Khai báo extractor ngay trong `babel.cfg`, ở section `[extractors]` với dòng `ckan = ckan.lib.extract:extract_ckan`. Pattern `**/templates/**.html` phải được chạy với thư mục cha của `ckanext/`.
6z. **`AttributeError: module 'ckan.plugins.toolkit' has no attribute 'plugin_loaded'`.**
   Dùng `from ckan.plugins import plugin_loaded`. Trong template thì dùng `h.plugin_loaded()`.
6aa. **Lệnh CLI của plugin lỗi khi action cần sinh URL** (`package_show` sinh link tải về). CLI của CKAN nạp app nhưng không đẩy request context cho lệnh của plugin.
   Bọc thân lệnh trong `click.get_current_context().meta["flask_app"].test_request_context()` (xem `ckanext/evntheme/cli.py`).
6ab. **Nhật ký (activity) của dataset trống dù vừa tạo bằng script.** Hoạt động do *site user* tạo bị ẩn khỏi activity stream.
   Chạy action với `context={"user": "<sysadmin thật>", "ignore_auth": True}`.
6ac. **Nút theo dõi dùng form POST thường bị trả về một mảnh HTML.** Ở 2.11, `dataset.follow`/`unfollow` là endpoint cho htmx, trả `package/snippets/info.html`.
   Gọi bằng `fetch` kèm header `X-CSRFToken`, lấy token từ `<meta name="csrf_field_name">` (module `evn-follow`).
6ad. **Option của JS module nhận giá trị `true` thay vì chuỗi rỗng.** CKAN coi `data-module-foo=""` là thuộc tính boolean và đổi thành `true`, nên Leaflet crash (`t.replace is not a function`).
   Chỉ in thuộc tính khi có giá trị, và trong JS kiểm tra `typeof x === 'string'`.
6ae. **Override `header.html` làm mất tính năng của plugin khác**, ví dụ badge Dashboard của `activity` hay link login của plugin SSO. Nguyên nhân là viết lại toàn bộ markup tài khoản.
   Trong block override, gọi lại block core bằng `{{ self.header_account_logged() }}` / `{{ self.header_account_notlogged() }}`. Các block con đã được plugin khác override vẫn được áp dụng.
6af. **`h.render_datetime(date)` trả chuỗi rỗng.** Hàm này chỉ nhận `datetime`, không nhận `date`.
   Dùng `h.evn_date()` (Babel `format_date`, dạng `dd/MM/y` với `vi`).
6ah. **Mọi trang lỗi 500 `NotAuthorized` với trình duyệt còn phiên của một user vừa bị xóa**, trong khi khách (curl) vẫn vào được. CKAN từ chối mọi action của user đã xóa, kể cả `package_search`. Helper nào của theme gọi action bằng quyền người đang xem đều làm sập trang.
   Các lệnh đọc dữ liệu **công khai** (bộ đếm, danh sách có cache) đi qua `ckanext/evntheme/public.py`, dùng `ignore_auth`; `package_search` mặc định vẫn loại dataset private/draft. Cách này cũng giữ cache không phụ thuộc quyền của người truy cập đầu tiên. Dữ liệu theo người dùng (DataStore, activity, theo dõi) vẫn dùng context của họ.
6ag. **Workflow CI của extension không bao giờ chạy.** GitHub chỉ đọc `.github/workflows/` ở **gốc repo**, còn `ckanext-*/.github/` bị bỏ qua.
   Workflow của evntheme đặt ở `.github/workflows/evntheme.yml`, dùng `working-directory`.
6ai. **Tải logo lên ở `/ckan-admin/config` báo `No uploads allowed for object type admin`** (CKAN 2.11.6, định dạng nào cũng bị từ chối). Uploader đọc `ckan.upload.admin.types` / `ckan.upload.admin.mimetypes`, nhưng core chỉ khai báo hai key này cho `user` và `group`, còn `admin` thì bỏ trống.
   evntheme khai báo bù hai key này (`CORE_GAPS` trong `config.py`), mặc định cho phép PNG, JPEG, GIF, WebP. Nếu core đã tự khai báo thì theme bỏ qua. SVG cố ý không nằm trong danh sách: mở trực tiếp một file SVG là chạy script của nó trên origin của portal. Logo SVG nên đặt trong theme rồi trỏ `ckan.site_logo` tới đó.
   Cũng lưu ý: giá trị lưu từ trang admin nằm trong bảng `system_info` và **đè lên `ckan.ini`**. Đã upload rồi thì sửa `ckan.site_logo` trong ini/env sẽ không còn tác dụng, cho tới khi bấm "Remove" ở trang admin.
6aj. **Chạy lại `setup_step3_datastore.sh` thì `psql` báo `password authentication failed for user "datastore_default"`** dù vừa nhập mật khẩu. Script bỏ qua `createuser -P` khi role đã tồn tại (lần chạy trước tạo rồi), nhưng bước sau vẫn bảo nhập "mật khẩu vừa chọn" — mà lần này script **không** hỏi mật khẩu nào cả. Mật khẩu gõ vào không khớp với mật khẩu thật của role. Đây là bẫy chung của script "chạy lại được": phần *tạo* tài nguyên thì idempotent, phần *dùng* lại giả định vừa tạo xong. (2026-09-22)
   Script luôn hỏi mật khẩu rồi `alter role … password` (hoặc `create role`) trong mọi lần chạy, và tự ghi cả hai URL DataStore vào `ckan.ini`: `write_url` lấy mật khẩu sẵn có trong `sqlalchemy.url`, `read_url` URL-encode bằng `urllib.parse.quote` thay vì để người dùng tự mã hóa trong nano (bẫy 6e). Đặt mật khẩu qua biến của psql (`-v pw=…`, dùng `:'pw'`) để không vỡ khi mật khẩu có dấu nháy.
   Kèm theo đó: **`psql -c "… :'pw'"` báo `syntax error at or near ":"`**. psql chỉ thay biến cho SQL đọc từ **stdin hoặc `-f`**; chuỗi truyền qua `-c` được gửi thẳng cho server, `:'pw'` không phải cú pháp SQL nên lỗi. Dùng `printf '%s\n' "… :'pw';" | psql -v pw="$PW"`. Đã kiểm với mật khẩu chứa `'` và `@`: `:'pw'` bọc nháy và nhân đôi dấu nháy đúng.
6ak. **`pip install ckanext-<tên>` báo thành công, `pip show` thấy gói, nhưng CKAN vẫn `ModuleNotFoundError: No module named 'ckanext.<tên>'`** (gặp với `ckanext-xloader` 2.5.0, 2026-09-22). Bản cài **editable** của `ckan` và của extension trong repo sinh file `*-nspkg.pth`; các file này chạy lúc Python khởi động và **tạo sẵn module `ckanext` trong `sys.modules`** với `__path__` chỉ gồm đúng thư mục của chúng (`src/ckan/ckanext` và `…/ckanext-evntheme/ckanext`). Vì `ckanext` đã có sẵn trong `sys.modules`, import không bao giờ tra lại `sys.path`, nên `site-packages/ckanext/xloader/` **vô hình**. Kiểm tra bằng `python -c "import ckanext; print(ckanext.__path__)"`: thiếu `site-packages` là dính bẫy này.
   **Đúng cả trong image** (kiểm 2026-09-22): trong `ckan-lakehouse:0.1.0`, `ckanext.__path__` là `['/srv/app/src/ckan/ckanext', '/srv/app/src/ckanext-evntheme/ckanext']` — không có `site-packages`. Vì vậy Dockerfile cũng phải cài `-e`.
   Cài extension **từ source bằng `pip install -e`** (đúng cách CKAN docs và ckan-docker làm): bản editable đăng ký một finder trong `sys.meta_path`, được hỏi **trước** `__path__` của package cha, nên `ckanext.xloader` import được dù `ckanext.__path__` vẫn không đổi. Hệ quả cho GĐ2: mọi extension trong Dockerfile cũng phải `-e`, không dùng wheel (khớp với bẫy 15).
6al. **`ckan db upgrade -p <plugin>` chết với `alembic.util.exc.CommandError: No 'script_location' key found in configuration`** (gặp với `xloader`, 2026-09-22). Không phải lỗi cấu hình: extension đó **không có thư mục alembic** nào cả. CKAN dựng alembic config từ `ckanext/<plugin>/migration/<plugin>/`; không có thì `script_location` trống. `ckanext-xloader` không giữ bảng nào phía DB của CKAN — nó ghi thẳng vào DB DataStore — nên không cần migration.
   Chỉ chạy `db upgrade -p` cho plugin thật sự có `migration/<plugin>/`. Hàm `has_migrations` trong `setup_step3_datastore.sh` kiểm tra bằng `importlib.util.find_spec`. Lưu ý `spec.origin` là `None` với package **không có `__init__.py`** (đúng trường hợp `ckanext.evntheme`), nên phải đọc cả `spec.submodule_search_locations`, nếu không sẽ bỏ sót plugin có migration thật.
6am. **Cả portal đứng hình, mọi `curl` đều timeout, trong khi `ckan run` và worker vẫn sống.** Dev server của `ckan run` (Werkzeug) phục vụ **tuần tự**: một request chưa đóng là chặn hết phần còn lại. Đã gặp khi một lệnh `curl` bị treo 5 phút vì tiến trình cha chờ stdin (heredoc gửi qua `wsl.exe -e bash -c` bị ép thành **một dòng**, biến thể của bẫy 2).
   `ps -eo pid,etime,cmd | grep "[c]url"` tìm request cũ rồi `kill <pid>` **theo PID**, đừng `pkill -f` (bẫy 3a). Muốn gọi HTTP kèm heredoc/nhiều dòng thì viết script ra file rồi `wsl.exe -e bash <file>`. Luôn thêm `timeout` vào curl khi kiểm tra tự động. Trên K8s không gặp vì chạy uWSGI nhiều process.
7. **Thêm file template mới mà không thấy tác dụng.**
   Reloader chỉ theo dõi file đã biết. **Restart** `ckan run`.
8. **Đổi `ckan.ini` (site title, logo…) mà giao diện không đổi.**
   Giá trị đặt ở `/ckan-admin/config` lưu trong DB và ghi đè ini. Reset ở trang admin.
9. **Theme không được áp dụng hoặc bị plugin khác đè.**
   Kiểm tra thứ tự `ckan.plugins`: theme đứng đầu, `envvars` đứng cuối. Bật `debug` để xem template nào đang dùng.
10. **Redirect, CSS hoặc đăng nhập lỗi khi truy cập bằng IP/host khác `ckan.site_url`.**
    CKAN sinh URL tuyệt đối và cookie theo `site_url`. Luôn dùng đúng URL đó; với NodePort là `http://10.1.117.91:30500`, không phải IP worker.

## Image `ckan-base` / Docker
11. **Secret bị sinh lại mỗi lần container khởi động.** `start_ckan.sh` tự sinh `SECRET_KEY`, CSRF key và JWT secret khi `ckan.ini` còn trống. Trên K8s, `ckan.ini` nằm trong filesystem tạm của container, nên mỗi lần restart là sinh mới → **mọi API token (Airflow) và session bị vô hiệu**.
    Truyền secret cố định qua env/Secret. **Đã xác minh 2026-09-22 trên compose:** `start_ckan.sh` vẫn ghi một `SECRET_KEY` ngẫu nhiên vào `ckan.ini` (giá trị trong ini **khác** giá trị env), nhưng plugin `envvars` là `IConfigurer` nên chạy trong `update_config()` *trước* bước validate và đè lên ini. Sau `docker compose restart ckan`, cookie phiên (ký bằng `SECRET_KEY`) và API token cũ (ký bằng `api_token.jwt.*`) đều còn dùng được. `SECRET_KEY` và `WTF_CSRF_SECRET_KEY` nằm trong config declaration nên envvars giữ nguyên chữ HOA; key không được khai báo sẽ bị hạ thành chữ thường và **trượt**.
12. **`pip install` trong Dockerfile bị Permission denied.** Ở `ckan-base:2.11`, `/usr/local` (site-packages) thuộc `ckan-sys`, còn user mặc định là `ckan`. Bản `ckan-base:2.12` thì `/usr/local` thuộc `root`.
    Dùng `USER root` khi cài (đúng với cả hai bản), `USER ckan` khi chạy. Kiểm tra lại mỗi lần đổi base tag.
13. **Container kêu thiếu DataStore dù không dùng.** `CKAN__PLUGINS` mặc định của ckan-base có `datastore`.
    Luôn đặt `CKAN__PLUGINS` tường minh.
14. **Pod khởi động lâu, bị liveness kill vòng lặp.** `prerun.py` chờ DB rồi chạy `ckan db init` mỗi lần start.
    Dùng `startupProbe` dài; chỉ bật liveness sau khi đã start.
15. **Cài extension không editable thì template/asset biến mất** nếu `MANIFEST.in`/`package_data` khai báo thiếu.
    Dùng `pip install -e` như ckan-docker, hoặc kiểm tra kỹ package data.
15a. **Biến môi trường để RỖNG không giống với không đặt.** `CKANEXT__XLOADER__API_TOKEN=` trong `.env` làm plugin `envvars` đẩy chuỗi rỗng vào config; option này khai báo `not_missing` nên CKAN chết ngay với `Invalid configuration values provided: ckanext.xloader.api_token: Missing value`. Chết cả ở `ckan db init` trong `prerun.py`, nên container quay vòng restart và log chỉ hiện traceback của `db init` (2026-09-22).
    Trong `.env` thì **comment cả dòng** thay vì để trống (`#CKANEXT__XLOADER__API_TOKEN=`). Trên K8s: đừng khai key rỗng trong ConfigMap/Secret. Chỉ áp dụng cho option có validator `not_missing`; các key "để trống nghĩa là ẩn" của theme thì rỗng vẫn hợp lệ.
15b. **Container phụ (worker) chạy CKAN trần, không thấy theme lẫn extension.** `prerun.py` chỉ chạy trong container web, mà chính nó mới là chỗ ghi `CKAN__PLUGINS` vào `ckan.ini` bằng `config-tool`. `ckan.plugins` được đọc **trước** khi nạp plugin, mà `envvars` lại là một plugin, nên tự thân biến env không bật được plugin nào.
    Nướng danh sách vào ini lúc build (`RUN ckan config-tool ${CKAN_INI} "ckan.plugins = ${CKAN__PLUGINS}"`) **và** cho entrypoint của worker ghi lại từ env, để hai container luôn theo cùng một `CKAN__PLUGINS`.
15c. **Job XLoader lỗi `NameResolutionError` hoặc không gọi được callback khi worker ở container khác.** Payload của job mang `ckan_url` và `result_url` dựng từ `ckan.site_url` (URL của trình duyệt, ví dụ `http://localhost:5000`), mà container worker không giải được tên đó.
    Đặt `ckanext.xloader.site_url` (env `CKANEXT__XLOADER__SITE_URL`) bằng địa chỉ nội bộ, ví dụ `http://ckan:5000` trong compose hoặc `http://ckan-service:5000` trên K8s: `jobs.py` cho cả URL tải file (dòng 371) lẫn URL callback (dòng 542) đi qua `modify_input_url()`. Cũng nên trỏ `ckanext.xloader.jobs_db.uri` vào Postgres — mặc định là file SQLite trong `/tmp`, tức mỗi container một bản nhật ký job riêng.
15d. **Console báo `POST /_tracking 405 (METHOD NOT ALLOWED)` nhưng lượt xem vẫn được ghi.** Plugin `tracking` của 2.11 ghi nhận bằng hook `after_request` (`ckanext/tracking/middleware.py`), không đăng ký route Flask nào cho `/_tracking`, nên mã trả về luôn là 405. Kiểm chứng 2026-09-22: mỗi lần POST, `tracking_raw` tăng thêm một dòng.
    Không phải bẫy đóng gói, đừng "sửa". Khi soi console thì bỏ qua lỗi này.
15e. **`datastore set-permissions` mà không có superuser.** `prerun.py` chạy SQL đó bằng chính `CKAN_DATASTORE_WRITE_URL` (user `ckan_default`), trong khi tài liệu CKAN bảo phải là superuser — và nó nuốt lỗi, chỉ in "Could not initialize datastore".
    Chạy được **miễn là `ckan_default` sở hữu cả `ckan_default` lẫn `datastore_default`**: từ PostgreSQL 15, schema `public` thuộc `pg_database_owner` nên chủ DB revoke/grant được. Script `postgres-init` phải tạo DB với `OWNER ckan_default`. Kiểm chứng (2026-09-22): role read-only `SELECT` được `_table_metadata` nhưng `CREATE TABLE` bị `permission denied for schema public`. Trên K8s, `postgres-service` dùng chung: tạo DB với đúng owner này, nếu không phải nhờ DBA chạy SQL bằng superuser.

## Kubernetes (cluster công ty)
16. **`ErrImagePull` / `ImagePullBackOff` với image tự build.** Tag `latest` làm `imagePullPolicy` mặc định thành `Always`, trong khi chưa có registry.
    Dùng tag phiên bản + `IfNotPresent`, và import image vào **cả 2 worker** với `ctr -n k8s.io`.
17. **Pod Pending sau khi node chết, hoặc không lên node khác.** PV `local-path` có nodeAffinity tới node tạo ra nó.
    Chấp nhận (1 replica), hoặc chuyển file upload sang MinIO.
18. **Rollout treo khi deploy bản mới** vì pod mới và cũ tranh nhau PVC RWO.
    `strategy: Recreate`.
19. **Solr báo lỗi quyền ghi `/var/solr`.** Solr chạy uid 8983.
    Thêm `securityContext.fsGroup: 8983`. Tương tự CKAN dùng `fsGroup: 502` cho `/var/lib/ckan`.
20. **Lỗi `provided port is already allocated`.** NodePort 30500 đã thuộc `ckan-service` (stub).
    Thay chính service đó (cùng tên) sau khi chủ cluster đồng ý, không tạo service mới trùng cổng.
21. **Ảnh hưởng người khác trên cluster dùng chung.**
    Audit read-only trước. Dùng `--dry-run=server` trước mỗi lần `apply`. Tên tài nguyên có tiền tố `ckan-`.

21a. **Pod `ckan` bị `OOMKilled` (exit 137) chỉ vài giây sau dòng `WSGI app 0 ... ready`, dù cùng image chạy tốt trong compose** (gặp khi tập dượt trên kind, 2026-09-25).
    - Nguyên nhân: uWSGI cấp phát bảng theo giới hạn số file mở (`RLIMIT_NOFILE`) mà nó nhận từ runtime. Docker đặt 1048576. containerd trên node kind (và có thể cả node kubeadm, tùy `LimitNOFILE` của containerd và `fs.nr_open`) đặt **1073741816**, gấp khoảng 1000 lần, nên RAM vượt limit 2Gi.
    - Nhận biết: log in `detected max file descriptor number: 1073741816`.
    - Xử lý: `EXTRA_UWSGI_OPTS=--max-fd 65536` trong `k8s/base/config.env`, không phải build lại image. `start_ckan.sh` nối biến này vào lệnh uwsgi. Khi build image mới, cân nhắc đưa vào `ENV` của Dockerfile.

21b. **`kubectl apply` báo `spec.selector: Invalid value ... field is immutable` cho `deployment/ckan`** (dự đoán, chưa gặp). Bản stub 2.10 đã có Deployment tên `ckan` với selector khác. Selector của Deployment không sửa được sau khi tạo.
    `--dry-run=server` sẽ báo lỗi này trước. Phải xóa stub (sau khi chủ cluster đồng ý, Q8) rồi mới apply. Đừng đổi tên Deployment để lách, vì Service `ckan-service` và NodePort 30500 vẫn phải thay.

21c. **Secret/ConfigMap sinh ở overlay rơi vào namespace `default`**, pod trong `lakehouse` báo `secret "ckan-secrets-…" not found` (phòng trước). Trường `namespace:` của base không áp lên object do overlay sinh ra; thiếu trường này ở overlay thì `kubectl apply` dùng namespace của context.
    Cả hai overlay đều khai báo lại `namespace: lakehouse`.

21d. **Solr/Redis nhận biến lạ kiểu `SOLR_PORT=tcp://10.96.x.x:8983` và không khởi động** (phòng trước). K8s tự bơm biến môi trường cho **mọi Service trong namespace** (service links). Namespace `lakehouse` dùng chung, nên chỉ cần một Service tên `solr` hay `redis` của người khác là đủ gây lỗi.
    Mọi pod của CKAN đặt `enableServiceLinks: false`.

21e. **`kubectl rollout status` báo xong nhưng `curl` tới NodePort vẫn bị từ chối vài giây** (gặp khi tập dượt: `000` rồi `200` sau khoảng 4 giây). Endpoint của Service cập nhật sau khi pod ready, rồi kube-proxy mới đổi luật.
    Smoke test phải retry vài giây. Cộng thêm thời gian `prerun.py` với `strategy: Recreate`, mỗi lần deploy portal gián đoạn khoảng 30 giây. Nên deploy ngoài giờ.

21f. **`kind create cluster` âm thầm đổi `current-context` của `~/.kube/config`.** Lệnh `kubectl` gõ sau đó (không có `--context`) sẽ chạy vào cluster khác với dự định. Khi đã có kubeconfig của cluster công ty, lỗi này nguy hiểm.
    Mọi script trong `k8s/scripts/` bắt buộc `--context`. Sau khi tạo cluster kind thì `kubectl config use-context <cũ>`.

21g. **Mật khẩu đưa vào dòng lệnh `kubectl exec ... psql -c "CREATE ROLE ... PASSWORD '...'"` bị lộ ở nhiều chỗ**: argv trên máy mình, audit log của API server (lệnh exec nằm trong URL của request), và log của Postgres nếu câu lệnh lỗi.
    `prepare-postgres.sh` gửi SQL qua **stdin**, và gửi **SCRAM verifier** tính sẵn ở máy local thay cho mật khẩu thật.

21h. **`kubectl` trong WSL là v1.36, cluster công ty v1.30.** Chênh lệch 6 bản minor, vượt chính sách hỗ trợ ±1 của kubectl. Khi tập dượt trên kind 1.30.13, `apply -k`, `--dry-run=server`, `exec svc/…`, `create job --from=cronjob/…` và `rollout` đều chạy đúng.
    Nếu gặp lỗi lạ trên cluster thật, dùng kubectl 1.30 (tải binary riêng, gọi bằng đường dẫn đầy đủ) để loại trừ nguyên nhân này.

## Riêng CKAN 2.11
22. **Extension bên thứ ba lỗi import hoặc template.** Bản mới nhất của một extension có thể đã chuyển hẳn sang 2.12, ví dụ dùng tầng `ckan.files.*` hoặc bỏ phụ thuộc `PackageExtra`.
    Kiểm tra README, CHANGELOG hoặc CI của extension để lấy **phiên bản cuối còn hỗ trợ 2.11** (Q10), rồi ghim đúng phiên bản đó.
23. **Khác phiên bản Python giữa local và image.** WSL dùng 3.12, còn `ckan-base:2.11.6` dùng **3.10** và không có biến thể Python khác. Code extension dùng tính năng của 3.11+ (`tomllib`, `typing.Self`, `except*`…) sẽ chạy ở local nhưng lỗi trong image.
    Viết code tương thích 3.10. Bước kiểm thử GĐ2 sẽ phát hiện. Ghim version trong requirements của extension.
24. **Dockerfile viết theo 2.11 hỏng khi lên 2.12 sau này.** Image 2.11 là một stage, có `git`/`g++`/`wget`, nên `pip install git+...` và healthcheck `wget` chạy được. Runtime 2.12 là multi-stage, không còn các công cụ đó.
    Khi lên 2.12: cài từ PyPI/wheel hoặc `apt-get install` build deps tạm thời, và kiểm tra lại lệnh healthcheck.
25. **Form POST của extension chạy được ở 2.11 nhưng trả 400/403 ở 2.12**, hoặc khi đặt `ckan.csrf_protection.ignore_extensions = false`. 2.11 mặc định miễn CSRF cho blueprint của extension.
    Luôn thêm `{{ h.csrf_input() }}` vào form.
26. **Block override không hiện gì mà cũng không báo lỗi.** Block đó không tồn tại trong bộ template gốc đang dùng, ví dụ `featured_datasets` chỉ có ở Midnight Blue (2.12), classic 2.11 không có.
    Kiểm tra danh sách block trong `~/ckan/default/src/ckan/ckan/templates`.
27. **Grep block bỏ sót.** Nhiều block viết dạng `{%- block scripts %}`.
    Dùng regex `\{%-?\s*block [a-z_]+`.
