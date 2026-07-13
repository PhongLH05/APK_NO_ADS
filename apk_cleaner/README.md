# APK Cleaner Tool

Công cụ Python tự động gỡ **Quảng cáo (Ads)** và **chặn điều hướng Play Store** bên trong file APK Android.

## Quy trình hoạt động

```
[APK gốc]
   │
   ▼  Bước 1 — apktool decompile
[Smali + XML]
   │
   ▼  Bước 2 — Python quét & sửa code
[Code sạch]
   │
   ▼  Bước 3 — apktool build
[APK chưa ký]
   │
   ▼  Bước 4 — uber-apk-signer ký số
[APK hoàn chỉnh ✓]
```

---

## Cài đặt prerequisites

### 1. Java JDK 8+
- Tải từ: https://adoptium.net/
- Đảm bảo lệnh `java -version` chạy được trong terminal

### 2. APKTool
- Tải `apktool.jar` từ: https://ibotpeaches.github.io/Apktool/
- Đặt vào thư mục `apk_cleaner/tools/apktool.jar`

### 3. Uber-APK-Signer
- Tải `uber-apk-signer.jar` từ: https://github.com/patrickfav/uber-apk-signer/releases
- Đặt vào thư mục `apk_cleaner/tools/uber-apk-signer.jar`

### 4. Python 3.9+
```bash
pip install pytest   # chỉ cần nếu muốn chạy tests
```

---

## Cấu trúc thư mục

```
apk_cleaner/
├── apk_cleaner.py          # Entry point chính (CLI)
├── config.py               # Cấu hình paths & tham số
├── decompiler.py           # Bước 1: Decompile APK
├── cleaner.py              # Bước 2: Quét & sửa Smali + XML
├── recompiler.py           # Bước 3 & 4: Recompile + Sign
├── logger.py               # Logging màu sắc
├── patterns/
│   ├── ads_patterns.json   # Blacklist 35+ Ad SDK
│   └── store_patterns.json # Blacklist Play Store URI
├── tests/
│   └── test_cleaner.py     # Unit tests
├── tools/                  # Đặt JAR files vào đây
│   ├── apktool.jar
│   └── uber-apk-signer.jar
├── output/                 # File APK sạch sẽ xuất ra đây
├── logs/                   # Log chi tiết từng lần chạy
└── requirements.txt
```

---

## Cách sử dụng

### Cơ bản
```bash
python apk_cleaner.py -i ten_app.apk
```

### Chỉ định thư mục output
```bash
python apk_cleaner.py -i ten_app.apk -o ./ket_qua
```

### Xem log chi tiết
```bash
python apk_cleaner.py -i ten_app.apk --verbose
```

### Dry run (kiểm tra trước, không sửa file)
```bash
python apk_cleaner.py -i ten_app.apk --dry-run
```

### Ký bằng production keystore
```bash
python apk_cleaner.py -i ten_app.apk --keystore release.jks --alias mykey --ks-pass mypassword
```

### Thêm patterns tùy chỉnh
```bash
python apk_cleaner.py -i ten_app.apk --patterns my_extra_patterns.json
```

### Giữ lại thư mục Smali để kiểm tra
```bash
python apk_cleaner.py -i ten_app.apk --keep-temp
```

---

## Tất cả tùy chọn CLI

| Flag | Mô tả |
|------|-------|
| `-i / --input` | File APK đầu vào **(bắt buộc)** |
| `-o / --output` | Thư mục output (mặc định: `./output`) |
| `--patterns` | File JSON patterns bổ sung |
| `--keystore` | File .jks để ký production |
| `--alias` | Alias trong keystore |
| `--ks-pass` | Mật khẩu keystore |
| `--keep-temp` | Giữ thư mục Smali tạm |
| `-v / --verbose` | Log chi tiết |
| `--dry-run` | Chỉ quét, không ghi file |
| `--no-xml` | Bỏ qua XML cleaning |

---

## Chạy Unit Tests

```bash
cd apk_cleaner
pytest tests/ -v
```

---

## Thêm Patterns mới

Tạo file JSON theo format sau và truyền vào `--patterns`:

```json
{
  "sdk_packages": [
    "com/ten_sdk_moi/ads"
  ]
}
```

Hoặc chỉnh trực tiếp file `patterns/ads_patterns.json`.

---

## Lưu ý quan trọng

> **Chống crash**: Tool không xóa code mà chỉ chèn `return-void` / `return v0` vào đầu method. Cách này đảm bảo app không bị crash do lệch offset bytecode.

> **XML**: Khai báo trong Manifest và layout XML được comment out chứ không xóa — APKTool vẫn compile được.

> **Anti-decompile**: Một số app lớn có cơ chế chống dịch ngược. Nếu decompile thất bại, kiểm tra log để biết nguyên nhân.

---

## Danh sách Ad SDK được hỗ trợ (35+)

Google AdMob, Unity Ads, Facebook Audience Network, AppLovin, Vungle, MoPub, IronSource, Chartboost, Tapjoy, InMobi, StartApp, AdColony, Millennial Media, Flurry, Amazon Ads, AppNext, HeyZap, LeadBolt, RevMob, AppBrain, Appodeal, Ogury, Criteo, Yandex Ads, MyTarget, Supersonic, PubNative, LoopMe, Smaato, BidMachine, Fyber, Digital Turbine...
