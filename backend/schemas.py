from datetime import date as Date
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

EQUIPMENT = {'projector': 'Проектор', 'whiteboard': 'Доска', 'computers': 'Компьютеры', 'wifi': 'Wi-Fi', 'outlets': 'Розетки'}


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class Login(Input):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=False)
    login: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=128)


class PersonName(Input):
    displayName: str | None = Field(default=None, min_length=2, max_length=100)
    firstName: str | None = Field(default=None, min_length=1, max_length=50)
    lastName: str | None = Field(default=None, min_length=1, max_length=50)

    @model_validator(mode='after')
    def names(self):
        if self.firstName is not None or self.lastName is not None:
            if not (self.firstName and self.firstName.strip() and self.lastName and self.lastName.strip()):
                raise ValueError('Укажите имя и фамилию')
            self.firstName, self.lastName = self.firstName.strip(), self.lastName.strip()
            self.displayName = self.firstName+' '+self.lastName
        elif self.displayName and self.displayName.strip():
            self.displayName = self.displayName.strip()
            first, _, last = self.displayName.partition(' ')
            self.firstName, self.lastName = first[:50], last[:50]
        else:
            raise ValueError('Укажите имя и фамилию')
        if len(self.displayName)>100:
            raise ValueError('Имя и фамилия вместе — до 100 символов')
        return self


class Register(PersonName):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=False)
    login: str = Field(min_length=3, max_length=40, pattern=r'^[a-zA-Z0-9_.-]+$')
    password: str = Field(min_length=8, max_length=128)
    inviteCode: str = Field(default='', max_length=128)


class ProfileInput(PersonName):
    pass


class PasswordInput(Input):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=False)
    currentPassword: str = Field(min_length=1, max_length=128)
    newPassword: str = Field(min_length=12, max_length=128)


class BookingInput(Input):
    requirements: list[str] = Field(default_factory=list, max_length=5)

    @field_validator('requirements')
    @classmethod
    def valid_requirements(cls, values):
        if set(values) - EQUIPMENT.keys():
            raise ValueError('Неизвестное оборудование')
        return sorted(set(values))

    roomId: int = Field(gt=0)
    date: Date
    startTime: str = Field(pattern=r'^([01]\d|2[0-3]):[0-5]\d$')
    endTime: str = Field(pattern=r'^([01]\d|2[0-3]):[0-5]\d$')
    comment: str = Field(default='', max_length=300)


class RoomInput(Input):
    name: str = Field(min_length=1, max_length=60)
    building: str = Field(min_length=1, max_length=30)
    floor: int = Field(ge=-2, le=100)
    capacity: int = Field(ge=1, le=1000)
    equipment: list[str] = Field(default_factory=list, max_length=5)
    description: str = Field(default='', max_length=300)

    @field_validator('equipment')
    @classmethod
    def valid_equipment(cls, values):
        if any(v not in EQUIPMENT for v in values):
            raise ValueError('Неизвестное оборудование')
        return sorted(set(values))
