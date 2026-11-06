# E6 — Ước tính chi phí compute

E6 không tạo tải hay thay đổi hạ tầng. `cost.py` tính từ node-seconds, giá và số job thành công **do người chạy cung cấp**, có ghi nguồn. Không tự lấy giá AWS, không đoán giá hay tuyên bố đây là hóa đơn. Các file `report.json` của thí nghiệm chỉ là nguồn tham khảo: tự đối chiếu vùng, loại node, NodeClaim/EC2 runtime, cửa sổ, job success và chất lượng dữ liệu trước khi nhập.

## Nhập dữ liệu

Từ `experiments/E6`, sao chép `input.example.txt` thành file cho mỗi lượt. Nội dung là JSON, ví dụ `cp input.example.txt c1.json`, rồi tự điền toàn bộ trường còn trống:

- `run_id`, `source_run`, `configuration`, `workload`: định danh và nguồn thật. Dùng cùng workload identifier cho các lượt so sánh được.
- `region`, `currency`, `price_date`, `price_source`: vùng, đơn vị tiền, ngày và nguồn giá theo thời điểm chạy; Spot dùng giá phù hợp thời gian thực hoặc ước tính what-if được ghi rõ.
- `window_start`, `window_end`: ISO 8601 có timezone (ví dụ hậu tố `Z`); cửa sổ bao gồm idle theo quy ước và phải giống độ dài giữa các cấu hình so sánh.
- `processed_success` và `success_count_method`: số job hoàn thành thành công và nguồn/cách tính. Giá trị xấp xỉ từ counter cần được ghi rõ và không chứng minh đối soát job ID.
- `instances`: mỗi nhóm loại instance/capacity type có `node_seconds` cộng trên các node, `hourly_price` cùng currency/giờ. `idle_node_seconds` là phần con của `node_seconds`, có thể `null` khi không biết. Nếu giá thay đổi theo thời gian, tách nhóm theo giá tương ứng.

Giữ `node_seconds` tính cho toàn bộ tập node đã chọn, kể cả node nhàn rỗi trong cửa sổ. Node Kubernetes hiện diện chỉ là proxy nếu không có thời gian EC2 thực. Không cộng Pod-minutes thành một khoản chi EC2 độc lập. Giá 0, quota, billing rounding, storage và network cần ghi rõ giả định nếu áp dụng; công thức ở đây không mô phỏng những khoản đó.

## Tính và so sánh

```bash
python ./cost.py c1.json
python ./cost.py c1.json c2.json c3.json --baseline ten-run-id-c1 --output comparison.json
```

Mỗi input là một lượt; input không bị thay đổi, output không ghi đè. Tool từ chối các lượt khác workload, region, currency hoặc độ dài cửa sổ và từ chối số thiếu, âm, không hữu hạn hoặc không có success. Nó tính:

- `compute_cost = Σ(node_seconds / 3600 × hourly_price)`;
- `cost_per_1000 = compute_cost / processed_success × 1000`;
- `idle_cost` chỉ khi có đủ idle của từng nhóm, là **một phần** compute cost;
- `saving_percent_per_1000_vs_baseline`, nếu chọn baseline có cost/1000 dương.

Giữ thời gian, sự kiện và lý do loại lượt; không gộp lượt không hợp lệ. Kết quả chưa bao gồm EKS control plane, NAT, RDS, đĩa, truyền dữ liệu hoặc các dịch vụ khác. Đối chiếu dữ liệu và phương pháp, rồi trình bày các khoản cố định/co giãn riêng. Không dùng Pod về 0 để kết luận tổng chi phí AWS về 0.
