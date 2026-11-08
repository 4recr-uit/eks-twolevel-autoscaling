# Biểu đồ E1

Bộ script đọc các lượt trong `experiments/results/E1` và tạo hình tại `experiments/E1/figures/config-N` hoặc `figures/comparison`. Không cần kết nối cluster và script không sửa dữ liệu kết quả gốc. Các file PNG phù hợp đưa vào slide; SVG có thể phóng lớn.

## Cài đặt và chạy

Các lệnh dưới đây chạy từ `experiments/E1` trong Git Bash trên Windows. Nếu môi trường ảo chưa có, tạo và cài dependency một lần:

```bash
python -m venv ../../.generated/e1-visualize-venv
source ../../.generated/e1-visualize-venv/Scripts/activate
python -m pip install -r visualize-scripts/requirements.txt
```

Ở những lần sau chỉ cần kích hoạt môi trường, rồi vẽ:

```bash
source ../../.generated/e1-visualize-venv/Scripts/activate
python visualize-scripts/plot_e1.py --config 1
```

Mặc định script chọn `r01` và `r02` của cả hai nhánh cho mỗi profile. Hình có sẵn sẽ không bị ghi đè trừ khi chỉ định:

```bash
python visualize-scripts/plot_e1.py --config 1 --overwrite
```

Ví dụ chỉ tạo Burst, hoặc chọn các lượt khi cả Warm và Elastic đều có đủ những lượt đó:

```bash
python visualize-scripts/plot_e1.py --config 2 --profile burst
python visualize-scripts/plot_e1.py --config 3 --attempts 1 2 3
```

Config 2 và 3 hiện chỉ có Burst, nên để tạo các hình từ dữ liệu hiện có:

```bash
python visualize-scripts/plot_e1.py --config 2 --profile burst --overwrite
python visualize-scripts/plot_e1.py --config 3 --profile burst --overwrite
python visualize-scripts/plot_burst_comparison.py --overwrite
```

Lệnh cuối so sánh Burst của cả ba config và yêu cầu cùng workload, cấu hình worker và cửa sổ báo cáo. Bỏ `--overwrite` nếu không muốn ghi đè hình đã tồn tại; dùng `--attempts 1 2` để chọn lượt.

Xem các tùy chọn đường dẫn bằng `python visualize-scripts/plot_e1.py --help`. Trên Linux/macOS, đường dẫn kích hoạt môi trường là `../../.generated/e1-visualize-venv/bin/activate`.

## Các hình

| Tên | Nội dung |
|---|---|
| `step_summary` | p95 E2E, đỉnh queue và node-phút theo nhánh cho Step |
| `burst_summary` | Các chỉ số tương tự cho Burst |
| `step_timeline` | Queue, worker desired/Ready và số node E1 theo thời gian ở từng lượt Step |
| `burst_timeline` | Các chuỗi tương tự cho Burst |
| `conclusion_average` | Trung bình của từng chỉ số, so sánh Warm và Elastic theo từng profile |
| `comparison/burst_comparison_average` | Trung bình Burst của cả ba mức worker, gồm p95 E2E, đỉnh queue, Ready Pod-phút và node-phút |

Mỗi hình được xuất thành `.png` và `.svg`; nhãn trong hình bằng tiếng Anh. Cột trong hình tổng hợp và kết luận là trung bình số học của các lượt; p95 trung bình **không phải** p95 gộp của mọi job. Hình kết luận chỉ được tạo khi chạy cả hai profile; `--profile step` hoặc `--profile burst` không cập nhật hình này. Trục thời gian timeline dùng thời điểm bắt đầu workload từ report làm mốc, còn tốc độ tải được đánh dấu theo kịch bản cấu hình.

Queue là tổng visible và in-flight từ các mẫu SQS gần đúng; các đường nối chỉ giúp theo dõi xu hướng và bị ngắt khi thiếu mẫu dài. Node-phút dùng node Kubernetes thuộc `e1-orders` trong cửa sổ 60 giây trước đến 60 giây sau tải, không phải chi phí EC2. Do Step và Burst có thời lượng khác nhau, chỉ so sánh node-phút Warm/Elastic trong cùng profile. Counter success và CPU không được dùng để vẽ so sánh chính do giới hạn dữ liệu đã nêu trong README E1.

Config 1/2/3 tương ứng 1/3/5 worker tối thiểu; các report cũ thiếu trường config được đọc là Config 1. Script chỉ vẽ các lượt cùng config, workload và cấu hình worker. Trước khi vẽ, script kiểm tra metadata, trạng thái collector và mẫu đầu gần lúc bắt đầu: Warm có 4 node E1 Ready, Elastic không có node E1 rảnh, các worker tối thiểu đều Ready, queue và DLQ bằng 0 theo mẫu. Elastic Config 3 có thể cần nhiều hơn một node. Script từ chối các lượt không khớp và không tự đổi `validity: not_assessed` thành hợp lệ; vẫn cần đánh giá thủ công.
