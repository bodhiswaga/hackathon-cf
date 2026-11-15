# CampusFlow

Сервис поиска и бронирования аудиторий: фильтры по корпусу, вместимости и оборудованию, календарь занятости, личные бронирования и панель администратора. Поддерживает светлую и тёмную тему, экспорт в календарь и CSV.

Стек: React + TypeScript, FastAPI, SQLAlchemy, PostgreSQL / SQLite.

## Открыть сайт

| Версия | Адрес | Как войти |
|---|---|---|
| Демо хакатона | [campusflow-78s7.onrender.com](https://campusflow-78s7.onrender.com) | Учебные аккаунты из таблицы ниже |
| Prod-ready | [campusflow-production.onrender.com](https://campusflow-production.onrender.com) | Собственный аккаунт; для регистрации нужен код приглашения от администратора |

Версии независимы: аккаунты и бронирования между ними не переносятся. На бесплатном Render первый запрос после простоя может потребовать ожидания запуска.

### Демонстрационная версия

1. Откройте [демо](https://campusflow-78s7.onrender.com).
2. Выберите демо-аккаунт на экране входа или введите данные вручную.
3. Войдите студентом, задайте дату и фильтры, выберите свободное время и подтвердите бронь.
4. В разделе «Мои бронирования» проверьте результат; там же можно отменить бронь или скачать событие для календаря.
5. Для управления аудиториями, просмотра всех броней и загрузки кампуса войдите администратором.

| Логин | Пароль | Роль |
|---|---|---|
| student1 | campus2026 | Студент |
| student2 | campus2026 | Студент |
| admin | campus2026 | Администратор |

Демо содержит учебные аудитории и бронирования. В Render оно использует временную SQLite: после пересоздания контейнера изменения могут исчезнуть, а учебные данные будут созданы заново.

### Prod-ready версия

1. Откройте [prod-ready сайт](https://campusflow-production.onrender.com).
2. Войдите в свой аккаунт. Для нового студента: откройте «Регистрация», укажите логин, имя, пароль и код приглашения, полученный у администратора.
3. Найдите аудиторию, выберите время и подтвердите бронь. Просмотр и отмена доступны в личных бронированиях.
4. Нажмите на аватар или имя внизу боковой панели (на телефоне сначала откройте меню). Откроются настройки профиля: личные данные, пароль, оформление и завершение всех сессий.

Демонстрационных аккаунтов в этой версии нет. Администратор создаётся при первом развёртывании и добавляет аудитории через интерфейс. Данные хранятся в отдельной PostgreSQL. Забытый пароль восстанавливает оператор по регламенту в [PRODUCTION.md](docs/PRODUCTION.md).

## Локальный запуск

Нужны Git и запущенный Docker Desktop с Docker Compose. Все команды ниже выполняются в PowerShell.

### Скачать проект

```powershell
git clone https://github.com/bodhiswaga/hackathon-cf.git
cd hackathon-cf
```

Если проект уже скачан, откройте терминал в его корневой папке. Первая сборка требует подключения к интернету.

### Демо

```powershell
docker compose -p campusflow up --build -d
```

Дождитесь запуска, затем откройте [http://127.0.0.1:8080](http://127.0.0.1:8080). Используйте демо-аккаунты из таблицы выше. Учебные данные создаются автоматически. Локальное демо использует PostgreSQL в Docker volume и сохраняет данные между перезапусками.

Проверка состояния и просмотр логов:

```powershell
docker compose -p campusflow ps
docker compose -p campusflow logs --tail=100 web
```

Остановка:

```powershell
docker compose -p campusflow down
```

### Prod-ready

1. Создайте файл настроек, если его ещё нет:

   ```powershell
   Copy-Item .env.production.example .env.production
   ```

   Если `.env.production` уже настроен, используйте его — не перезаписывайте секреты.

2. Откройте `.env.production` в редакторе. Замените примеры значений:

   | Переменная | Значение |
   |---|---|
   | POSTGRES_PASSWORD | Случайный пароль БД: 64 шестнадцатеричных символа |
   | JWT_SECRET | Другая случайная строка: 64 шестнадцатеричных символа |
   | REGISTRATION_INVITE_CODE | Третья случайная строка: код приглашения студентов |
   | ALLOWED_HOSTS | Для локального запуска оставьте `localhost,127.0.0.1` |

   При установленном Python 3 независимые строки можно получить так:

   ```powershell
   python -c "import secrets; print('\n'.join(secrets.token_hex(32) for _ in range(3)))"
   ```

   Файл с секретами не публикуйте. Пароль БД задаётся при первом создании volume; простое изменение переменной позднее не меняет пароль существующей БД.

3. Соберите и запустите приложение:

   ```powershell
   docker compose --env-file .env.production -f compose.production.yaml -p campusflow-prod-check up --build -d
   ```

4. При первом запуске создайте администратора:

   ```powershell
   docker compose --env-file .env.production -f compose.production.yaml -p campusflow-prod-check exec web python -m backend.cli create-admin --login operator --name "Администратор кампуса"
   ```

   Введите пароль минимум из 12 символов. При вводе символы не отображаются. Если этот логин уже создан, войдите с существующим паролем: повторно создавать его не нужно.

5. Откройте [http://127.0.0.1:8081](http://127.0.0.1:8081), войдите как `operator` и добавьте аудитории. Для регистрации студентов используйте REGISTRATION_INVITE_CODE из `.env.production`. Демо-данные в этом режиме не загружаются; миграции выполняются автоматически отдельным контейнером.

Проверка состояния и просмотр логов:

```powershell
docker compose --env-file .env.production -f compose.production.yaml -p campusflow-prod-check ps
docker compose --env-file .env.production -f compose.production.yaml -p campusflow-prod-check logs --tail=100 web
```

Остановка:

```powershell
docker compose --env-file .env.production -f compose.production.yaml -p campusflow-prod-check down
```

Оба режима можно запускать одновременно: у них разные порты, контейнеры и volumes. Команды `down` сохраняют БД; не добавляйте `-v`, если данные нужны. Локальные данные не синхронизируются с размещёнными сайтами.

## Развёртывание на Render

Для повторного развёртывания подключите [репозиторий](https://github.com/bodhiswaga/hackathon-cf) в Render через **New → Blueprint**, ветка `main`. Создайте два отдельных Blueprint:

| Версия | Blueprint Path | Ресурсы |
|---|---|---|
| Демо | `render.yaml` | Один Free Docker Web Service, временная SQLite |
| Prod-ready | `render.production.yaml` | Free Docker Web Service и Free PostgreSQL |

Для prod-ready Blueprint:

1. Задайте BOOTSTRAP_ADMIN_PASSWORD — уникальный пароль минимум из 12 символов; начальный логин `operator`.
2. Проверьте бесплатные планы ресурсов и нажмите **Deploy Blueprint**. Команда запуска выполняет миграции и создаёт администратора; адрес Render автоматически добавляется в разрешённые hostname.
3. Откройте сайт и войдите администратором. Затем удалите BOOTSTRAP_ADMIN_PASSWORD из **Environment** веб-сервиса и примените изменения. Аккаунт и его пароль сохранятся.
4. Возьмите REGISTRATION_INVITE_CODE в **Environment** для приглашения студентов. JWT_SECRET и DATABASE_URL не передавайте пользователям.
5. Проверьте `/api/health`: ожидается HTTP 200 и `{"status":"ok"}`. В prod-ready `/docs` отключён.

Данные локального запуска при деплое не загружаются. Для собственного домена добавьте его hostname в ALLOWED_HOSTS без `https://` и пути.

## cron-job.org и ограничения бесплатного хостинга

В [консоли cron-job.org](https://console.cron-job.org/) создайте два включённых задания с методом GET и интервалом 10 минут:

| Задание | URL |
|---|---|
| CampusFlow demo health | https://campusflow-78s7.onrender.com/api/health |
| CampusFlow production health | https://campusflow-production.onrender.com/api/health |

Авторизация, заголовки и тело запроса не нужны. Включите email-уведомления о сбое и восстановлении. Выполните **Test run** для каждого задания, убедитесь в HTTP 200 и проверьте последующие запуски в **History**.

Бесплатный Render предоставляет 750 часов работы web-сервисов в месяц суммарно на workspace. Два сайта 24/7 потребуют около 1440 часов за 30 дней. Для дней хакатона можно включить оба задания круглосуточно. Для работы в течение месяца задайте обоим **custom schedule**: timezone `Asia/Yekaterinburg`, часы `09–19` включительно, минуты `0,10,20,30,40,50`, все дни и месяцы. Вне этого окна возможен холодный старт. Дополнительные обращения также расходуют часы — следите за **Billing → Monthly Included Usage**.

В workspace доступна одна бесплатная PostgreSQL; она используется prod-ready версией. БД истекает через 30 дней и не имеет автоматических бэкапов: до истечения сохраните дамп и перенесите данные. Cron уменьшает вероятность засыпания, но не продлевает БД и не гарантирует постоянную доступность. Prod-ready обозначает настройки приложения; бесплатный хостинг имеет перечисленные ограничения. [Условия Render Free](https://render.com/docs/free).

## API

Все пути начинаются с `/api`, данные передаются в JSON. Получите `accessToken` через POST `/api/auth/login` с полями `login` и `password`, затем передавайте заголовок `Authorization: Bearer <accessToken>`. В Swagger демо токен вводится через **Authorize**.

| Метод и путь | Назначение |
|---|---|
| POST `/auth/login`, `/auth/register` | Вход / регистрация студента; в prod-ready нужен `inviteCode` |
| GET `/auth/me` | Текущий пользователь |
| PATCH `/auth/profile` | Изменение `displayName` |
| POST `/auth/password` | Смена пароля: `currentPassword`, `newPassword` |
| POST `/auth/logout`, `/auth/logout-all` | Завершение текущей / всех сессий |
| GET `/rooms` | Фильтры: `building`, `minCapacity`, `equipment`, `date`, `startTime`, `endTime` |
| GET `/rooms/{id}`, `/rooms/{id}/free-slots?date=YYYY-MM-DD` | Карточка аудитории / свободные интервалы |
| POST `/bookings` | Создание: `roomId`, `date`, `startTime`, `endTime`, необязательный `comment` |
| GET `/bookings/my`, `/bookings/{id}` | Свои брони / отдельная бронь |
| DELETE `/bookings/{id}` | Отмена своей брони |
| GET `/admin/bookings` | Все брони, только admin |
| DELETE `/admin/bookings/{id}` | Отмена любой брони, только admin |
| POST `/admin/rooms`, PUT / DELETE `/admin/rooms/{id}` | Создание, изменение / архивирование аудитории, только admin |
| GET `/admin/stats`, `/admin/bookings.csv`, `/admin/audit` | Загрузка кампуса, CSV и журнал действий, только admin |
| GET `/meta`, `/health` | Настройки кампуса / проверка приложения и БД, без авторизации |

Время — `HH:MM`, даты — `YYYY-MM-DD`, часовой пояс — Asia/Yekaterinburg; часы бронирования 08:00–22:00. Создание возвращает 201; пересечение активной брони — 409 `BOOKING_CONFLICT`, чужая бронь — 403 `FORBIDDEN`. Касание границ интервалов допустимо. Отмена сохраняет статус `cancelled` и освобождает слот. Удаление аудитории архивирует её; будущие активные брони сначала нужно отменить. Администратор не создаёт брони.

Ошибка имеет формат `{"error":{"code":"BOOKING_CONFLICT","message":"…"}}`. Полный контракт: Swagger `/docs` и OpenAPI `/openapi.json` локального демо. Интеграция с расписанием вуза и почтовая отправка не подключены; экспорт в календарь выполняется файлом `.ics`.

## Документация и проверки

- [Эксплуатация, резервное копирование и восстановление](docs/PRODUCTION.md).
- [Результаты проверок](docs/VERIFICATION.md).
- [Соответствие ТЗ и восемь сценариев приёмки](docs/ACCEPTANCE.md).
- [Сценарий демонстрации](docs/DEMO.md).
- [Источники компонентов интерфейса](THIRD_PARTY.md).
- [Swagger демо](https://campusflow-78s7.onrender.com/docs).

CI проверяет backend на SQLite и PostgreSQL и собирает frontend и Docker-образ. Для локального запуска API-тестов нужны Python 3.11+ и отдельное виртуальное окружение:

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt
.venv/Scripts/python -m pytest backend/tests -q
```
