# CampusFlow

Сервис поиска и бронирования аудиторий по кейсу IBS. FastAPI + SQLAlchemy, React + TypeScript. SQLite локально, PostgreSQL для Render. Поиск, занятость и выбор времени доступны на одном экране.

Два независимых режима: демонстрация для жюри и prod-ready конфигурация с чистой БД. Оба можно разместить на бесплатном Render; ограничения тарифа описаны ниже. Эксплуатация: [PRODUCTION.md](docs/PRODUCTION.md). Проверки: [VERIFICATION.md](docs/VERIFICATION.md).

## Демо: запуск локально

С Docker Desktop из корня проекта:

```powershell
docker compose -p campusflow up --build -d
```

Откройте http://127.0.0.1:8080 и http://127.0.0.1:8080/docs. Автоматически создаются учебные аккаунты, 12 аудиторий и стартовые брони. Локальная PostgreSQL сохраняется в отдельном volume. Остановка: `docker compose -p campusflow down`; без `-v`, чтобы сохранить данные.

Альтернатива без Docker: нужны Python 3.11+ и Node.js 22.12+.

```powershell
Copy-Item .env.example .env
powershell -ExecutionPolicy Bypass -File scripts/start.ps1
```

Сайт будет на http://127.0.0.1:8000; SQLite хранится в `campusflow.db`. Повторный запуск без установки: `.venv/Scripts/python -m uvicorn backend.main:app --env-file .env`.

## Prod-ready: запуск локально

Скопируйте `.env.production.example` в `.env.production`, если файла ещё нет. Задайте разные случайные POSTGRES_PASSWORD, JWT_SECRET и REGISTRATION_INVITE_CODE; рекомендуются hex-строки по 64 символа. Для получения одной строки: `python -c "import secrets; print(secrets.token_hex(32))"`. Не перезаписывайте уже настроенный файл с секретами.

```powershell
docker compose --env-file .env.production -f compose.production.yaml -p campusflow-prod-check up --build -d
docker compose --env-file .env.production -f compose.production.yaml -p campusflow-prod-check exec web python -m backend.cli create-admin --login operator --name "Администратор кампуса"
```

CLI запросит пароль администратора, минимум 12 символов. При уже существующем операторе используйте его пароль — повторное создание запрещено. Откройте http://127.0.0.1:8081. В этом режиме нет демо-аккаунтов и учебных аудиторий: администратор добавляет комнаты, студенты регистрируются по коду приглашения. Миграции запускаются отдельным контейнером, Swagger отключён.

Демо и prod-ready можно запускать одновременно: порты 8080/8081, контейнеры и volumes разделены. Остановка второго режима:

```powershell
docker compose --env-file .env.production -f compose.production.yaml -p campusflow-prod-check down
```

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

## Бесплатный Render: два сайта

| Режим | Blueprint Path | Данные | Вход |
|---|---|---|---|
| Демо хакатона | `render.yaml` | SQLite во временной файловой системе, seed после перезапуска | student1 / student2 / admin |
| Prod-ready приложение | `render.production.yaml` | Отдельная бесплатная Render PostgreSQL | Свой администратор и приглашённые студенты |

Демо специально не занимает бесплатную PostgreSQL: в одном Render workspace разрешена только одна такая БД. После перезапуска демо изменения и новые аккаунты могут исчезнуть, учебные данные создадутся заново. Не используйте демо для важных записей.

### 1. Загрузить изменения

В уже подключённом Git-репозитории:

```powershell
git add README.md docs/PRODUCTION.md render.yaml render.production.yaml backend/launch.py backend/tests/test_bootstrap.py
git commit -m "feat: support separate free demo and production deployments"
git push origin main
```

Убедитесь, что GitHub Actions завершился успешно. Не добавляйте `.env`, `.env.production` и резервные копии.

### 2. Развернуть демо

1. Render Dashboard → New → Blueprint → подключите `bodhiswaga/hackathon-cf`, ветка `main`.
2. Название Blueprint: `campusflow-demo`; Blueprint Path: `render.yaml`.
3. Проверьте, что создаётся только один Docker Web Service, план Free, без PostgreSQL. Нажмите Deploy Blueprint.
4. После сборки сохраните назначенный HTTPS-адрес. Откройте `/api/health` → `{"status":"ok"}`, затем сайт и демо-вход.

### 3. Развернуть prod-ready приложение

