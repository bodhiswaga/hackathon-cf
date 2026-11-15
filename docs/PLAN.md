# CampusFlow — план реализации

Источник: 25 страниц исходного PDF. Бюджет: около 5 часов.

## Этапы
1. 0:00–0:30: требования, контракт, дизайн, инфраструктура.
2. 0:30–1:50: API, модель данных, авторизация, транзакции, seed.
3. 1:50–3:30: интерфейс студента и администратора, интеграция.
4. 3:30–4:20: API-приёмка, конкуренция, визуальная и мобильная проверка.
5. 4:20–5:00: документация, Compose, Render и cron-job.org.

## Архитектура
- FastAPI / SQLAlchemy 2 / PostgreSQL; SQLite для запуска без инфраструктуры.
- React / TypeScript / Vite; production-сборка обслуживается FastAPI с того же origin.
- User, Room, Booking. Отмена сохраняет историю. Удаление аудитории — архивирование; активные будущие брони блокируют его.
- JWT на 8 часов, пароли PBKDF2, права проверяются сервером. Администратор не создаёт брони.
- Интервалы полуоткрытые: [start, end). Пересечение: old.start < new.end AND old.end > new.start.
- PostgreSQL: SELECT FOR UPDATE на аудитории сериализует создание брони. SQLite: BEGIN IMMEDIATE перед чтением занятости. Не использовать обычную проверку без транзакционной блокировки.
- Часовой пояс кампуса Asia/Yekaterinburg; часы 08:00–22:00; прошлое нельзя бронировать.
- Seed идемпотентный, 12 аудиторий, student1, student2, admin, даты относительно первого запуска. Не сбрасывать данные при рестарте.
- Render Docker web service + managed PostgreSQL. GET /api/health для cron-job.org раз в 10 минут; конфигурация и ручной fallback в README.

## API-контракт
JSON camelCase. Ошибка: {error: {code, message, ...}}.
POST /api/auth/login, GET /api/auth/me, GET /api/meta.
GET /api/rooms?building=&minCapacity=&equipment=&date=&startTime=&endTime=.
GET /api/rooms/{id}, GET /api/rooms/{id}/free-slots?date=.
POST /api/bookings, GET /api/bookings/my, GET /api/bookings/{id}, DELETE /api/bookings/{id}.
GET /api/admin/bookings, DELETE /api/admin/bookings/{id}.
POST /api/admin/rooms, PUT /api/admin/rooms/{id}, DELETE /api/admin/rooms/{id}.
GET /api/admin/stats, GET /api/admin/bookings.csv.
Swagger /docs, OpenAPI /openapi.json. Успех создания 201; конфликт 409; чужая бронь/роль 403.

## Дизайн
Основной экран — инструмент поиска с сеткой занятости и боковой панелью бронирования, без посадочной страницы.
Golos Text; фон #F5F6F2, поверхности #FFFFFF, хвойный #244C43, жёлтый #E6C56A, графит #28332F, ошибка #A94F46.
Номер аудитории — главный визуальный акцент. Корпуса различаются табличками. Цвет сопровождается текстом.
21st: Calendar Scheduler (ruixen.ui, 8228) и Sidebar 1 (uiable, 19371). Адаптируем реальные исходники, сохраняем атрибуцию в THIRD_PARTY.md.
На мобильном: компактная навигация, список аудиторий, календарь и форма в доступном диалоге. Фокус, Escape, подписи полей, состояния загрузки, повтор запроса.

## Приёмка
1. Фильтры возвращают только подходящие аудитории.
2. Свободные интервалы не пересекают активные брони.
3. Создание даёт 201 и отображается в моих бронях.
4. Конфликт даёт 409, в том числе конкурентные запросы.
5. Отмена возвращает слот, сохраняет cancelled.
6. Чужая бронь недоступна для просмотра/отмены, 403.
7. Администратор видит и отменяет все брони, CRUD ограничен ролью.
8. Чистый запуск, seed и Swagger работают по README.

Бонусы после MVP: JWT, статистика, CSV, рекомендации по вместимости, Compose, тесты.
