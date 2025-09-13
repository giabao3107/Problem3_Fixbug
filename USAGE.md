# Hướng dẫn sử dụng Hệ thống Cảnh báo Realtime

## 🚀 Khởi động nhanh

### 1. Thiết lập ban đầu

```bash
# Di chuyển vào thư mục project
cd realtime_alert_system

# Thiết lập project (tạo thư mục, file cấu hình)
python main.py setup

# Cài đặt dependencies
pip install -r requirements.txt
```

### 2. Cài đặt FiinQuantX (BẮT BUỘC)

**🚨 YÊU CẦU BẮT BUỘC: FiinQuantX**
Hệ thống này yêu cầu bắt buộc phải có FiinQuantX package để hoạt động.

**Cách thức cài đặt:**
1. 📞 **Liên hệ FiinQuant**: https://fiinquant.com
2. 📦 **Yêu cầu package**: FiinQuantX installation package
3. 👤 **Đăng ký tài khoản**: Premium account với quyền truy cập API
4. 📋 **Lấy hướng dẫn**: Installation guide và documentation
5. ✅ **Cài đặt**: Theo hướng dẫn của FiinQuant

**⚠️ Lưu ý quan trọng:**
- ❌ **Không có mock data fallback**
- ❌ **Hệ thống sẽ báo lỗi** nếu thiếu FiinQuantX
- 💰 **Premium service** - có phí sử dụng
- 🏢 **Doanh nghiệp**: Liên hệ trực tiếp để có giá tốt nhất

### 3. Cấu hình môi trường

Chỉnh sửa file `.env` với thông tin của bạn:

```env
# FiinQuant (BẮT BUỘC - từ tài khoản premium FiinQuant)
FIINQUANT_USERNAME=your_fiinquant_username
FIINQUANT_PASSWORD=your_fiinquant_password

# Telegram Bot (BẮT BUỘC cho alerts)
TELEGRAM_BOT_TOKEN=1234567890:ABCDEFghijklmnopqrstuvwxyzABCDEFG1234
TELEGRAM_CHAT_ID=-1001234567890

# Hệ thống (Tùy chọn)
REFRESH_INTERVAL_SECONDS=60
TIMEFRAME=15m
LOG_LEVEL=INFO
TIMEZONE=Asia/Ho_Chi_Minh
```

### 4. Chạy hệ thống

#### Chạy tất cả dịch vụ cùng lúc:
```bash
python main.py all
```

#### Chạy từng dịch vụ riêng biệt:
```bash
# Monitor realtime
python main.py monitor

# Dashboard Streamlit
python main.py dashboard

# Telegram bot
python main.py bot
```


## 📊 Các thành phần chính

### 1. Realtime Monitor
- **Chức năng**: Giám sát thị trường realtime, phân tích tín hiệu
- **URL**: Chạy trong background
- **Log**: Kiểm tra folder `log/` cho chi tiết

### 2. Streamlit Dashboard
- **Chức năng**: Giao diện web hiển thị signals, charts, portfolio
- **URL**: http://localhost:8501
- **Tính năng**:
  - Charts OHLC với indicators (RSI, PSAR)
  - Bảng tín hiệu realtime
  - Thống kê portfolio
  - Heatmap tín hiệu

### 3. Telegram Bot
- **Chức năng**: Gửi cảnh báo tức thời
- **Commands**:
  - `/start` - Khởi động bot
  - `/help` - Hướng dẫn
  - `/status` - Trạng thái hệ thống
  - `/top` - Top cơ hội
  - `/positions` - Vị thế hiện tại

## 🎯 Chiến lược RSI-PSAR-Engulfing

### Tín hiệu MUA:
- ✅ Giá > PSAR (xu hướng tăng)
- ✅ RSI > 50 (động lượng)
- ✅ Volume > trung bình (tùy chọn)
- ✅ Bullish Engulfing ≤ 3 nến gần nhất (tùy chọn)

### Tín hiệu BÁN:
- ❌ RSI < 50
- ❌ Bearish Engulfing
- ❌ Take Profit: +15%
- ❌ Stop Loss: -8%
- ❌ Trailing Stop: 3% sau khi lãi ≥ 9%

### Quản lý rủi ro:
- 📊 Position size: 2% rủi ro/lệnh
- 📈 Max positions: 10 đồng thời
- 📉 Max daily loss: 5% portfolio

## 🧪 Testing & Validation

### Chạy tests:
```bash
# Tất cả tests
python main.py test

# Với coverage report
python main.py test --coverage

# Test cụ thể
python -m pytest test/test_indicators.py -v
```

