# Tài liệu dự án CKAN Lakehouse Portal

| File | Nội dung | Khi nào đọc |
|---|---|---|
| [roadmap.md](roadmap.md) | Kế hoạch 3 giai đoạn, trạng thái, decision log, câu hỏi mở | **Luôn đọc đầu tiên** |
| [phase-1-local-source.md](phase-1-local-source.md) | Cài CKAN 2.11 từ source trên WSL2 (+ chuyển từ bản cài 2.12) + scaffold theme | Giai đoạn 1 |
| [phase-2-docker-packaging.md](phase-2-docker-packaging.md) | Đóng gói image `ckan-base:2.11.6` + theme, test bằng docker compose | Giai đoạn 2 |
| [phase-3-k8s-deploy.md](phase-3-k8s-deploy.md) | Manifest kustomize, audit, tạo DB, đưa image lên node, deploy lên cụm K8s công ty; kết quả tập dượt trên kind (§3.10) | Giai đoạn 3 |
| [ckan-overview.md](ckan-overview.md) | Kiến trúc CKAN, mô hình dữ liệu, config, CLI, API, extension hữu ích | Tra cứu |
| [ckan-theming.md](ckan-theming.md) | Cách làm theme: template, block, snippet, assets, helper, i18n | Khi làm theme |
| [cluster-context.md](cluster-context.md) | Thông tin cụm K8s on-prem (node, storage, service, CKAN stub), điều cần xác minh khi audit | Giai đoạn 3 |
| [gotchas.md](gotchas.md) | Các bẫy đã gặp / đã biết và cách tránh (K8s: mục 16–21h) | Khi gặp lỗi lạ |
| [../Bao-cao-ky-thuat-Cong-du-lieu-EVN.docx](../Bao-cao-ky-thuat-Cong-du-lieu-EVN.docx) | Báo cáo kỹ thuật cho EVN (40 trang): bài toán, công nghệ, use case, triển khai, nghiệm thu, đánh giá, hướng mở rộng. Bản chụp trạng thái ngày 2026-09-25 | Khi trình bày / nghiệm thu |

Phiên bản mục tiêu: **CKAN 2.11.6** (quay về từ 2.12.0 ngày 2026-09-18, xem Decision log trong roadmap).

Script ở gốc repo (user tự chạy trong WSL):
- `setup_step1_system.sh`: gói hệ thống, cần sudo.
- `setup_step2_switch_to_2.11.sh`: CKAN 2.11.6 + config + Solr + DB + theme `evntheme`, không cần sudo.
- `setup_step3_datastore.sh`: DataStore + XLoader + DB test, cần sudo (đã chạy 2026-09-22).

Script GĐ3 trong `k8s/`. Mọi script bắt buộc `--context`, chạy trong WSL:
- `k8s/scripts/audit.sh`: audit chỉ đọc cụm công ty.
- `k8s/scripts/make-secrets.sh <overlay>`: sinh `k8s/overlays/<overlay>/secrets.env` (không commit).
- `k8s/scripts/prepare-postgres.sh`: tạo 2 role + 2 DB trên `postgres-service`. Mặc định chỉ đọc; `--apply` để tạo; `--print` để xuất SQL cho chủ Postgres chạy hộ.
- `k8s/overlays/kind/smoke-test.sh`: 47 kiểm tra đầu-cuối; chỉ chạy được với context `kind-*`.

Theme: [`ckanext-evntheme/README.md`](../ckanext-evntheme/README.md).

Nguồn chính: <https://docs.ckan.org/en/2.11/>, <https://docs.ckan.org/en/latest/changelog.html>, <https://github.com/ckan/ckan-docker-base> (thư mục `ckan-2.11`), <https://github.com/ckan/ckan-docker>, báo cáo nội bộ `Lakehouse_Kubernetes_Report.pdf` (mục 2.7, 7.2.3, 10.7, 11.10).
