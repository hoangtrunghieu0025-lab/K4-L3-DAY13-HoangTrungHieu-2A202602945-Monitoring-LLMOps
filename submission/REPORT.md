# Báo cáo cá nhân — K4-L3A Day 13 Monitoring & LLMOps

> Mỗi học viên hoàn thiện một file duy nhất này. Khi dẫn evidence, dùng đường dẫn tương đối, ví dụ `evidence/07-trace-waterfall.webp`.

## 1. Thông tin học viên

- **Họ và tên:** Hoàng Trung Hiếu
- **MSSV:** 2A202602945
- **Lớp:** K4-L3A
- **Repository URL:** https://github.com/hoangtrunghieu0025-lab/K4-L3-DAY13-HoangTrungHieu-2A202602945-Monitoring-LLMOps
- **Commit SHA cuối:** `76b19df` (commit chứa toàn bộ source, config, evidence CP0–CP3 và report)
- **Challenge ID:** `day13-k4-l3a-monitoring-llmops-v1`
- **Tên project Langfuse cá nhân:** `day13-k4-l3a-<MSSV>` 

## 2. Evidence index

Điền đúng đường dẫn tới evidence thực tế. Có thể đổi tên hoặc dùng nhiều ảnh nếu cần.

| Evidence | Đường dẫn |
|---|---|
| Pytest cuối | `evidence/01-pytest.png` |
| Log validator | `evidence/02-log-validator.png` |
| Dashboard validator | `evidence/03-dashboard-validator.png` |
| Structured log | `evidence/04-structured-log.png` |
| PII redaction | `evidence/05-pii-redaction.webp` |
| Trace list | `evidence/06-trace-list.webp` |
| Trace waterfall | `evidence/07-trace-waterfall.webp` |
| Trace metadata | `evidence/08-trace-metadata.webp` |
| Prompt versions | `evidence/09-prompt-versions.webp` |
| Prompt rollback | `evidence/10-prompt-rollback-production-v2.webp`, `evidence/10-prompt-rollback-production-v1.webp` |
| Dashboard runtime | `evidence/11-dashboard-overview.webp` |
| Incident metric | `evidence/12-incident-metric.webp` |
| Incident log | `evidence/13-incident-log.png` |
| Incident trace | `evidence/14-incident-trace.webp` |

## 3. Kết quả kỹ thuật

| Nội dung | Baseline | Kết quả cuối | Nhận xét |
|---|---|---|---|
| `validate_logs.py` | 30/100 (thiếu correlation_id, enrichment) | 100/100 | 47 correlation ID khác nhau, 0 lỗi field |
| `validate_dashboard.py` | 6/6 panel | 6/6 panel | contract vốn đã hợp lệ; dashboard runtime dựng bằng `scripts/build_dashboard.py` |
| `pytest` | 22 passed | 25 passed | thêm test CCCD, thẻ, passport |
| Số traces hợp lệ | 0 (tracing tắt) | 47 trace `lab-agent-run` (khớp 47 correlation ID trong log) | mỗi trace có 2 span con, tạo từ project cá nhân |
| Số PII leak | 0 (validator baseline) | 0 | request thử chứa email, SĐT, thẻ, CCCD đều bị che |
| Latency P95 / TTFT P95 | ~155 ms (chưa tracing) | 1083 ms / 50 ms | P99 4315 ms do request đầu sau mỗi lần restart (tải prompt Langfuse); P50 152 ms |
| Retrieval success rate | 100% | 100% | không có incident |

## 4. Logging và PII

- **Cách tạo/nhận và truyền correlation ID:** `CorrelationIdMiddleware` xóa contextvars, nhận `x-request-id` hoặc sinh `req-<8-hex>`, bind vào structlog và trả lại trong header `x-request-id` cùng `x-response-time-ms`. `agent.run` nhận cùng ID và đặt vào trace metadata.
- **Các metadata được ghi vào structured log:** `correlation_id`, `user_id_hash` (SHA-256 cắt 12 ký tự), `session_id`, `feature`, `model`, `env`, cùng `latency_ms`, `ttft_ms`, `tokens_in/out`, `cost_usd`, `quality_score`, `tool_name`, `tool_success`.
- **Cách bảo đảm PII được scrub trước khi ghi:** `scrub_event` được đăng ký trong `structlog` processors trước `JsonlFileProcessor`, nên dữ liệu đã được che trước khi ghi file. Message người dùng chỉ vào log qua `summarize_text` (đã scrub). Pattern: email, SĐT VN, CCCD, thẻ, passport, từ khóa địa chỉ.
- **Cách kiểm chứng kết quả:** `validate_logs.py` 100/100, `pytest` 25 test, và gửi thủ công một request chứa email, SĐT, thẻ, CCCD; log chỉ còn `[REDACTED_*]` (evidence 05).

