from pydantic import BaseModel, Field


class TextChunk(BaseModel):
    chunk_id: str
    text: str = Field(min_length=1)
    start_char: int
    end_char: int


def chunk_text(text: str, *, chunk_size: int = 1200, overlap: int = 150) -> list[TextChunk]:
    cleaned = text.strip()

    if not cleaned:
        return []

    if chunk_size <= overlap:
        raise ValueError("chunk_size must be greater than overlap")

    chunks: list[TextChunk] = []
    start = 0
    index = 0

    while start < len(cleaned):
        end = min(start + chunk_size, len(cleaned))
        chunk = cleaned[start:end].strip()

        if chunk:
            chunks.append(
                TextChunk(
                    chunk_id=f"chunk_{index}",
                    text=chunk,
                    start_char=start,
                    end_char=end,
                )
            )

        if end >= len(cleaned):
            break

        start = end - overlap
        index += 1

    return chunks