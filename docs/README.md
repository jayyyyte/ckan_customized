# Tài liệu dự án CKAN Lakehouse Portal

| File | Nội dung | Khi nào đọc |
|---|---|---|
| [roadmap.md](roadmap.md) | Kế hoạch 3 giai đoạn, trạng thái, decision log, câu hỏi mở | **Luôn đọc đầu tiên** |
| [phase-1-local-source.md](phase-1-local-source.md) | Cài CKAN 2.12 từ source trên WSL2 + scaffold theme | Giai đoạn 1 |
| [phase-2-docker-packaging.md](phase-2-docker-packaging.md) | Đóng gói image `ckan-base:2.12.0` + theme, test bằng docker compose | Giai đoạn 2 |
| [phase-3-k8s-deploy.md](phase-3-k8s-deploy.md) | Audit + manifest + deploy lên cụm K8s công ty | Giai đoạn 3 |
| [ckan-overview.md](ckan-overview.md) | Kiến trúc CKAN, mô hình dữ liệu, config, CLI, API, extension hữu ích | Tra cứu |
| [ckan-theming.md](ckan-theming.md) | Cách làm theme: template, block, snippet, assets, helper, i18n | Khi làm theme |
| [cluster-context.md](cluster-context.md) | Thông tin cụm K8s on-prem (node, storage, service, CKAN stub) | Giai đoạn 3 |
| [gotchas.md](gotchas.md) | Các bẫy đã gặp / đã biết và cách tránh | Khi gặp lỗi lạ |

Phiên bản mục tiêu: **CKAN 2.12.0** (xem Decision log trong roadmap).

Nguồn chính: <https://docs.ckan.org/en/2.12/>, <https://docs.ckan.org/en/latest/changelog.html>, <https://github.com/ckan/ckan-docker-base> (thư mục `ckan-2.12`), <https://github.com/ckan/ckan-docker>, báo cáo nội bộ `Lakehouse_Kubernetes_Report.pdf` (mục 2.7, 7.2.3, 10.7, 11.10).