## 5. Tracing và prompt versioning

- **Cách xác nhận traces do chính tôi tạo trong project cá nhân:** Các trace xuất hiện trong project Langfuse `day13-k4-l3a-2A202602945` sau khi chạy `load_test.py` với key của tôi; lọc theo `metadata.correlation_id` khớp với log local.
- **Cấu trúc root/retrieval/generation observations:** Root `lab-agent-run` (agent) → `retrieve-docs` (retriever, output `doc_count`) và `llm-generate` (generation, có model, prompt link, usage input/output, cost). Không capture raw prompt/output; chỉ preview đã scrub.
- **Cách nối trace với log:** Cùng `correlation_id`: lọc `data/logs.jsonl` theo ID, rồi trong Langfuse lọc `metadata.correlation_id equals <ID>`. Ví dụ `req-5d62e27c` ↔ trace `213db14ba156e8a6a12a3db0ffade8d1`.
- **Prompt name:** `day13-chat`
- **Version/label baseline:** v1, labels `baseline` + `production`
- **Version/label candidate:** v2, label `candidate` (thêm dòng "Answer concisely in at most 3 sentences.")
- **Trace ID của mỗi version:** cùng input "How should alerts be designed?": baseline `req-ca610e2b` (v1), candidate `req-777ac7ed` (v2). Sau đổi label: production→v2 `req-2cad7acc`, rollback production→v1 `req-1c383bab` (tìm trace bằng correlation_id).
- **Cách promote và rollback `production`:** Dùng `update_prompt(name, version, new_labels=["production"])` của Langfuse SDK để chuyển label sang v2, restart API (prompt cache 60s) rồi chạy request; sau đó chuyển label về v1 và chạy lại. Trace hiển thị `Prompt: day13-chat - v2` rồi `- v1`.

## 6. Dashboard, SLO và alerts

- **Dashboard và sáu panel:** `python scripts/build_dashboard.py` dựng `dashboard/dashboard.html` từ `data/logs.jsonl` theo `config/dashboard.yaml`: latency (P50/P95/P99 + TTFT), traffic, errors (+ retrieval success), cost, tokens, quality; time range 60 phút, refresh 30s, có đơn vị và threshold.
- **SLO và lý do chọn:** 99.5% request `response_sent` có latency ≤ 2000ms (mục tiêu 99.5%/28 ngày). Baseline P95 khoảng 0.16–0.35s. Ban đầu chọn 3000ms nhưng thử `rag_slow` (retrieval +2.5s) cho latency server ~2650ms, dưới ngưỡng nên không bị phát hiện; tôi hạ xuống 2000ms để bắt được sự cố này.
- **Cách tính error budget:** (100 − 99.5)% = 0.5%; 28 ngày × 24 × 60 = 40 320 phút → 201.6 phút budget.
- **Ba alert và runbook tương ứng:** `high_latency_p95` (P95 > 2000ms, 5m), `high_error_rate` (> 2%, 5m), `cost_budget_spike` (> 2.5 USD/giờ, 15m); chi tiết ở `docs/alerts.md`, cấu hình ở `config/alert_rules.yaml`.

## 7. Điều tra challenge

- **Challenge ID:** `day13-k4-l3a-monitoring-llmops-v1`
- **Khoảng thời gian điều tra:** 2026-09-29 08:38:34Z–08:38:48Z (15:38:34–15:38:48 giờ VN). Baseline cùng 5 query lúc 08:38:29Z–08:38:31Z, chưa bật incident.
- **Triệu chứng từ metrics:** 5/5 request của feature `monitoring` có `latency_ms` 2652–2654 ms so với baseline ~152 ms (tăng ~17 lần), vượt ngưỡng 2000 ms của challenge và SLO của tôi. `ttft_ms` vẫn 50 ms, `error` = 0%, `tool_success` = true, `tokens`/`cost` không đổi: hệ thống chậm nhưng không lỗi, và chậm trước khi LLM bắt đầu sinh.
- **Log line và correlation ID liên quan:** `req-54254ef2` (`data/logs.jsonl`, `event: response_sent`, `feature: monitoring`, `latency_ms: 2654`, `ttft_ms: 50`, `tool_success: true`). Bốn request còn lại: `req-ba290370`, `req-0b3c310b`, `req-99b7e5e4`, `req-d677777c` cùng ~2653 ms.
- **Trace ID và span gây ảnh hưởng:** Trace `8b69c2efead894193b0cc01f0c177b4b` (correlation `req-54254ef2`): `lab-agent-run` 2.654 s, trong đó `retrieve-docs` 2.502 s (94%) và `llm-generate` 0.152 s. Baseline `req-b1bf7174` (trace `8d1a07321c705e262cc64b109518578d`): `retrieve-docs` ~0 s, `llm-generate` 0.152 s. Cả 5 trace incident đều có `retrieve-docs` ≈ 2.50 s, `llm-generate` không đổi.
- **Root cause:** Bước retrieval bị chậm thêm ~2.5 s (incident `rag_slow`: `time.sleep(2.5)` trong `retrieve()`), không phải LLM. Bằng chứng nhất quán: latency tăng ≈ đúng 2.5 s, TTFT không đổi, `llm-generate` giữ 0.152 s, span `retrieve-docs` chiếm 94% thời gian. Vì `retrieve()` chạy đồng bộ trong handler nên các request còn xếp hàng chờ nhau: client thấy đến ~13 s dù server đo 2.65 s.
- **Fix action:** Tắt incident (`python scripts/inject_incident.py --disable`); latency về ~152 ms. Trong sự cố thật: kiểm tra vector store/retrieval backend, đặt timeout và fallback cho retrieval.
- **Preventive measure:** Giữ alert `high_latency_p95` (P95 > 2000 ms trong 5 phút, runbook `docs/alerts.md#alert-1`); thêm span/metric riêng cho retrieval latency và timeout; đổi `retrieve()` sang async/threadpool để một retrieval chậm không chặn các request khác.

