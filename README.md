# CampusFlow

Сервис поиска и бронирования аудиторий по кейсу IBS. FastAPI + SQLAlchemy, React + TypeScript. SQLite локально, PostgreSQL для Render. Поиск, занятость и выбор времени доступны на одном экране.

Для реальной эксплуатации: [production runbook](docs/PRODUCTION.md). Демо и production разделены: `compose.yaml` / `render.yaml` содержат публичные учебные аккаунты; `compose.production.yaml` / `render.production.yaml` запускают чистую PostgreSQL, миграции и регистрацию по приглашению. Результаты проверок: [VERIFICATION.md](docs/VERIFICATION.md).

## Запуск на Windows

Нужны Python 3.11+ и Node.js 22.12+. Из корня проекта:

```powershell
Copy-Item .env.example .env
powershell -ExecutionPolicy Bypass -File scripts/start.ps1
```

Сайт: http://127.0.0.1:8000, Swagger: http://127.0.0.1:8000/docs. Первый запуск скачивает зависимости; seed создаётся автоматически. Следующие запуски сохраняют БД `campusflow.db`. Для повторного запуска без установки: `.venv/Scripts/python -m uvicorn backend.main:app --env-file .env`.

## Docker

С запущенным Docker Desktop: `docker compose up --build`. Приложение доступно на порту 8080. PostgreSQL хранится в volume `campus-data`. `docker compose down` сохраняет данные; не добавляйте `-v`, если они нужны.

## Демо-аккаунты

| Логин | Пароль | Роль |
|---|---|---|
| student1 | campus2026 | Студент, Алексей Морозов |
| student2 | campus2026 | Студент, Мария Волкова |
| admin | campus2026 | Администратор, Анна Соколова |

Регистрация создаёт только студента. JWT действует 8 часов, хранится в sessionStorage текущей вкладки. После обновления страницы сессия восстанавливается; выход удаляет токен. Для стабильных сессий задайте JWT_SECRET в .env. Пароли хешируются PBKDF2. Демонстрационные аккаунты намеренно опубликованы для жюри.

## Возможности

- Фильтры: корпус, вместимость, набор оборудования, дата, интервал; поиск по номеру.
- Сетка занятости, календарь, выбор длительности, комментарий, подтверждение.
- Мои брони, история отмен, экспорт `.ics` для Google Calendar / Outlook / Apple Calendar.
- Администратор: все брони, отмена, создание/редактирование/архивирование аудиторий, недельная загрузка и CSV.
- Светлая, тёмная и системная тема; сохранение выбора, мобильная версия, клавиатурный фокус и диалоги.
- 12 аудиторий, 3 пользователя, 56 стартовых броней на 8 дней относительно первого запуска.

## API

Все запросы кроме health, meta и auth требуют `Authorization: Bearer TOKEN`. Получить `accessToken` через POST `/api/auth/login`, затем вставить в Swagger → Authorize. JSON использует camelCase. Ошибка: `{"error":{"code":"BOOKING_CONFLICT","message":"..."}}`.

| Метод | Путь | Действие |
|---|---|---|
| POST | /api/auth/login | login, password → JWT |
| POST | /api/auth/register | login, displayName, password → student + JWT |
| GET | /api/auth/me | Текущий пользователь |
| GET | /api/meta | Дата кампуса, оборудование, корпуса |
| GET | /api/health | Проверка приложения и БД |
| GET | /api/rooms | building, minCapacity, equipment (через запятую), date, startTime, endTime |
| GET | /api/rooms/{id} | Аудитория |
| GET | /api/rooms/{id}/free-slots?date=YYYY-MM-DD | Свободные интервалы и занятость без чужих персональных данных |
| POST | /api/bookings | roomId, date, startTime, endTime, comment |
| GET | /api/bookings/my | Свои брони |
| GET / DELETE | /api/bookings/{id} | Просмотр / отмена; чужая бронь → 403 |
| GET | /api/admin/bookings | Все брони, необязательные date и building |
| DELETE | /api/admin/bookings/{id} | Отмена любой брони |
| POST | /api/admin/rooms | Создание аудитории |
| PUT / DELETE | /api/admin/rooms/{id} | Редактирование / архивирование |
| GET | /api/admin/stats?date=YYYY-MM-DD | Загрузка за 7 дней |
| GET | /api/admin/bookings.csv | CSV с защитой от формульных значений |

