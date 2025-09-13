# 📧 Email Setup Guide

Hướng dẫn thiết lập email cho Trading Alert System để nhận thông báo và khuyến nghị giao dịch hàng ngày.

## 🚀 Thiết lập nhanh

### Bước 1: Chạy script thiết lập
```bash
python setup_email.py
```

### Bước 2: Làm theo hướng dẫn
Script sẽ hướng dẫn bạn:
- Nhập email gửi
- Nhập mật khẩu ứng dụng
- Nhập email nhận
- Cấu hình SMTP

### Bước 3: Kiểm tra
Script sẽ tự động kiểm tra kết nối và gửi email test.

## 📋 Thiết lập thủ công

### 1. Tạo file .env
Sao chép `.env.example` thành `.env`:
```bash
cp .env.example .env
```

### 2. Cấu hình Gmail (Khuyến nghị)

#### Bước 1: Bật xác thực 2 bước
1. Vào [Google Account Security](https://myaccount.google.com/security)
2. Bật "2-Step Verification"

#### Bước 2: Tạo App Password
1. Vào [App Passwords](https://myaccount.google.com/apppasswords)
2. Chọn "Mail" và thiết bị của bạn
3. Sao chép mật khẩu 16 ký tự

#### Bước 3: Cập nhật .env
```env
# Gmail Configuration
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SENDER_EMAIL=your-email@gmail.com
SENDER_PASSWORD=your-16-char-app-password
RECIPIENT_EMAILS=recipient1@gmail.com,recipient2@gmail.com
EMAIL_ENABLED=true
EMAIL_USE_TLS=true
```

### 3. Cấu hình email khác

#### Outlook/Hotmail
```env
SMTP_SERVER=smtp-mail.outlook.com
SMTP_PORT=587
SENDER_EMAIL=your-email@outlook.com
SENDER_PASSWORD=your-password
```

#### Yahoo Mail
```env
SMTP_SERVER=smtp.mail.yahoo.com
SMTP_PORT=587
SENDER_EMAIL=your-email@yahoo.com
SENDER_PASSWORD=your-app-password
```

## 🧪 Kiểm tra cấu hình

### Kiểm tra kết nối
```python
from jobs.email_service import EmailService
from utils.config_loader import ConfigLoader

config = ConfigLoader().load_config()
email_service = EmailService(config)

# Kiểm tra kết nối
result = email_service.test_email_connection()
print(result)

# Gửi email test
if result['success']:
    test_sent = email_service.send_test_email()
    print(f"Test email sent: {test_sent}")
```

### Kiểm tra qua Streamlit
1. Chạy ứng dụng: `streamlit run jobs/streamlit_app.py`
2. Vào tab "System Status"
3. Kiểm tra trạng thái Email Service

## 📨 Tính năng email

### Email hàng ngày
- **Thời gian**: 17:00 (có thể thay đổi trong config.yaml)
- **Nội dung**:
  - Tóm tắt giao dịch trong ngày
  - **🆕 Khuyến nghị mua/bán cho ngày tiếp theo**
  - Danh sách theo dõi
  - Cảnh báo rủi ro

### Email cảnh báo
- Tín hiệu mua/bán
- Cảnh báo rủi ro
- Bất thường về khối lượng
- Cập nhật danh mục

## ⚙️ Cấu hình nâng cao

### Tùy chỉnh template email
Sửa file `config/config.yaml`:
```yaml
email:
  templates:
    subject_prefix: "[Trading Alert]"
    include_charts: false
    include_recommendations: true
```

### Giới hạn email
```yaml
email:
  settings:
    debounce_minutes: 15  # Thời gian tối thiểu giữa các email cùng loại
    max_emails_per_hour: 10  # Tối đa email mỗi giờ
```

## 🔧 Xử lý sự cố

### Lỗi thường gặp

#### "Authentication failed"
- ✅ Kiểm tra email và mật khẩu
- ✅ Sử dụng App Password cho Gmail
- ✅ Bật xác thực 2 bước

#### "Connection refused"
- ✅ Kiểm tra SMTP server và port
- ✅ Kiểm tra kết nối internet
- ✅ Kiểm tra firewall

#### "Recipient emails empty"
- ✅ Kiểm tra RECIPIENT_EMAILS trong .env
- ✅ Đảm bảo format đúng (phân cách bằng dấu phẩy)

### Kiểm tra logs
```bash
tail -f log/main.log | grep -i email
```

## 🔒 Bảo mật

### Bảo vệ thông tin
- ✅ File .env không được commit vào git
- ✅ Sử dụng App Password thay vì mật khẩu chính
- ✅ Giới hạn quyền truy cập file .env

### Permissions (Linux/Mac)
```bash
chmod 600 .env
```

## 📞 Hỗ trợ

Nếu gặp vấn đề:
1. Chạy `python setup_email.py` để kiểm tra cấu hình
2. Kiểm tra logs trong thư mục `log/`
3. Đảm bảo tất cả dependencies đã được cài đặt

---

**Lưu ý**: Khuyến nghị giao dịch được tạo dựa trên thuật toán RSI + PSAR + Engulfing Pattern. Đây chỉ là tham khảo, không phải lời khuyên đầu tư.