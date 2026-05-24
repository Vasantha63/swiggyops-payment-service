from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from prometheus_client import Counter, Histogram, generate_latest
from fastapi.responses import PlainTextResponse
import sqlite3
import uvicorn

app = FastAPI(title="SwiggyOps Payment Service")

# Prometheus metrics
request_counter = Counter("payment_requests_total", "Total requests", ["method", "endpoint"])
request_latency = Histogram("payment_request_latency_seconds", "Request latency")

# Database setup
def get_db():
    conn = sqlite3.connect("payments.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            customer_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            payment_method TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            transaction_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Sample data
    conn.execute("INSERT OR IGNORE INTO payments (id, order_id, customer_id, amount, payment_method, status, transaction_id) VALUES (1, 1, 101, 360.0, 'UPI', 'success', 'TXN123456')")
    conn.execute("INSERT OR IGNORE INTO payments (id, order_id, customer_id, amount, payment_method, status, transaction_id) VALUES (2, 2, 102, 299.0, 'Card', 'pending', 'TXN123457')")
    conn.commit()
    conn.close()

init_db()

# Models
class Payment(BaseModel):
    order_id: int
    customer_id: int
    amount: float
    payment_method: str

class PaymentStatus(BaseModel):
    status: str
    transaction_id: Optional[str] = None

# Payment Routes
@app.get("/payments")
def get_payments():
    request_counter.labels(method="GET", endpoint="/payments").inc()
    conn = get_db()
    payments = conn.execute("SELECT * FROM payments").fetchall()
    conn.close()
    return [dict(p) for p in payments]

@app.get("/payments/{payment_id}")
def get_payment(payment_id: int):
    request_counter.labels(method="GET", endpoint="/payments/id").inc()
    conn = get_db()
    payment = conn.execute("SELECT * FROM payments WHERE id=?", (payment_id,)).fetchone()
    conn.close()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    return dict(payment)

@app.post("/payments")
def create_payment(payment: Payment):
    request_counter.labels(method="POST", endpoint="/payments").inc()
    import random
    import string
    transaction_id = "TXN" + "".join(random.choices(string.digits, k=8))
    conn = get_db()
    cursor = conn.execute(
        "INSERT INTO payments (order_id, customer_id, amount, payment_method, status, transaction_id) VALUES (?, ?, ?, ?, ?, ?)",
        (payment.order_id, payment.customer_id, payment.amount, payment.payment_method, "success", transaction_id)
    )
    conn.commit()
    conn.close()
    return {"id": cursor.lastrowid, "message": "Payment successful!", "transaction_id": transaction_id, "status": "success"}

@app.put("/payments/{payment_id}/status")
def update_payment_status(payment_id: int, status: PaymentStatus):
    request_counter.labels(method="PUT", endpoint="/payments/status").inc()
    conn = get_db()
    conn.execute("UPDATE payments SET status=?, transaction_id=? WHERE id=?",
                 (status.status, status.transaction_id, payment_id))
    conn.commit()
    conn.close()
    return {"message": "Payment status updated!", "status": status.status}

@app.get("/payments/order/{order_id}")
def get_payment_by_order(order_id: int):
    request_counter.labels(method="GET", endpoint="/payments/order").inc()
    conn = get_db()
    payment = conn.execute("SELECT * FROM payments WHERE order_id=?", (order_id,)).fetchone()
    conn.close()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found for this order")
    return dict(payment)

@app.get("/health")
def health():
    return {"status": "healthy", "service": "payment-service"}

@app.get("/metrics", response_class=PlainTextResponse)
def metrics():
    return generate_latest()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8005)