# Hệ Thống Cảnh Báo Realtime - RSI PSAR Engulfing Strategy

Hệ thống cảnh báo realtime cho chiến lược giao dịch RSI-PSAR-Engulfing trên thị trường chứng khoán Việt Nam.

## Tính năng chính

- 📡 **Dữ liệu Realtime**: Tích hợp FiinQuantX để lấy dữ liệu OHLCV realtime chất lượng cao
- 🤖 **Telegram Alerts**: Gửi cảnh báo tự động qua Telegram bot với debounce thông minh
- 📊 **Streamlit Dashboard**: Dashboard realtime với biểu đồ và bảng dữ liệu trực quan
- 🎯 **Chiến lược RSI-PSAR-Engulfing**: Implement đầy đủ với risk management chuyên nghiệp
- 📝 **Logging & Replay**: Ghi log chi tiết và khả năng replay dữ liệu để phân tích
- 🧪 **Testing**: Unit tests đầy đủ cho tất cả components đảm bảo chất lượng
- 🚨 **Production Ready**: Yêu cầu FiinQuantX premium cho dữ liệu thị trường thật

## Cấu trúc project

```
realtime_alert_system/
├── README.md                    # Tài liệu dự án
├── requirements.txt             # Dependencies Python
├── .env.example                 # Template cấu hình
├── config/                      # Cấu hình và settings
│   ├── config.yaml             # Cấu hình chính
│   └── symbols.json            # Danh sách mã cổ phiếu
├── utils/                      # Utility functions
│   ├── __init__.py
│   ├── fiinquant_adapter.py    # FiinQuant API adapter
│   ├── indicators.py           # Technical indicators
│   └── helpers.py              # Helper functions
├── strategy/                   # Chiến lược giao dịch
│   ├── __init__.py
│   ├── rsi_psar_engulfing.py  # Main strategy
│   └── risk_management.py      # Quản lý rủi ro
├── database/                   # Quản lý dữ liệu
│   ├── __init__.py
│   └── data_manager.py         # Lưu trữ và truy vấn dữ liệu
├── jobs/                       # Main applications
│   ├── __init__.py
│   ├── realtime_monitor.py     # Monitoring realtime
│   ├── telegram_bot.py         # Telegram bot
│   └── streamlit_app.py        # Dashboard Streamlit
├── log/                        # Log files
│   └── .gitkeep
├── test/                       # Unit tests
│   ├── __init__.py
│   ├── test_indicators.py
│   ├── test_strategy.py
│   └── test_fiinquant.py
└── plot/                       # Visualization utilities
    ├── __init__.py
    └── charts.py               # Chart utilities
```

## Cài đặt

1. **Clone repository và setup environment:**
   ```bash
   cd realtime_alert_system
   pip install -r requirements.txt
   ```

2. **Cấu hình environment:**
   ```bash
   cp env_example.txt .env 
   # Chỉnh sửa .env với thông tin của bạn
   ```

3. **Cài đặt FiinQuantX (BẮT BUỘC):**
   - 📞 **Liên hệ FiinQuant**: https://fiinquant.com để có FiinQuantX package
   - 👤 **Tài khoản premium**: Cần tài khoản có quyền truy cập API realtime  
   - 📦 **Cài đặt package**: Theo hướng dẫn chính thức của FiinQuant
   - ⚙️ **Cấu hình credentials**: Cập nhật username/password trong .env

4. **Cấu hình Telegram Bot:**
   - Tạo bot mới với @BotFather trên Telegram
   - Lấy bot token và chat ID
   - Cập nhật vào .env

## Sử dụng

### 1. Chạy Realtime Monitor
```bash
python jobs/realtime_monitor.py
```

### 2. Chạy Streamlit Dashboard
```bash
streamlit run jobs/streamlit_app.py
```

### 3. Chạy Telegram Bot
```bash
python jobs/telegram_bot.py
```

## Cấu hình Strategy

Tham số mặc định trong `config/config.yaml`:

```yaml
strategy:
  rsi:
    period: 14
    overbought: 70
    oversold: 30
    neutral: 50
  psar:
    af_init: 0.02
    af_step: 0.02
    af_max: 0.20
  engulfing:
    detection_window: 2
    min_body_ratio: 0.5
  risk_management:
    take_profit: 0.15
    stop_loss: 0.08
    trailing_take_profit: 0.09
    trailing_stop: 0.03
    position_size: 0.02
    max_positions: 10
    max_daily_loss: 0.05
```

## Testing

```bash
python -m pytest test/ -v
```

## Giới hạn và Lưu ý

- Yêu cầu tài khoản FiinQuant Premium để truy cập dữ liệu realtime
- Hệ thống chỉ hoạt động trong giờ giao dịch của sàn HOSE/HNX/UPCOM
- Cần kết nối internet ổn định để đảm bảo độ trễ thấp

## Liên hệ

Mọi thắc mắc vui lòng tạo issue trong repository.
