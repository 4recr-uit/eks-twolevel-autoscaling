# Khôi phục sau E3

Hoàn tất lúc 2026-11-07T14:42:12.000466+00:00.

Đã khôi phục đúng bản sao trước E3: Orders worker chọn NodePool e1-orders, desired/Ready=3/3, ScaledObject e1-orders-sqs min=3/max=10 và HPA thuộc KEDA. Đây là trạng thái E1 trước E3, không phải baseline trước E1 vì bản sao cũ đó không còn. Orders API đủ replica Ready.

Đã gỡ controller/auth E3 và release e3-capacity; không còn node/NodeClaim E3 hoặc EC2 hoạt động mang tag NodePool E3 của cluster. Node hệ thống, KEDA/Karpenter controller, monitoring, dữ liệu DB và 12 thư mục kết quả được giữ. Các port-forward có sẵn được giữ để người dùng tiếp tục xem kết quả.

Nguồn kiểm tra: [cleanup.json](../results/E3/cleanup.json).