1. Создайте второй Blueprint из того же репозитория и ветки `main`.
2. Название: `campusflow-production`; Blueprint Path: `render.production.yaml`.
3. Задайте BOOTSTRAP_ADMIN_PASSWORD — уникальный пароль минимум 12 символов. Начальный логин: `operator`. Сохраните пароль в менеджере паролей.
4. Проверьте Free у web и PostgreSQL. Если бесплатная PostgreSQL в workspace уже занята, сначала используйте существующую инфраструктуру осознанно или освободите ненужный ресурс с сохранением его данных: второй Free Postgres создать нельзя. Не подключайте рабочий сайт к демо-данным.
5. Deploy Blueprint. Команда `python -m backend.launch` выполняет миграции, создаёт первого администратора и запускает сервер. Это заменяет недоступные на Free pre-deploy и Shell. Назначенный Render hostname автоматически добавляется в ALLOWED_HOSTS.
6. Откройте `/api/health`, войдите как `operator`, добавьте реальные аудитории. `/docs` должен возвращать 404, кнопок демо-входа нет.
7. В Environment веб-сервиса найдите сгенерированный REGISTRATION_INVITE_CODE: он нужен студентам при регистрации. JWT_SECRET и DATABASE_URL никому не передавайте.
8. После успешного первого входа удалите BOOTSTRAP_ADMIN_PASSWORD из Environment и примените изменения. Администратор останется в БД. Перезапуски не сбрасывают его пароль. Для собственного домена добавьте его точное имя в ALLOWED_HOSTS через запятую, без https и пути.

Сайты имеют разные URL и независимые JWT_SECRET. Учётные записи между ними не переносятся. Локальные БД и пароли также не загружаются в Render.

### 4. Два задания cron-job.org

В https://console.cron-job.org/ создайте два задания:

| Поле | Демо | Prod-ready |
|---|---|---|
| Title | CampusFlow demo health | CampusFlow production health |
| URL | `https://<demo-host>/api/health` | `https://<production-host>/api/health` |
| Method | GET | GET |
| Интервал | Каждые 10 минут | Каждые 10 минут |
| Авторизация / body | Пусто | Пусто |

Включите задания, добавьте email-уведомления о сбое и восстановлении. Для каждого выполните Test run → HTTP 200, затем проверьте History. При первом холодном старте запрос может завершиться таймаутом; откройте сайт, дождитесь запуска и повторите тест. Endpoint проверяет приложение и БД. Cron не выполняет миграции, не создаёт бэкап и не продлевает срок жизни PostgreSQL.

**Лимит работы двух сайтов.** Free workspace получает 750 instance-hours в месяц суммарно. Два сайта 24/7 расходуют 1440 часов за 30 дней: постоянный ping обоих исчерпает лимит примерно за 15,6 дня, после чего Render приостановит бесплатные web-сервисы до следующего месяца. Для хакатона можно включить оба ping на дни показа. Для всего месяца задайте обоим заданиям custom schedule: timezone Asia/Yekaterinburg, часы 09–19 включительно, минуты 0,10,20,30,40,50, все дни и месяцы. Это примерно 687 часов за 31 день с учётом 15 минут до сна; дополнительный пользовательский трафик вне окна тоже расходует лимит. Следите за Billing → Monthly Included Usage. Вне окна сайты доступны с холодным стартом.

Бесплатный Render засыпает после 15 минут без трафика, может перезапускаться и не гарантирует непрерывную доступность. Free PostgreSQL истекает через 30 дней, автоматических бэкапов нет: заранее сохраните дамп и перенесите данные до истечения. Prod-ready обозначает конфигурацию приложения; бесплатная инфраструктура подходит для демонстрации этой конфигурации и ограниченного пилота.

Источники: [Render Free](https://render.com/docs/free), [Blueprint](https://render.com/docs/blueprint-spec), [cron-job.org](https://cron-job.org/en/). Подробный регламент резервного копирования и восстановления: [PRODUCTION.md](docs/PRODUCTION.md).

## Эксплуатация и границы интеграций

Личный кабинет позволяет менять имя и пароль, завершать все сессии. Восстановление забытого пароля выполняет оператор через `python -m backend.cli reset-password`. JWT действует 8 часов без refresh-токена; выход и смена пароля отзывают сессии на сервере. Производственная регистрация требует кода приглашения; можно установить REGISTRATION_MODE=closed.

Реальной интеграции с расписанием вуза нет по ТЗ. Gmail OAuth, email-подтверждение и отправка писем не подключены; календарь экспортируется в `.ics`. Для текущего сценария не нужны доступ к почтовому ящику и хранение Google-токенов. Seed используется только в демо. Alembic обновляет схему; production требует выполнения миграций до запуска HTTP-сервера (на Free это делает backend.launch). Резервное копирование, восстановление, мониторинг, журнал действий и порядок обновления описаны в runbook.

Дизайн и источники компонентов: [THIRD_PARTY.md](THIRD_PARTY.md). План: [docs/PLAN.md](docs/PLAN.md). Демо: [docs/DEMO.md](docs/DEMO.md).