## 8. Giải thích và tự đánh giá

- **Một quyết định kỹ thuật quan trọng và lý do:** Hạ ngưỡng SLO/alert latency từ 3000 ms xuống 2000 ms sau khi chạy thử `rag_slow`: incident chỉ làm latency lên ~2650 ms nên ngưỡng 3000 ms không phát hiện được. Ngưỡng 2000 ms vẫn cách xa baseline ~150–350 ms. Đây là quyết định dựa trên dữ liệu đo, không phải chọn số tùy ý.
- **Một lỗi/blocker đã gặp:** Test `test_agent_records_prompt_version...` vỡ khi thêm span con vì client giả không có `start_as_current_observation`; và `pytest` chạy bằng Python hệ thống báo thiếu `structlog`.
- **Cách tìm nguyên nhân và xử lý:** Đọc traceback rồi bọc span con bằng helper `_observation` (no-op khi client không hỗ trợ); chạy pytest bằng `.venv\Scripts\python.exe`.
- **Cách hiểu luồng Metrics → Logs → Traces:** Dashboard/metric phát hiện triệu chứng và khoảng thời gian (P95 tăng lúc 08:38Z). Lọc `data/logs.jsonl` trong khoảng đó để lấy `correlation_id` của request bất thường (`req-54254ef2`). Dùng cùng ID tìm trace trong Langfuse rồi so sánh span với request baseline để khoanh vùng nguyên nhân.
- **Vai trò của prompt version, token/cost, SLO hoặc rollback trong vận hành LLM:** Prompt version gắn vào trace cho biết request dùng prompt nào, nên khi chất lượng/chi phí đổi có thể đối chiếu và rollback nhanh bằng cách đổi label `production` mà không cần deploy code. Token/cost cho biết prompt mới có làm tăng chi phí không. SLO và error budget biến “chậm” thành ngưỡng đo được để quyết định khi nào phải cảnh báo.
- **Điều quan trọng nhất đã học:** Metric cho biết *có* vấn đề và từ lúc nào, log cho biết *request nào*, còn trace chỉ ra *bước nào*. Ở challenge, chỉ khi đặt ba thứ cạnh nhau (latency +2.5 s, TTFT không đổi, span `retrieve-docs` 2.50 s) mới kết luận chắc chắn là retrieval chứ không phải LLM.
- **Hạn chế hoặc phần chưa hoàn thành, nếu có:** Dashboard là trang HTML tĩnh dựng từ log local (không real-time trong Langfuse). Panel latency theo contract dùng ngưỡng 3000 ms nên vẫn báo OK trong lúc incident (P95 2654 ms); ngưỡng 2000 ms chỉ áp dụng cho SLO/alert. Retrieval đồng bộ khiến request xếp hàng, chưa sửa trong code. Chưa có Slack webhook thật cho alert.

## 9. Checklist trước khi nộp

- [ ] Kết quả và evidence thuộc commit SHA cuối.
- [x] Tất cả ảnh/output mở được bằng đường dẫn tương đối.
- [x] Incident evidence nối đúng metric → log → trace.
- [ ] Trace/prompt evidence thuộc project Langfuse cá nhân và ảnh không lộ key/secret.
- [ ] Repository chạy lại được theo README.
- [x] Không có secret, API key, PII thô hoặc evidence của người khác/lớp khác.
- [ ] URL repo và commit SHA cuối đã được nộp trên LMS/Codelabs.
