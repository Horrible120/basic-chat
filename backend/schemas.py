from pydantic import BaseModel, Field, field_validator


def clean_text(value: str, *, max_length: int, label: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError(f"{label}不能为空")
    if len(value) > max_length:
        raise ValueError(f"{label}不能超过{max_length}个字符")
    return value


class ClientPacket(BaseModel):
    type: str
    content: str = Field(default="")

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        return clean_text(value, max_length=2000, label="消息")
