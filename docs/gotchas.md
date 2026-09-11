# Bẫy đã biết & cách tránh

Thêm mục mới khi gặp bẫy mới. Ghi rõ **triệu chứng → nguyên nhân → cách xử lý**.

## Môi trường Windows / WSL / agent
1. **Git Bash tự đổi đường dẫn `/mnt/c/...`** thành `C:/Program Files/Git/mnt/c/...`.
   Thêm `MSYS_NO_PATHCONV=1` trước lệnh `wsl.exe`.
2. **Biến `$x` bị mất khi gọi `wsl.exe ... bash -c "..."`** vì escape nhiều lớp.
   Viết script `.sh` vào scratchpad rồi chạy file đó.
3. **sudo trong WSL cần mật khẩu**, agent không chạy non-interactive được.
   Viết script và để user tự chạy. Không hỏi mật khẩu.
4. **Cluster kind local (`kind-lakehouse`, `kind-lakehouse-lab`) báo connection refused.**
   Docker Desktop đang tắt; mở Docker Desktop trước.
5. **Code trên `/mnt/c` chậm hơn filesystem Linux.** Đôi khi reloader của `ckan run` không nhận thay đổi.
   Restart `ckan run`. Nếu vẫn khó chịu, chuyển repo vào `~/` và mở bằng VS Code Remote-WSL.
6. **Windows không mở được `localhost:5000`.**
   Chạy `ckan ... run -H 0.0.0.0` và dùng IP của WSL (`hostname -I`).

## CKAN
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
12. **`pip install` trong Dockerfile bị Permission denied.** Ở `ckan-base:2.12`, `/usr/local` (site-packages) thuộc **root** (bản 2.11 là `ckan-sys`), còn user mặc định là `ckan`.
    Dùng `USER root` khi cài, `USER ckan` khi chạy. Kiểm tra lại mỗi lần đổi base tag.
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

## Riêng CKAN 2.12
22. **Extension bên thứ ba lỗi import hoặc template.** 2.12 vừa ra (2026-08-26) nên nhiều extension chưa cập nhật. 2.12 cũng bỏ `PackageExtra`/`GroupExtra`, đổi `IGroupForm`.
    Kiểm tra README, CHANGELOG hoặc CI của extension trước khi cài (Q10). Ghim phiên bản.
23. **Khác phiên bản Python giữa local và image.** WSL dùng 3.12, còn `ckan-base:2.12.0` dùng 3.14 và không có biến thể Python khác. Một dependency có thể thiếu wheel cho 3.14 hoặc chạy khác đi.
    Bước kiểm thử GĐ2 sẽ phát hiện. Ghim version trong requirements của extension.
24. **`pip install git+...` hỏng trong Dockerfile.** Runtime image 2.12 là multi-stage, không có `git`/`g++`.
    Cài từ PyPI/wheel, hoặc `apt-get install` build deps tạm thời rồi xóa.
25. **Form POST của extension trả 400/403.** Thiếu CSRF token; 2.12 bắt buộc có.
    Thêm `{{ h.csrf_input() }}` vào form.
26. **Block override không hiện gì mà cũng không báo lỗi.** Block đó không tồn tại trong bộ template gốc đang dùng, ví dụ `header_site_search` không có trong Midnight Blue.
    Kiểm tra danh sách block của đúng bộ gốc (Q9).
27. **Grep block bỏ sót.** Nhiều block viết dạng `{%- block scripts %}`.
    Dùng regex `\{%-?\s*block [a-z_]+`.
