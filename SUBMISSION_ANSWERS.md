# Câu Trả Lời Nộp Bài Lab 28

## 1. Trade-offs trong kiến trúc AI platform

Kiến trúc tách local infrastructure và Kaggle GPU để cân bằng chi phí và khả năng tính toán. Local Docker Compose chạy Kafka, Prefect, Redis, Qdrant, Prometheus, Grafana và API Gateway nên dễ debug, restart và quan sát. Kaggle chỉ đảm nhiệm model/embedding serving qua tunnel, giúp tận dụng GPU mà không bắt buộc local có GPU. Trade-off là network latency và tunnel availability; API Gateway vì vậy có timeout ngắn và fallback response để giữ service healthy.

## 2. Xử lý mất kết nối Local + Kaggle

API Gateway gọi vLLM qua `VLLM_URL` với timeout cấu hình bằng `VLLM_TIMEOUT_SECONDS`. Khi upstream Kaggle chậm, lỗi HTTP, hoặc tunnel mất kết nối, gateway trả về local fallback thay vì crash. Embedding ingestion script dùng timeout và `raise_for_status()` để fail rõ ràng khi service embedding không sẵn sàng.

## 3. Kafka giúp decouple components

Kafka topic `data.raw` làm điểm đệm giữa ingestion và processing. Script ingestion chỉ cần publish event, Prefect flow consume và ghi parquet vào Delta Lake mà không phụ thuộc trực tiếp vào producer. Cách này giúp thêm consumer khác như vector indexing hoặc feature pipeline mà không cần sửa producer.

## 4. Observability

API Gateway expose `/metrics` bằng `prometheus-fastapi-instrumentator`. Prometheus scrape API Gateway và Qdrant, Grafana được provision sẵn datasource Prometheus và dashboard `Lab28 AI Platform Overview`. Dashboard hiển thị API Gateway status, request rate và scrape targets. Prefect UI hiển thị deployment, flow run, task run và logs của pipeline Kafka to Delta.

## 5. Xử lý khi service crash

Docker Compose giúp restart/recreate từng service riêng lẻ. Nếu Qdrant crash, API Gateway bỏ qua vector context và vẫn có thể trả lời qua LLM/fallback. Nếu Kafka crash, ingestion sẽ fail rõ ràng và Prefect flow không ghi batch mới, nhưng API Gateway/observability vẫn tiếp tục hoạt động. Redis bị lỗi chỉ ảnh hưởng feature lookup/push, không làm gateway crash.