### Validation components:
- ✅ Technical indicators (RSI, PSAR, Engulfing)
- ✅ Strategy logic
- ✅ Risk management
- ✅ FiinQuant adapter
- ✅ Database operations

## 📁 Cấu trúc dữ liệu

### Logs:
```
log/
├── main_20231201_090000.log          # Log chính
├── signals/
│   └── signals_20231201_090000.log   # Log tín hiệu
├── audit/
│   └── audit_20231201_090000.log     # Log giao dịch
└── replay/
    └── replay_20231201_090000.pkl.gz # Dữ liệu replay
```

### Database:
```
database/
└── trading_data.db    # SQLite database
    ├── signals        # Tín hiệu giao dịch
    ├── market_data    # Dữ liệu thị trường
    ├── trades         # Giao dịch
    └── performance_metrics # Thống kê hiệu suất
```

## 🔧 Cấu hình nâng cao

### Tùy chỉnh chiến lược (config/config.yaml):
```yaml
strategy:
  rsi:
    period: 14
    overbought: 70
    oversold: 30
  psar:
    af_init: 0.02
    af_max: 0.20
  risk_management:
    take_profit: 0.15
    stop_loss: 0.08
```

### Danh sách cổ phiếu (config/symbols.json):
```json
{
  "universe": {
    "vn30": ["ACB", "VNM", "HPG", "..."],
    "watchlist": ["FPT", "MSN", "..."]
  }
}
```

## 🚨 Troubleshooting

### Lỗi thường gặp:

#### 1. "FiinQuantX not available" hoặc "FiinQuantX is required"
**Nguyên nhân:** Chưa cài đặt FiinQuantX package
**📛 LỖI NGHIÊM TRỌNG - HỆ THỐNG SẼ KHÔNG KHỞI ĐỘNG**

**Giải pháp duy nhất:**
1. 📞 **Liên hệ FiinQuant**: https://fiinquant.com hoặc hotline support
2. 📦 **Yêu cầu**: FiinQuantX installation package + documentation  
3. 👤 **Đăng ký**: Premium account với API access
4. 💾 **Cài đặt**: Theo hướng dẫn chính thức của FiinQuant
5. ⚙️ **Cấu hình**: FIINQUANT_USERNAME và FIINQUANT_PASSWORD trong .env

**⚠️ Không có giải pháp thay thế - FiinQuantX là bắt buộc**

#### 2. "Failed to login to FiinQuant"
- Kiểm tra username/password trong `.env`
- Đảm bảo tài khoản FiinQuant còn hạn

#### 3. "Telegram bot failed"
- Kiểm tra `TELEGRAM_BOT_TOKEN`
- Đảm bảo bot được add vào group/channel

#### 4. "Database locked"
```bash
# Stop tất cả processes trước khi restart
pkill -f realtime_monitor
python main.py all
```

### Debug mode:
```bash
python main.py monitor --log-level DEBUG
```

## 📈 Monitoring & Performance

### Kiểm tra logs:
```bash
# Log realtime
tail -f log/main_*.log

# Tín hiệu
tail -f log/signals/signals_*.log
```

### Performance metrics:
- Streamlit dashboard → Analytics tab
- Database queries cho detailed stats
- Log files cho historical performance

### Health checks:
- Telegram: `/status` command
- Dashboard: Status indicators
- Logs: Error/warning messages

## 🔒 Bảo mật

### Khuyến nghị:
1. ✅ Không commit file `.env`
2. ✅ Sử dụng strong passwords
3. ✅ Restrict Telegram bot permissions
4. ✅ Monitor unusual activity in logs
5. ✅ Regular backup of database

### Backup dữ liệu:
```bash
# Backup database
cp database/trading_data.db backup/trading_data_$(date +%Y%m%d).db

# Backup logs
tar -czf backup/logs_$(date +%Y%m%d).tar.gz log/
```

## 📞 Hỗ trợ

### Log files quan trọng:
- `log/main_*.log` - Lỗi hệ thống
- `log/signals/*.log` - Chi tiết tín hiệu
- `log/audit/*.log` - Giao dịch

### Commands hữu ích:
```bash
# Xem trạng thái processes
ps aux | grep python

# Kiểm tra port đang dùng
netstat -tulpn | grep :8501

# Clean up old logs
find log/ -name "*.log*" -mtime +30 -delete
```

---

**⚠️ Lưu ý quan trọng**: Hệ thống này chỉ mang tính chất tham khảo. Luôn thực hiện phân tích kỹ lưỡng và quản lý rủi ro cẩn thận khi đầu tư thực tế.
