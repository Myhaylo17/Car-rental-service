# Архітектура локального backend

## Компоненти запуску

1. React frontend на localhost:3000 або localhost:5173.
2. Один процес FastAPI/Uvicorn на localhost:8000.
3. MySQL Server на localhost:3306.
4. Окремий Python email worker, що читає outbox у MySQL.
5. Зовнішній Gemini API; SMTP-провайдер потрібен лише для справжніх листів.

Контейнерів, Redis, Celery і брокера повідомлень немає. Робоча папка і `.venv`
можуть бути на диску D. Обов'язкова локальна служба — лише MySQL Server.

## Структура

```text
backend/
├── src/
│   ├── api/
│   │   ├── routes.py
│   │   ├── dependencies.py
│   │   └── composition.py
│   ├── application/
│   │   ├── authentication.py
│   │   ├── bookings.py
│   │   ├── assistant.py
│   │   ├── schemas.py
│   │   └── ports.py
│   ├── domain/
│   │   ├── booking.py
│   │   └── errors.py
│   ├── infrastructure/
│   │   ├── models.py
│   │   ├── database.py
│   │   ├── auth_store.py
│   │   ├── security.py
│   │   ├── catalog.py
│   │   ├── bookings.py
│   │   ├── favorites.py
│   │   ├── rate_limit.py
│   │   ├── email.py
│   │   └── gemini.py
│   ├── config.py
│   ├── main.py
│   ├── seed.py
│   └── worker.py
├── alembic/
│   ├── versions/0001_initial.py
│   ├── env.py
│   └── script.py.mako
├── database/
│   ├── create_database.sql
│   └── create_test_database.sql
├── scripts/
│   ├── start-api.ps1
│   └── start-worker.ps1
├── tests/
├── .env.example
├── .gitignore
├── alembic.ini
├── pyproject.toml
├── requirements.txt
├── requirements-dev.txt
├── ARCHITECTURE.md
├── README.md
└── VALIDATION.md
```

У Python-пакетах також є `__init__.py`.

## Межі шарів

| Шар | Відповідальність | Чого тут немає |
|---|---|---|
| api | HTTP, авторизаційні залежності, побудова компонентів, DTO | SQL-запитів, розрахунку ціни |
| application | Сценарії реєстрації, входу, бронювання, скасування, AI | Залежності від ORM, FastAPI, Google SDK |
| domain | Чисті правила дат і вартості, бізнес-помилки | Мережі, SQL, конфігурації сервера |
| infrastructure | MySQL, ORM, JWT, Argon2, SMTP, Gemini, throttling | HTTP-маршрутів |

Композиція використовує конкретні адаптери, реалізовані через Protocol-порти.
Для простого CRUD улюблених авто окремий порожній use-case wrapper не додається.

## Збереження даних

| Таблиця | Дані |
|---|---|
| users | Профілі та хеші паролів |
| auth_sessions | Сесії, термін дії та відкликання |
| refresh_tokens | Хеші refresh-токенів, факт їх використання |
| cars | Каталог і поточна ціна оренди |
| bookings | Дати, статус, власник, зафіксована ціна, ключ ідемпотентності |
| favorites | Зв'язок користувач–авто |
| email_outbox | Намір доставки листа, повторні спроби, стан обробки |

## Обмеження запитів

`InMemoryRateLimiter` використовує monotonic clock, asyncio.Lock і TTL.
Лічильники розділені за операцією та HMAC ідентифікатора. Є обмеження кількості
ключів; min-heap видаляє прострочені записи. При переповненні нові ключі не
витісняють діючі ліміти: повертається 503. При перевищенні ліміту — 429 із
реальним Retry-After. Стан скидається при перезапуску або reload коду.

API запускається в ОДНОМУ процесі. Кілька worker-ів мали б незалежні ліміти.
Email worker — окремий процес, він не впливає на ці лічильники.
Це обмеження стосується лише throttling. Бронювання та auth-сесії залишаються в MySQL.

## Бронювання та сповіщення

У транзакції backend блокує користувача для idempotency та рядок авто для
захисту від перетинів. Бронювання і лист outbox записуються разом.
Інший запит чекає на той самий row lock і бачить результат першого commit.
Скасування також блокує авто. Пошук доступності в каталозі не резервує авто.

Worker опитує email_outbox. Після помилки доставка повторюється з backoff;
після 8 спроб запис переходить у dead-letter. Сервіс доставки працює у двох режимах:
`console` — показує лист у логах для розробки; `smtp` — надсилає через провайдера.
SMTP-доставка має семантику at least once, тому повторний лист після аварії можливий.

## AI-помічник

Модель формує лише валідовані фільтри каталогу. Backend сам виконує SELECT,
після чого модель ранжує до 20 кандидатів і повертає до 5 реальних ID.
Картки, ціни й характеристики читаються з БД. Довільного SQL та write tools
у моделі немає; записи users, auth_sessions і bookings їй недоступні.
