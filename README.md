# Car Rental Backend — локальна версія

FastAPI + MySQL, без контейнерів та зовнішнього сховища лімітів.
Архітектура й призначення кожного модуля: **ARCHITECTURE.md**.
Потрібні Python 3.11+ і запущений MySQL 8 Server. Workbench — клієнт;
встановлення лише Workbench не встановлює сервер бази даних.

## 1. Встановлення на Windows / диск D

Відкрийте PowerShell у папці backend, наприклад `D:\UAD\rental cars\backend`.

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-cache-dir -r requirements.txt
Copy-Item .env.example .env
py -c "import secrets; print(secrets.token_hex(32))"
```

Середовище `.venv` створюється в поточній папці, отже може бути на диску D.
Python/системні тимчасові файли можуть використовувати диск C; перенесення
самого проєкту не переносить автоматично інсталяцію Python або MySQL data directory.

У MySQL Workbench під адміністратором виконайте `database/create_database.sql`,
попередньо замінивши пароль-заглушку. Скрипт створює базу й користувача для
TCP-з'єднання з 127.0.0.1. Він не змінює пароль уже існуючого користувача.
Якщо у вас вже є база/користувач, використайте їх і пропустіть створення.

У `.env` задайте:

```dotenv
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_DATABASE=car_rental
MYSQL_USER=car_rental_app
MYSQL_PASSWORD=ваш_пароль_користувача_бази
JWT_SECRET_KEY=сюди_вставте_згенерований_секрет
EMAIL_BACKEND=console
```

Це фрагмент; збережіть решту полів із `.env.example`.
Пароль адміністратора MySQL у `.env` застосунку не потрібен.
SMTP у режимі console не потрібен; Gemini можна налаштувати пізніше.

## 2. Таблиці та демодані

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m src.seed
```

SQLAlchemy описує схему, Alembic створює/оновлює таблиці.
Не викликаємо `create_all()` при старті сервера.
Демодані призначені лише для розробки. У `.env` задайте `SEED_USER_PASSWORD`
(власний пароль 12+ символів, без частини email на кшталт `anna.demo`; у репозиторій
його не додавайте), потім виконайте `python -m src.seed`. Скрипт ідемпотентний:
додає лише відсутні записи за природними ключами (slug авто, email користувача,
пара user/car для улюблених, детерміновані UUID бронювань), нічого не оновлює й не
видаляє, не створює сесій, refresh-токенів та email-outbox і відмовляється працювати
при `APP_ENV=production`. Створює:

- 28 авто (економ, седан, SUV, преміум, мікроавтобуси; бензин, дизель, гібрид,
  електро; механіка й автомат; 4-9 місць) і одне неактивне
  `peugeot-208-inactive-demo` для перевірки, що воно приховане;
- користувачів `anna.demo@example.com`, `oleh.demo@example.com`,
  `iryna.demo@example.com` (остання без улюблених і бронювань);
- улюблені авто Анни й Олега та 5 бронювань відносно дати запуску (4 підтверджені
  в межах 10-50 днів уперед і одне скасоване) для перевірки фільтра доступності.

## 3. Запуск

Перше вікно PowerShell — API:

```powershell
.\.venv\Scripts\python.exe -m uvicorn src.main:app --host 127.0.0.1 --port 8000 --reload --no-proxy-headers
```

Друге вікно в тій самій папці — email worker:

```powershell
.\.venv\Scripts\python.exe -m src.worker
```

Також є необов'язкові `scripts/start-api.ps1` і `scripts/start-worker.ps1`.
Прямі команди Python не потребують активації virtualenv чи зміни ExecutionPolicy.
API запускайте в одному процесі; `--workers 2` та більше тут не підтримуються
для спільного throttling. `--reload` скидає лічильники під час зміни коду.

- Swagger: http://127.0.0.1:8000/docs
- Liveness: http://127.0.0.1:8000/health
- MySQL readiness: http://127.0.0.1:8000/ready
- React origins: localhost і 127.0.0.1 на портах 3000, 5173.

