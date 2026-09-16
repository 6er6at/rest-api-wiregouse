import os
import time
from contextlib import asynccontextmanager
from decimal import Decimal

import psycopg
from fastapi import FastAPI, HTTPException, status
from psycopg.errors import UniqueViolation
from pydantic import BaseModel, Field, field_validator


def get_connection():
    return psycopg.connect(
        host=os.getenv("DB_HOST", "db"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
    )


def init_db():
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL CHECK (length(trim(title)) > 0),
                sku TEXT NOT NULL UNIQUE,
                quantity INTEGER NOT NULL CHECK (quantity >= 0),
                price NUMERIC(12, 2) NOT NULL CHECK (price > 0)
            )
        """)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Повторяем подключение, пока PostgreSQL не будет готов
    for attempt in range(10):
        try:
            init_db()
            break
        except psycopg.OperationalError:
            if attempt == 9:
                raise
            time.sleep(3)

    yield


app = FastAPI(
    title="Warehouse REST API",
    version="1.0.0",
    lifespan=lifespan,
)


class ProductCreate(BaseModel):
    title: str = Field(min_length=1)
    sku: str = Field(min_length=1)
    quantity: int = Field(ge=0)
    price: Decimal = Field(gt=0, max_digits=12, decimal_places=2)

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Title must not be empty or whitespace")
        return value

class Product(ProductCreate):
    id: int


def product_to_dict(row):
    return {
        "id": row[0],
        "title": row[1],
        "sku": row[2],
        "quantity": row[3],
        "price": row[4],
    }


@app.post(
    "/api/v1/products/",
    status_code=status.HTTP_201_CREATED,
)
def create_product(product: ProductCreate):
    try:
        with get_connection() as conn:
            row = conn.execute(
                """
                INSERT INTO products (title, sku, quantity, price)
                VALUES (%s, %s, %s, %s)
                RETURNING id, title, sku, quantity, price
                """,
                (
                    product.title,
                    product.sku,
                    product.quantity,
                    product.price,
                ),
            ).fetchone()

        return product_to_dict(row)

    except UniqueViolation:
        raise HTTPException(
            status_code=409,
            detail="Product with this SKU already exists",
        )


@app.get("/api/v1/products/")
def get_products():
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, title, sku, quantity, price
            FROM products
            ORDER BY id
            """
        ).fetchall()

    return [product_to_dict(row) for row in rows]


@app.get("/api/v1/products/{product_id}")
def get_product(product_id: int):
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id, title, sku, quantity, price
            FROM products
            WHERE id = %s
            """,
            (product_id,),
        ).fetchone()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail="Product not found",
        )

    return product_to_dict(row)


@app.put("/api/v1/products/{product_id}")
def update_product(product_id: int, product: ProductCreate):
    try:
        with get_connection() as conn:
            row = conn.execute(
                """
                UPDATE products
                SET title = %s,
                    sku = %s,
                    quantity = %s,
                    price = %s
                WHERE id = %s
                RETURNING id, title, sku, quantity, price
                """,
                (
                    product.title,
                    product.sku,
                    product.quantity,
                    product.price,
                    product_id,
                ),
            ).fetchone()

        if row is None:
            raise HTTPException(
                status_code=404,
                detail="Product not found",
            )

        return product_to_dict(row)

    except UniqueViolation:
        raise HTTPException(
            status_code=409,
            detail="Product with this SKU already exists",
        )


@app.delete("/api/v1/products/{product_id}")
def delete_product(product_id: int):
    with get_connection() as conn:
        row = conn.execute(
            """
            DELETE FROM products
            WHERE id = %s
            RETURNING id
            """,
            (product_id,),
        ).fetchone()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail="Product not found",
        )

    return {"message": "Product deleted successfully"}
