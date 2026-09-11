# Bối cảnh cụm K8s on-prem (Lakehouse)

> Nguồn: báo cáo nội bộ `Lakehouse_Kubernetes_Report.pdf` (snapshot, **chưa đối chiếu cluster thật**). Sau khi audit (phase-3 §3.1), cập nhật mục "Kết quả audit" và ghi ngày.
> **Không ghi mật khẩu/token vào file này.** Báo cáo có credential dạng plaintext (POC). Tra trong báo cáo khi cần, và dùng Secret cho bản thật.

## Cluster
- kubeadm, Kubernetes **v1.30.14**, CNI Calico v3.28, runtime **containerd**. Helm v3 đã cài.

| Node | IP | Vai trò |
|---|---|---|
| k8s-master | 10.1.117.91 | control-plane (taint NoSchedule) |
| k8s-worker1 | 10.1.117.88 | worker |
| k8s-worker2 | 10.1.117.235 | worker |

- **Namespace:** `lakehouse` (dùng chung cho toàn stack).
- **StorageClass:** chỉ có `local-path` (rancher.io/local-path): RWO, dữ liệu nằm trên đĩa của node, `WaitForFirstConsumer`. **Không có RWX.**
- **Expose:** không có Ingress/LoadBalancer; mọi thứ qua **NodePort** (30000–32767). NodePort mở trên mọi node IP.
- **Registry:** báo cáo không nhắc. Image kéo từ registry công khai.

## Dịch vụ đang có trong `lakehouse` (theo báo cáo)

| Service | Truy cập | Ghi chú cho CKAN |
|---|---|---|
| `postgres-service` | :5432 nội bộ, NodePort 30432 | `postgres:16-alpine`; pattern **mỗi app một DB + user** (vd. `openmetadata_db`, mục 7.2.3). CKAN sẽ dùng `ckan_default` (+ `datastore_default`) |
| `minio-service` | :9000, console NodePort 30090 | Ứng viên lưu file upload (cần extension S3) |
| Trino | NodePort 30800 | Resource URL: `jdbc:trino://10.1.117.91:30800/iceberg_curated/demo` |
| OpenMetadata | NodePort 30858 | Catalog kỹ thuật; đồng bộ metadata với CKAN (sau) |
| Airflow | NodePort 30808 | DAG export CSV `curated_outage_summary` → CKAN API |
| NiFi | NodePort 30909 / 30910 | |
| Kafka | NodePort 30092 | |

## CKAN hiện tại (mục 11.10, Case Study 2)
- Deployment `ckan`, image `ckan/ckan-base:2.10`, containerPort 5000, requests `500m` / `1Gi`.
- Service `ckan-service`, NodePort **30500**, tại http://10.1.117.91:30500.
- **Là stub:**
  - không có env cho Postgres, Solr hay Redis (báo cáo tự ghi cần thêm PostgreSQL + Solr);
  - không có trong danh sách `kubectl get svc` ở mục 10.7, nên có thể chưa từng được apply hoặc đang lỗi.
- Sẽ được thay bằng bản **2.12.0** (image `ckan-lakehouse`) ở GĐ3, sau khi hỏi chủ cluster (Q8).

## Quy tắc an toàn (mục 2.7 báo cáo)
Trước khi tạo tài nguyên phải chạy audit read-only:
- `get namespaces/nodes/storageclass`
- `helm list -A`
- `get crd`
- `auth can-i create deployments -n lakehouse`
- `auth can-i create namespaces`

## Hệ quả thiết kế cho CKAN
- 1 replica + `strategy: Recreate` cho mọi thứ có PVC. Pod bị ghim vào node chứa PV.
- `ckan.site_url` cố định `http://10.1.117.91:30500`. Người dùng phải vào bằng đúng URL này (xem gotchas).
- Solr/Redis dùng Service **ClusterIP**, không mở NodePort.
- Image tự build phải import vào containerd (`ctr -n k8s.io`) trên **cả 2 worker** nếu không có registry.

## Kết quả audit
_(chưa thực hiện — chờ kubeconfig)_