## Правила MVP

- Валюта всього каталогу — UAH; ціна вказана за календарний день.
- Інтервал `[start_date, end_date)`: день повернення не оплачується.
  10–13 числа = 3 дні. Інше бронювання може початися 13 числа.
- Тривалість 1–90 днів; початок сьогодні або протягом наступних 365 днів.
  Календарна дата визначається в UTC. Для погодинної оренди/часових зон
  філій потрібна інша модель часу.
- Створене бронювання одразу `confirmed`; оплати/депозиту в цій реалізації немає.
- Скасування дозволено лише до календарного дня початку; комісій немає.
- Ціна зберігається у бронюванні і не змінюється зі зміною каталогу.
- `Idempotency-Key` — UUID, новий для кожного нового наміру бронювання.
  При мережевому повторі використовуйте той самий ключ і те саме тіло.
  Повтор із іншим тілом = 409. Повтор ключа скасованого бронювання повертає
  саме його: для нового бронювання потрібен новий ключ.


## Перевірка повного сценарію у PowerShell

```powershell
$base = "http://localhost:8000/api/v1"
$registration = @{
    email = "myhaylo@example.com"
    full_name = "Myhaylo Koltun"
    password = "Strong-Rental-Phrase!48"
    password_confirmation = "Strong-Rental-Phrase!48"
} | ConvertTo-Json
Invoke-RestMethod "$base/auth/register" -Method Post -ContentType "application/json" -Body $registration

$login = @{
    email = "myhaylo@example.com"
    password = "Strong-Rental-Phrase!48"
} | ConvertTo-Json
$tokens = Invoke-RestMethod "$base/auth/login" -Method Post -ContentType "application/json" -Body $login
$headers = @{ Authorization = "Bearer $($tokens.access_token)" }
Invoke-RestMethod "$base/auth/me" -Headers $headers

Invoke-RestMethod "$base/cars?category=sedan&max_price=2000&sort=price_asc"
Invoke-RestMethod "$base/favorites/1" -Method Put -Headers $headers
Invoke-RestMethod "$base/favorites" -Headers $headers

$bookingHeaders = @{
    Authorization = "Bearer $($tokens.access_token)"
    "Idempotency-Key" = [guid]::NewGuid().ToString()
}
$bookingBody = @{
    car_id = 1
    start_date = (Get-Date).ToUniversalTime().AddDays(10).ToString("yyyy-MM-dd")
    end_date = (Get-Date).ToUniversalTime().AddDays(13).ToString("yyyy-MM-dd")
} | ConvertTo-Json
$booking = Invoke-RestMethod "$base/bookings" -Method Post -Headers $bookingHeaders -ContentType "application/json" -Body $bookingBody
$booking
Invoke-RestMethod "$base/bookings" -Headers $headers
Invoke-RestMethod "$base/bookings/$($booking.id)/cancel" -Method Post -Headers $headers

Invoke-RestMethod "$base/auth/logout" -Method Post -Headers $headers
# Після виходу /auth/me з цим токеном поверне 401.
```

Заголовок `Idempotency-Key` обов'язковий лише для POST /bookings.
Дати повинні бути ISO `YYYY-MM-DD`. Усі фінансові значення в JSON повертаються
рядками для збереження точності Decimal.
У Swagger натисніть Authorize і вставте access token без префікса `Bearer`.
Login приймає JSON, а не OAuth2 form.

## Endpoint-и

