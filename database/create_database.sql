-- Run as a MySQL administrator in MySQL Workbench.
-- Replace the password BEFORE executing; use the same value in .env.
CREATE DATABASE IF NOT EXISTS car_rental
    CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE USER IF NOT EXISTS 'car_rental_app'@'127.0.0.1'
    IDENTIFIED BY 'REPLACE_WITH_YOUR_DATABASE_PASSWORD';
GRANT ALL PRIVILEGES ON car_rental.* TO 'car_rental_app'@'127.0.0.1';

-- CREATE USER IF NOT EXISTS does not change an existing account's password.
-- If necessary, run ALTER USER explicitly with your actual password:
-- ALTER USER 'car_rental_app'@'127.0.0.1' IDENTIFIED BY 'YOUR_NEW_PASSWORD';
-- Tables are created by Alembic, not this script.
