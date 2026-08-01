# Quản lý nhà trọ

Ứng dụng web Flask quản lý phòng trọ, chạy trên trình duyệt tại `http://localhost:5000`. Dữ liệu được lưu trong MySQL của XAMPP.

## Chức năng

- Đăng nhập và phân quyền quản trị viên/người thuê.
- Tổng quan số phòng, công nợ, hóa đơn chưa thanh toán và doanh thu tháng.
- Quản lý phòng: thêm, sửa, xóa, tìm kiếm và lọc trạng thái.
- Quản lý người thuê: thông tin cá nhân, phòng, tiền cọc và tệp CCCD/hợp đồng.
- Quản lý điện nước: thêm, sửa, xóa; tự tính tiền; kiểm tra chỉ số mới không thấp hơn chỉ số cũ.
- Kế thừa chỉ số điện/nước: tự lấy chỉ số mới của kỳ gần nhất làm chỉ số cũ kỳ hiện tại. Có thể nhập thủ công khi cần.
- Quản lý dịch vụ: thêm, sửa, xóa; tính theo phòng hoặc theo người.
- Hóa đơn: tạo, sửa, xóa, thu tiền, lịch sử thanh toán, in trực tiếp và xuất PDF.
- Chọn nhiều dịch vụ cho từng hóa đơn; từng khoản dịch vụ được lưu trong chi tiết hóa đơn.
- Người thuê chỉ xem, in, tải PDF hóa đơn của chính phòng mình và chọn phương thức thanh toán. Quản trị viên xác nhận thanh toán.

## Quyền truy cập

| Vai trò | Quyền |
| --- | --- |
| Quản trị viên | Toàn quyền quản lý dữ liệu, tạo tài khoản người thuê và xác nhận thanh toán. |
| Người thuê | Chỉ xem hóa đơn thuộc phòng đang thuê, in/tải PDF và chọn phương thức thanh toán. |

## Cài đặt

1. Cài Python 3.12 hoặc mới hơn.
2. Mở XAMPP Control Panel và khởi động dịch vụ **MySQL**.
3. Vào `http://localhost/phpmyadmin`, chọn **Import**, sau đó chọn tệp `database.sql` trong thư mục dự án.
4. Mở PowerShell trong thư mục dự án và chạy:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Nếu lệnh `py` không có, dùng đường dẫn Python đã cài hoặc lệnh `python` thay thế.

5. Mở `http://localhost:5000`.

## Tài khoản ban đầu

```text
Tên đăng nhập: admin
Mật khẩu: admin123
```

Sau khi đăng nhập, vào mục **Tài khoản** để tạo tài khoản cho mỗi người thuê. Chọn đúng người thuê, nhập tên đăng nhập và mật khẩu. Tài khoản này tự động bị giới hạn vào hóa đơn của phòng người thuê đó.

## Cấu hình MySQL

Mặc định ứng dụng kết nối XAMPP bằng:

```text
Host: localhost
Database: boarding_house
User: root
Password: để trống
```

Nếu MySQL có mật khẩu hoặc thông số khác, đặt biến môi trường trước khi chạy:

```powershell
$env:DATABASE_URL = "mysql+pymysql://root:MAT_KHAU@localhost/boarding_house?charset=utf8mb4"
python app.py
```

## Quy trình sử dụng

1. Tạo phòng.
2. Thêm người thuê và gán phòng.
3. Tạo tài khoản người thuê trong mục **Tài khoản** nếu cần.
4. Khai báo các dịch vụ như Internet, rác hoặc giữ xe.
5. Hàng tháng nhập chỉ số điện nước. Khi chọn phòng/tháng, chỉ số cũ sẽ được gợi ý từ kỳ trước.
6. Tạo hóa đơn, chọn các dịch vụ phòng sử dụng và kiểm tra tổng tiền.
7. Xác nhận thanh toán tại mục Hóa đơn, sau đó in hoặc xuất PDF.

## Lưu ý vận hành

- Cần giữ MySQL trong XAMPP đang chạy trước khi mở ứng dụng.
- Dữ liệu tệp tải lên được lưu tại `static/uploads/`.
- Đổi mật khẩu `admin` trước khi dùng thực tế.
- Sao lưu database `boarding_house` thường xuyên bằng Export trong phpMyAdmin.
