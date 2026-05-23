## 📦 **Tổng hợp câu lệnh PostgreSQL trên PowerShell**

---

### 🐘 **Docker - Quản lý container PostgreSQL**

```bash
# Khởi động PostgreSQL container
docker-compose up -d

# Dừng container
docker-compose stop

# Khởi động lại container
docker-compose start

# Dừng và xóa container (xóa luôn dữ liệu)
docker-compose down -v

# Xem container đang chạy
docker ps

# Xem log của container
docker logs ai_services_postgres

# Restart container
docker restart ai_services_postgres
```

---

### 🔌 **Kết nối database**

```bash
# Kết nối vào database (psql)
docker exec -it ai_services_postgres psql -U postgres -d ai_services

# Kết nối với mật khẩu (nếu cần)
docker exec -it ai_services_postgres psql -U postgres -d ai_services -W

# Chạy câu lệnh SQL trực tiếp (không vào psql)
docker exec -it ai_services_postgres psql -U postgres -d ai_services -c "SELECT 1"
```

---

### 📋 **Xem thông tin database**

```bash
# Liệt kê tất cả database
docker exec -it ai_services_postgres psql -U postgres -d ai_services -c "\l"

# Liệt kê tất cả bảng
docker exec -it ai_services_postgres psql -U postgres -d ai_services -c "\dt"

# Liệt kê tất cả bảng (kể cả hệ thống)
docker exec -it ai_services_postgres psql -U postgres -d ai_services -c "\dt *.*"

# Xem cấu trúc 1 bảng cụ thể
docker exec -it ai_services_postgres psql -U postgres -d ai_services -c "\d users"

# Xem thông tin kết nối
docker exec -it ai_services_postgres psql -U postgres -d ai_services -c "\conninfo"
```

---

### 📝 **CRUD - Thêm, sửa, xóa dữ liệu**

```bash
# Thêm user mới
docker exec -it ai_services_postgres psql -U postgres -d ai_services -c "INSERT INTO users (username, email, hashed_password) VALUES ('test', 'test@email.com', '123456');"

# Xem tất cả users
docker exec -it ai_services_postgres psql -U postgres -d ai_services -c "SELECT * FROM users;"

# Xóa user
docker exec -it ai_services_postgres psql -U postgres -d ai_services -c "DELETE FROM users WHERE username = 'test';"

# Cập nhật user
docker exec -it ai_services_postgres psql -U postgres -d ai_services -c "UPDATE users SET email = 'new@email.com' WHERE username = 'test';"

# Đếm số lượng users
docker exec -it ai_services_postgres psql -U postgres -d ai_services -c "SELECT COUNT(*) FROM users;"
```

---

### 🗑️ **Xóa dữ liệu**

```bash
# Xóa toàn bộ dữ liệu trong bảng (giữ cấu trúc)
docker exec -it ai_services_postgres psql -U postgres -d ai_services -c "TRUNCATE TABLE users;"

# Xóa toàn bộ dữ liệu + reset sequence (id về 1)
docker exec -it ai_services_postgres psql -U postgres -d ai_services -c "TRUNCATE TABLE users RESTART IDENTITY;"

# Xóa bảng (xóa luôn cấu trúc)
docker exec -it ai_services_postgres psql -U postgres -d ai_services -c "DROP TABLE users;"

# Xóa database
docker exec -it ai_services_postgres psql -U postgres -c "DROP DATABASE ai_services;"
```

---

### 🔄 **Backup & Restore**

```bash
# Backup toàn bộ database (ra file)
docker exec -it ai_services_postgres pg_dump -U postgres ai_services > backup.sql

# Backup chỉ cấu trúc (không có dữ liệu)
docker exec -it ai_services_postgres pg_dump -U postgres --schema-only ai_services > schema.sql

# Backup chỉ dữ liệu (không có cấu trúc)
docker exec -it ai_services_postgres pg_dump -U postgres --data-only ai_services > data.sql

# Restore từ file backup
cat backup.sql | docker exec -i ai_services_postgres psql -U postgres -d ai_services
```

---

### 📊 **Xem thống kê & monitor**

```bash
# Xem kích thước database
docker exec -it ai_services_postgres psql -U postgres -d ai_services -c "SELECT pg_database_size('ai_services')/1024/1024 || ' MB' AS size;"

# Xem kích thước từng bảng
docker exec -it ai_services_postgres psql -U postgres -d ai_services -c "SELECT tablename, pg_size_pretty(pg_total_relation_size('public.'||tablename)) AS size FROM pg_tables WHERE schemaname = 'public' ORDER BY pg_total_relation_size('public.'||tablename) DESC;"

# Xem số kết nối đang active
docker exec -it ai_services_postgres psql -U postgres -d ai_services -c "SELECT count(*) FROM pg_stat_activity WHERE datname = 'ai_services';"

# Xem danh sách kết nối đang active
docker exec -it ai_services_postgres psql -U postgres -d ai_services -c "SELECT pid, usename, application_name, client_addr, state FROM pg_stat_activity WHERE datname = 'ai_services';"
```

---

### 🔧 **Bảo trì & sửa lỗi**

```bash
# Phân tích và cập nhật thống kê
docker exec -it ai_services_postgres psql -U postgres -d ai_services -c "ANALYZE;"

# Vacuum (dọn dẹp dữ liệu chết)
docker exec -it ai_services_postgres psql -U postgres -d ai_services -c "VACUUM;"

# Vacuum full (dọn + trả dung lượng)
docker exec -it ai_services_postgres psql -U postgres -d ai_services -c "VACUUM FULL;"

# Reindex database
docker exec -it ai_services_postgres psql -U postgres -d ai_services -c "REINDEX DATABASE ai_services;"

# Kiểm tra lỗi
docker exec -it ai_services_postgres psql -U postgres -d ai_services -c "SELECT * FROM pg_stat_database WHERE datname = 'ai_services';"
```

---

### 🎯 **Alembic - Quản lý migration**

```bash
# Tạo migration mới (tự động dò changes)
alembic revision --autogenerate -m "ten_migration"

# Tạo migration trống
alembic revision -m "ten_migration"

# Chạy migration lên version mới nhất
alembic upgrade head

# Rollback 1 version
alembic downgrade -1

# Rollback về version cụ thể
alembic downgrade <revision_id>

# Xem version hiện tại
alembic current

# Xem lịch sử migration
alembic history
```

---

### 🚪 **Thoát & dọn dẹp**

```bash
# Thoát khỏi psql (khi đang trong psql)
\q

# Thoát khỏi container (khi đang trong container bash)
exit

# Dừng và xóa container + volume (xóa sạch data)
docker-compose down -v

# Xóa toàn bộ container PostgreSQL
docker rm -f ai_services_postgres

# Xóa image PostgreSQL
docker rmi postgres:16-alpine
```

---

## **💡 Mẹo: Tạo alias cho lệnh dài**

Thêm vào `$PROFILE` (PowerShell profile):

```powershell
function pg-sql { docker exec -it ai_services_postgres psql -U postgres -d ai_services -c "$args" }
function pg-tables { docker exec -it ai_services_postgres psql -U postgres -d ai_services -c "\dt" }
function pg-connect { docker exec -it ai_services_postgres psql -U postgres -d ai_services }
```

Dùng: `pg-sql "SELECT * FROM users"` hoặc `pg-tables`

---

**Lưu lại để dùng khi cần nhé!** 🚀