-- Optional. Run as MySQL administrator. Never use the main DB for tests.
CREATE DATABASE IF NOT EXISTS car_rental_test
    CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'car_rental_test'@'127.0.0.1'
    IDENTIFIED BY 'REPLACE_WITH_YOUR_TEST_DATABASE_PASSWORD';
GRANT ALL PRIVILEGES ON car_rental_test.* TO 'car_rental_test'@'127.0.0.1';