| Метод | Шлях /api/v1 | Призначення |
|---|---|---|
| POST | /auth/register | Реєстрація |
| POST | /auth/login | Access + refresh tokens |
| POST | /auth/refresh | Ротація refresh token |
| POST | /auth/logout | Відкликання поточної сесії |
| GET | /auth/me | Поточний користувач |
| GET | /cars | Каталог, фільтри, пагінація |
| GET | /cars/{car_id} | Інформація про авто |
| POST | /bookings | Створення бронювання |
| GET | /bookings | Лише власні бронювання |
| GET | /bookings/{id} | Власне бронювання |
| POST | /bookings/{id}/cancel | Скасування |
| GET | /favorites | Власні улюблені авто |
| PUT | /favorites/{car_id} | Додавання |
| DELETE | /favorites/{car_id} | Видалення |
| POST | /assistant/recommendations | AI-підбір і картки авто |

Фільтри каталогу: `q`, `brand`, `category`, `transmission`, `fuel_type`,
`min_seats`, `min_price`, `max_price`, `start_date`, `end_date`,
`sort` (price_asc/price_desc/newest), `page`, `page_size` (до 100).
Дати для доступності передаються парою. Категорії та інші допустимі значення
задокументовані в Swagger. GET /bookings і /favorites мають limit/offset.
401 — невалідна сесія; 404 — відсутній/чужий запис; 409 — конфлікт;
422 — невалідні дані; 429 — ліміт; 502/504 — збій/timeout AI; 503 — залежність недоступна.

## Чому немає подвійного бронювання

У транзакції InnoDB з READ COMMITTED:

1. Блокування користувача серіалізує повтори його idempotency key.
2. `SELECT cars ... FOR UPDATE` блокує конкретне авто.
3. Пошук перетину: `existing.start < requested.end AND existing.end > requested.start`.
4. Створення бронювання + outbox у тій самій транзакції, потім commit.

Другий процес чекає на блокування авто і після commit бачить нове бронювання.
Скасування також блокує авто перед зміною бронювання. Звичайна перевірка
доступності у каталозі не є резервуванням.
Цей механізм працює між різними процесами API, а не лише в одному Python-процесі.
Прямі INSERT/UPDATE бронювань в обхід use case не захищені цим протоколом:
всі майбутні admin/import writer-и теж повинні блокувати рядок авто.
Не намагайтеся замінити цей захист `UNIQUE(car_id, start_date, end_date)`.
При deadlock/DB disconnect API повертає 503: повторіть запит із тим самим ключем.


## Email

За замовчуванням `EMAIL_BACKEND=console`: worker виводить листи у свій термінал.
Це режим розробки, фактичного відправлення немає. Такі повідомлення позначаються
обробленими; зміна backend на smtp не перевідправляє їх автоматично.

Для справжньої пошти задайте у `.env`:

```dotenv
EMAIL_BACKEND=smtp
SMTP_HOST=адреса_вашого_smtp_сервера
SMTP_PORT=587
SMTP_USERNAME=ваш_логін
SMTP_PASSWORD=ваш_smtp_пароль
SMTP_STARTTLS=true
SMTP_USE_TLS=false
MAIL_FROM=підтверджена_адреса_відправника
```

Використайте порт і TLS-режим саме вашого провайдера. Для implicit TLS
зазвичай потрібні порт 465, SMTP_USE_TLS=true і SMTP_STARTTLS=false.
Після зміни конфігурації перезапустіть API і worker.
Outbox зберігається у MySQL разом із бронюванням; SMTP-помилка не втрачає
бронювання. Є повторні спроби, backoff та dead-letter після 8 невдач.
Доставка at least once: можливі дублікати після збою між SMTP send і DB commit.

## AI-помічник

Вкажіть `GOOGLE_API_KEY` та `GOOGLE_MODEL` у `.env`: доступний вашому проєкту
актуальний Gemini model ID з підтримкою structured JSON output.
Перезапустіть API. Приклад тіла POST /api/v1/assistant/recommendations:

```json
{"message":"Потрібне сімейне авто на автоматі для 5 людей до 2500 грн на день"}
```

Потрібен bearer access token. Google отримує текст повідомлення й публічні
картки авто, а не користувачів чи бронювання. Не вводьте персональних даних.
При відсутності конфігурації лише AI endpoint повертає 503; решта API працює.