Даты ISO, время HH:MM, зона Asia/Yekaterinburg, рабочие часы 08:00–22:00. Создание возвращает 201. Пересечение активных броней → 409; соседние границы допустимы. PostgreSQL блокирует строку аудитории FOR UPDATE до завершения проверки и записи; SQLite использует BEGIN IMMEDIATE. Отмена сохраняет cancelled. Архивирование блокируется при будущих активных бронях. Администратор не создаёт брони согласно матрице ТЗ.

## Проверки

```powershell
.venv/Scripts/python -m pip install -r requirements-dev.txt
.venv/Scripts/python -m pytest backend/tests -q
cd frontend
npm run build
```

31 API-тест: восемь сценариев, границы и виды пересечений, конкурентные запросы, роли, регистрация, CRUD, CSV, сохранение после перезапуска, миграции, ограничения запросов и отзыв сессий. По умолчанию используется временная SQLite БД. TEST_DATABASE_URL включает PostgreSQL: каждый тест получает отдельную случайную схему и удаляет только её. Для CI используйте отдельную тестовую БД.

## Render + cron-job.org

1. Поместите проект в GitHub-репозиторий. В Render: New → Blueprint → выберите репозиторий. Используется `render.yaml`: Docker Web Service и PostgreSQL, регион Frankfurt, бесплатные планы.
2. Проверьте сгенерированный JWT_SECRET, подключение DATABASE_URL и health `/api/health`. После сборки откройте адрес сервиса, `/docs` и войдите демо-аккаунтом.
3. В cron-job.org создайте HTTP GET на `https://АДРЕС-СЕРВИСА/api/health`, каждые 10 минут. Никаких паролей приложения передавать не нужно. Проверьте Test run → 200 и `status: ok`.
4. Альтернатива через API: задайте CAMPUS_URL и CRONJOB_API_KEY локальными переменными окружения, выполните `python scripts/setup_cron.py`. Ключ не помещайте в Git.

Бесплатный Render засыпает после 15 минут без входящих запросов; cron уменьшает вероятность холодного старта, но не гарантирует доступность. Локальная файловая система Render временная — используйте PostgreSQL. Бесплатная PostgreSQL истекает через 30 дней. Источники: [Render Free](https://render.com/docs/free), [Blueprint](https://render.com/docs/blueprint-spec), [cron-job API](https://docs.cron-job.org/rest-api.html).

## Эксплуатация и границы интеграций

Личный кабинет позволяет менять имя и пароль, завершать все сессии. Восстановление забытого пароля выполняет оператор через `python -m backend.cli reset-password`. JWT действует 8 часов без refresh-токена; выход и смена пароля отзывают сессии на сервере. Производственная регистрация требует кода приглашения; можно установить REGISTRATION_MODE=closed.

Реальной интеграции с расписанием вуза нет по ТЗ. Gmail OAuth, email-подтверждение и отправка писем не подключены; календарь экспортируется в `.ics`. Для текущего сценария не нужны доступ к почтовому ящику и хранение Google-токенов. Seed используется только в демо. Alembic обновляет схему; production требует выполнения миграций до старта. Резервное копирование, восстановление, мониторинг, журнал действий и порядок обновления описаны в runbook.

Дизайн и источники компонентов: [THIRD_PARTY.md](THIRD_PARTY.md). План: [docs/PLAN.md](docs/PLAN.md). Демо: [docs/DEMO.md](docs/DEMO.md).

