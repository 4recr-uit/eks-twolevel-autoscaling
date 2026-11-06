# Công cụ đọc kết quả lịch sử

Các lượt E1 HPA/KEDA cũ giữ nguyên ID và hiện nằm tại `experiments/results/E1-legacy`. `init.py`, HPA và workload lịch sử được giữ từ bản trước. Ba file `collect.py`, `report.py`, `compare.py` bị ghi đè trong lúc tái cấu trúc; chúng được khôi phục từ Git HEAD và bổ sung lại hỗ trợ HPA/KEDA và workload phiên bản 4. Đã kiểm thử và đọc được report cũ, nhưng không thể bảo đảm phục hồi chính xác mọi thay đổi chưa commit. Không dùng công cụ này để chạy E3 mới.