Додаткові налаштування (необов'язкові): `GOOGLE_TIMEOUT_SECONDS` (за замовчуванням 20,
на одну спробу; SDK робить до 2 спроб для 429/500/503/504) і `GOOGLE_THINKING_LEVEL`
(за замовчуванням `low`: Gemini 3.x за замовчуванням «думає» на рівні medium, а
для вилучення фільтрів і вибору ID це зайве; порожнє значення вимикає параметр).
Моделі `temperature` більше не передається, а ліміт токенів (4096) достатній разом
із «думанням». У журналі при збої є рядок
`Gemini plan|rank failed: error=... http_status=... provider_status=...`
(без ключів, промптів і тексту відповіді). Якщо падає лише крок `rank`, endpoint
повертає той самий формат із першими 5 авто каталогу за вашими фільтрами й
повідомленням, що AI-ранжування недоступне; помилка кроку `plan` лишається
HTTP 504 `assistant_timeout` або 502 `assistant_unavailable`.
Модель повертає фільтри та ID, дані у `cars` беруться з каталогу.
Це stateless-підбір до 5 авто серед 40 кандидатів, а не чат з історією.

Як помічник розуміє запит:

- Марка й модель зіставляються з активними авто каталогу без урахування регістру,
  пробілів і дефісів: `Toyota RAV4`, `Toyota Rav4`, `RAV 4` дають `brand=Toyota`,
  `q=RAV4`. Тоді відповідь збирається з рядків БД без ранжування (без зайвого
  AI-виклику), а текст містить рік, тип, коробку, пальне, місця й ціну. Якщо крок
  `plan` недоступний, назва марки/моделі все одно знаходиться.
- Якщо моделі в каталозі немає, помічник чесно про це каже й називає моделі цієї ж
  марки, що є.
- Для запитів про потреби (сім'я, кемпінг тощо) AI лише обирає ID серед знайдених
  авто, а текст відповіді складається з даних БД. Порожній вибір моделі дає
  уточнювальне запитання або пропозицію змінити умови, а не випадкові авто.
- Мова відповіді: українська за замовчуванням, англійська для повністю
  англомовного запиту.

## Тести

```powershell
.\.venv\Scripts\python.exe -m pip install --no-cache-dir -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\ruff.exe format --check .
```

За замовчуванням тести використовують тимчасову SQLite і підміни зовнішніх
адаптерів. Вони не доводять коректність MySQL row locks.
Для справжнього concurrency test виконайте `database/create_test_database.sql`
під адміністратором, замінивши пароль. Потім в ОКРЕМОМУ новому терміналі:

```powershell
$env:MYSQL_HOST = "127.0.0.1"
$env:MYSQL_DATABASE = "car_rental_test"
$env:MYSQL_USER = "car_rental_test"
$env:MYSQL_PASSWORD = "ваш_тестовий_пароль"
$env:TEST_MYSQL = "1"
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m pytest -q
```

Тестова fixture видаляє/створює таблиці: використовуйте ВИКЛЮЧНО тестову БД.
Після перевірки закрийте цей термінал, щоб не запускати API з тестовими env.
Не запускайте кілька test runner-ів проти однієї БД одночасно.

## Обслуговування

- Зупинка процесів — Ctrl+C у відповідних терміналах; MySQL лишається службою.
- Після зміни `.env` перезапустіть API та worker.
- JWT/refresh повертаються JSON. Для MVP frontend може зберігати їх у пам'яті.
  Browser cookie-auth з HttpOnly/Secure та CSRF потребує окремого дизайну.
- Сесії, бронювання, улюблені й outbox переживають перезапуск, бо зберігаються в MySQL.
- Rate limits після перезапуску очищаються. Це компроміс локального MVP.
- Не додавайте прямі записи бронювань в обхід application use case:
  усі майбутні writer-и також повинні блокувати рядок авто.
- Email verification, reset password, платежі, адмінка та web push не реалізовані.
