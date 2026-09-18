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
5. **Code trên `/mnt/c` chậm hơn filesystem Linux.** Đôi khi reloader của `ckan run` không nhận thay đổi.
   Restart `ckan run`. Nếu vẫn khó chịu, chuyển repo vào `~/` và mở bằng VS Code Remote-WSL.
6. **Windows không mở được `localhost:5000`.**
   Chạy `ckan ... run -H 0.0.0.0` và dùng IP của WSL (`hostname -I`).
6a. **`apt install` báo `Package 'git-core' has no installation candidate`** trên Ubuntu 24.04, script `set -e` dừng giữa chừng.
   `git-core` đã bị bỏ, dùng `git`. Tương tự `libmagic1` giờ là gói ảo, gói thật là `libmagic1t64`. Kiểm tra bằng `apt-cache policy <gói>` trước khi thêm gói vào script.
6b. **Docker Desktop đang chạy nhưng trong WSL `docker ps` báo `dial unix /var/run/docker.sock: no such file`.**
   Chưa bật WSL Integration cho distro. Docker Desktop → Settings → Resources → WSL Integration → bật Ubuntu → Apply & restart, rồi mở lại terminal WSL.

## CKAN
6c. **`pip install -e 'git+...#egg=ckan[requirements]'` báo `error: invalid-egg-fragment`.** Pip ≥ 25 không còn cho đặt extras trong egg fragment, mà docs CKAN vẫn hướng dẫn cú pháp này.
   `git clone --depth 1 --branch ckan-2.11.6 ... ~/ckan/default/src/ckan`, rồi `pip install -e "$HOME/ckan/default/src/ckan[requirements]"`. Muốn lên bản vá thì `git fetch --depth 1 origin tag ckan-2.11.x` và checkout tag đó.
6d. **`ckan config-tool ckan.ini "debug = true"` mà vẫn thấy `debug = false`.** Lệnh này mặc định ghi vào `[app:main]`, còn `debug` nằm ở `[DEFAULT]`, nên file có hai dòng trái nhau.
   Dùng `ckan config-tool ckan.ini -s DEFAULT "debug = true"`, rồi xóa dòng trùng trong `[app:main]`.
6e. **Mọi lệnh `ckan -c ...`, kể cả `--help`, đều crash `password authentication failed`.** CLI nạp app và kết nối DB trước khi chạy lệnh con, còn `ckan generate config` đặt sẵn mật khẩu mẫu trong `sqlalchemy.url`.
   Điền mật khẩu thật trước khi gọi bất kỳ lệnh `-c` nào. Nếu mật khẩu có ký tự `@ : / # % ?` thì phải **URL-encode**, ví dụ `@` thành `%40`.
6f. **Mất activity stream sau khi đặt lại `ckan.plugins`.** `ckan generate config` của 2.11 đặt sẵn `ckan.plugins = activity` (2.12 để trống). Ghi đè dòng đó mà quên `activity` thì trang dataset không còn tab hoạt động.
   Đặt tường minh, ví dụ `ckan.plugins = lakehouse_theme activity text_view image_view`.
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
    Truyền secret cố định qua env/Secret (xem phase-2, mục cần xác minh).
12. **`pip install` trong Dockerfile bị Permission denied.** Ở `ckan-base:2.11`, `/usr/local` (site-packages) thuộc `ckan-sys`, còn user mặc định là `ckan`. Bản `ckan-base:2.12` thì `/usr/local` thuộc `root`.
    Dùng `USER root` khi cài (đúng với cả hai bản), `USER ckan` khi chạy. Kiểm tra lại mỗi lần đổi base tag.
13. **Container kêu thiếu DataStore dù không dùng.** `CKAN__PLUGINS` mặc định của ckan-base có `datastore`.
    Luôn đặt `CKAN__PLUGINS` tường minh.
14. **Pod khởi động lâu, bị liveness kill vòng lặp.** `prerun.py` chờ DB rồi chạy `ckan db init` mỗi lần start.
    Dùng `startupProbe` dài; chỉ bật liveness sau khi đã start.
15. **Cài extension không editable thì template/asset biến mất** nếu `MANIFEST.in`/`package_data` khai báo thiếu.
    Dùng `pip install -e` như ckan-docker, hoặc kiểm tra kỹ package data.

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
