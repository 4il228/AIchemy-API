import re

from pydantic import BaseModel, Field, field_validator

# Никнейм: только безопасный алфавит (защита от XSS/инъекций в отображении)
_NICKNAME_RE = re.compile(r"^[a-zA-Z0-9_-]{3,50}$")


class RegisterRequest(BaseModel):
    nickname: str = Field(min_length=3, max_length=50)
    # Верхняя граница длины пароля защищает Argon2 от DoS сверхдлинным вводом
    password: str = Field(min_length=8, max_length=128)

    @field_validator("nickname")
    @classmethod
    def validate_nickname(cls, v: str) -> str:
        if not _NICKNAME_RE.fullmatch(v):
            raise ValueError(
                "Никнейм: 3–50 символов, только латиница, цифры, '_' и '-'"
            )
        return v

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        # Минимальная политика сложности: буква + цифра
        if not re.search(r"[A-Za-zА-Яа-я]", v) or not re.search(r"\d", v):
            raise ValueError("Пароль должен содержать хотя бы одну букву и одну цифру")
        return v


class LoginRequest(BaseModel):
    # Без валидации формата: любые неверные данные дают единый 401,
    # чтобы формат ошибки не выдавал информацию о правилах никнеймов
    nickname: str = Field(max_length=50)
    password: str = Field(max_length=128)


class UserResponse(BaseModel):
    id: int
    nickname: str


class MessageResponse(BaseModel):
    message: str


class CraftRequest(BaseModel):
    element_1: str
    element_2: str


class CraftResponse(BaseModel):
    result: str
    description: str
    image_url: str = Field(
        description="Относительный URL сгенерированного изображения (например, /images/result.png). "
        "В Scalar после тестового запроса картинка показывается дополнительно под JSON-ответом.",
        json_schema_extra={
            "format": "uri",
            "examples": ["/images/voda_ogon.png"],
        },
    )
    creator_id: int
    creator_nickname: str
