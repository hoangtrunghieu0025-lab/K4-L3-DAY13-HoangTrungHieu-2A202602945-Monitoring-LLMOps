# Alert và Runbook

Mỗi alert dựa trên triệu chứng người dùng hoặc SLO, không dựa trên tên implementation nội bộ. Cấu hình máy đọc được: [`config/alert_rules.yaml`](../config/alert_rules.yaml). Cách điều tra chung: **Metrics -> Logs -> Traces**.

## Alert 1

- Tên: `high_latency_p95`
- Severity: P2
- Duration: 5 phút
- Kênh thông báo: Slack `#day13-alerts`
- SLI/SLO liên quan: `fast_successful_requests` (latency <= 2000ms, mục tiêu 99.5%/28 ngày)
- Điều kiện và thời gian duy trì: P95 `latency_ms` của `response_sent` > 2000ms liên tục 5 phút
- Ảnh hưởng tới người dùng: câu trả lời chậm, trải nghiệm chat kém, tiêu hao error budget
- Ba bước kiểm tra đầu tiên:
  1. Mở panel Latency, xác nhận P95/P99 và TTFT, ghi lại khoảng thời gian bắt đầu tăng.
  2. Lọc `data/logs.jsonl` theo `latency_ms > 2000`, lấy một `correlation_id`.
  3. Tìm trace có `metadata.correlation_id` đó trên Langfuse; xem span `retrieve-docs` hay `llm-generate` chiếm phần lớn thời gian.
- Mitigation tạm thời: nếu retrieval chậm thì tắt incident/giảm tải hoặc dùng fallback không retrieval; nếu LLM chậm thì rollback prompt label `production` về version trước.
- Owner: hoangtrunghieu

## Alert 2

- Tên: `high_error_rate`
- Severity: P1
- Duration: 5 phút
- Kênh thông báo: Slack `#day13-alerts`
- SLI/SLO liên quan: guardrail `error_rate_pct_max: 2` và `retrieval_success_rate_pct_min: 90`
- Điều kiện và thời gian duy trì: `request_failed / request_received` > 2% trong 5 phút
- Ảnh hưởng tới người dùng: request trả HTTP 500, người dùng không nhận được câu trả lời
- Ba bước kiểm tra đầu tiên:
  1. Panel Errors: xem breakdown theo `error_type` và retrieval success.
  2. Lọc log `event == "request_failed"`, đọc `error_type`, `tool_name`, lấy `correlation_id`.
  3. Mở trace tương ứng, tìm span có level ERROR (thường là `retrieve-docs`).
- Mitigation tạm thời: tắt incident `tool_fail` (`python scripts/inject_incident.py --scenario tool_fail --disable`), retry/fallback retrieval, rollback deploy gần nhất.
- Owner: hoangtrunghieu

## Alert 3

- Tên: `cost_budget_spike`
- Severity: P2
- Duration: 15 phút
- Kênh thông báo: Slack `#day13-alerts`
- SLI/SLO liên quan: guardrail `daily_cost_usd_max: 2.5`
- Điều kiện và thời gian duy trì: tổng `cost_usd` trong 1 giờ > 2.5 USD, hoặc chi phí trung bình mỗi request gấp đôi baseline, kéo dài 15 phút
- Ảnh hưởng tới người dùng: không ảnh hưởng trực tiếp nhưng vượt ngân sách, có thể dẫn tới giới hạn dịch vụ
- Ba bước kiểm tra đầu tiên:
  1. Panel Cost và Tokens: xác định `tokens_out` hay `tokens_in` tăng.
  2. Lọc log `response_sent` có `cost_usd` cao nhất, lấy `correlation_id` và `feature`.
  3. Mở trace, kiểm tra span `llm-generate` (usage, cost) và prompt version đang dùng.
- Mitigation tạm thời: rút ngắn prompt/giới hạn `max_tokens`, rollback prompt version, tắt incident `cost_spike`, giới hạn traffic của feature tốn kém.
- Owner: hoangtrunghieu
