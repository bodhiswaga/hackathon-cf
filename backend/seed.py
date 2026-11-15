import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import select
from .models import User, Room, Booking
from .security import hash_password

TIMEZONE = os.getenv('CAMPUS_TIMEZONE', 'Asia/Yekaterinburg')


def campus_now():
    return datetime.now(ZoneInfo(TIMEZONE))


def seed(session):
    if session.scalar(select(User.id).limit(1)):
        return
    password = os.getenv('DEMO_PASSWORD', 'campus2026')
    session.add_all([User(login='student1', display_name='Алексей Морозов', role='student', password_hash=hash_password(password)), User(login='student2', display_name='Мария Волкова', role='student', password_hash=hash_password(password)), User(login='admin', display_name='Анна Соколова', role='admin', password_hash=hash_password(password))])
    rows = [
        ('101', 'A', 1, 24, ['whiteboard', 'wifi', 'outlets'], 'Для семинаров и работы в небольших группах.'),
        ('203', 'A', 2, 48, ['projector', 'whiteboard', 'wifi'], 'Светлая аудитория с проектором.'),
        ('305', 'A', 3, 16, ['computers', 'whiteboard', 'wifi', 'outlets'], 'Компьютерный класс на 16 рабочих мест.'),
        ('101', 'B', 1, 32, ['projector', 'whiteboard', 'wifi', 'outlets'], 'Универсальная аудитория для занятий и встреч.'),
        ('204', 'B', 2, 60, ['projector', 'whiteboard', 'wifi'], 'Большая лекционная аудитория.'),
        ('108', 'B', 1, 12, ['whiteboard', 'wifi', 'outlets'], 'Тихая комната для проектной команды.'),
        ('301', 'B', 3, 18, ['computers', 'wifi', 'outlets'], 'Компьютерный класс.'),
        ('102', 'C', 1, 30, ['projector', 'whiteboard', 'wifi'], 'Семинарская аудитория.'),
        ('201', 'C', 2, 80, ['projector', 'whiteboard', 'wifi', 'outlets'], 'Лекционный зал для больших групп.'),
        ('205', 'C', 2, 20, ['whiteboard', 'wifi', 'outlets'], 'Столы можно объединить для совместной работы.'),
        ('401', 'A', 4, 100, ['projector', 'whiteboard', 'wifi'], 'Поточная аудитория.'),
        ('310', 'C', 3, 24, ['computers', 'projector', 'wifi', 'outlets'], 'Лаборатория для практических занятий.'),
    ]
    for name, building, floor, capacity, equipment, description in rows:
        session.add(Room(name=name, building=building, floor=floor, capacity=capacity, equipment=equipment, description=description))
    session.flush()
    today = campus_now().date()
    for offset in range(0, 8):
        for room_id, start, end, user_id, comment in [(1,'10:00','11:30',1,'Подготовка к семинару'),(2,'09:00','10:30',2,'Работа над проектом'),(4,'10:00','12:00',2,'Практическое занятие'),(5,'13:00','15:00',1,'Встреча группы'),(8,'15:00','16:30',2,'Репетиция выступления'),(9,'11:00','13:00',1,'Лекция'),(12,'09:30','11:00',2,'Лабораторная работа')]:
            session.add(Booking(room_id=room_id, user_id=user_id, date=today+timedelta(days=offset), start_time=start, end_time=end, comment=comment))
    session.commit()
