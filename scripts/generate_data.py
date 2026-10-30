"""Sinh dữ liệu thương mại điện tử Việt Nam (giả lập) vào DuckDB.

Chạy:  python scripts/generate_data.py --orders 40000 --seed 42
Kết quả: data/ecommerce.duckdb

Các "bẫy" cố ý (để eval và critic agent có việc làm):
  1. customers.province có nhiều cách viết (HCM / TP.HCM / Sài Gòn ...)
  2. orders.order_ts lưu UTC; giờ Việt Nam = UTC+7 (đơn 22h-24h VN rơi sang ngày hôm sau theo UTC)
  3. ~12% đơn có 2 dòng payments (ví + COD) -> JOIN payments làm nhân dòng
  4. "Doanh thu" mơ hồ: gộp cả cancelled/returned hay chỉ completed?
  5. order_items.unit_price khác products.price (giá flash-sale / giá lúc mua)
  6. Đơn gần đây còn 'delivering', chưa có delivered_ts
"""
import argparse
import random
from datetime import date, datetime, timedelta
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "ecommerce.duckdb"
SCHEMA_PATH = ROOT / "src" / "schema.sql"

START = date(2024, 1, 1)
END = date(2026, 9, 30)

HO = ["Nguyễn", "Trần", "Lê", "Phạm", "Hoàng", "Huỳnh", "Phan", "Vũ", "Võ", "Đặng", "Bùi", "Đỗ", "Hồ", "Ngô", "Dương", "Lý"]
DEM = ["Văn", "Thị", "Minh", "Ngọc", "Quốc", "Thanh", "Hữu", "Anh", "Gia", "Đức", "Thùy", "Khánh"]
TEN = ["An", "Bình", "Châu", "Dũng", "Giang", "Hà", "Hải", "Hạnh", "Hiếu", "Hoa", "Hùng", "Huy", "Khoa", "Lan",
       "Linh", "Long", "Mai", "Nam", "Ngân", "Nhi", "Phúc", "Phương", "Quân", "Quỳnh", "Sơn", "Thảo", "Trang",
       "Trung", "Tú", "Tuấn", "Vy", "Yến"]

# (tên chuẩn, trọng số dân số/đơn hàng, các cách viết khác)
PROVINCES = [
    ("TP. Hồ Chí Minh", 28, ["HCM", "TP.HCM", "Sài Gòn", "Ho Chi Minh"]),
    ("Hà Nội", 22, ["HN", "Ha Noi", "Hanoi"]),
    ("Đà Nẵng", 6, []), ("Hải Phòng", 5, []), ("Cần Thơ", 4, []),
    ("Bình Dương", 5, []), ("Đồng Nai", 5, []), ("Khánh Hòa", 3, []),
    ("Thừa Thiên Huế", 2, []), ("Nghệ An", 3, []), ("Thanh Hóa", 3, []),
    ("Quảng Ninh", 2, []), ("Lâm Đồng", 2, []), ("Long An", 2, []),
    ("Bà Rịa - Vũng Tàu", 2, []), ("Bắc Ninh", 2, []), ("Quảng Nam", 2, []),
    ("An Giang", 1, []), ("Bình Định", 1, []), ("Đắk Lắk", 1, []),
]

# gốc -> (khoảng giá VND, [danh mục con], [mẫu tên sản phẩm])
CATEGORY_TREE = {
    "Điện thoại & Phụ kiện": ((150_000, 25_000_000), ["Điện thoại", "Ốp lưng", "Sạc & Cáp", "Tai nghe"],
                              ["Điện thoại", "Ốp lưng", "Cáp sạc", "Tai nghe"]),
    "Thời trang nữ": ((80_000, 1_200_000), ["Áo", "Váy", "Quần", "Túi xách"], ["Áo thun nữ", "Váy xòe", "Quần jean nữ", "Túi đeo chéo"]),
    "Thời trang nam": ((90_000, 1_500_000), ["Áo", "Quần", "Giày dép"], ["Áo sơ mi nam", "Quần kaki", "Giày sneaker nam"]),
    "Mẹ & Bé": ((50_000, 2_000_000), ["Bỉm & Tã", "Sữa", "Đồ chơi"], ["Bỉm dán", "Sữa bột", "Đồ chơi gỗ"]),
    "Nhà cửa & Đời sống": ((40_000, 5_000_000), ["Đồ bếp", "Nội thất", "Đồ gia dụng"], ["Nồi chiên không dầu", "Kệ để đồ", "Máy xay sinh tố"]),
    "Sức khỏe & Làm đẹp": ((30_000, 1_800_000), ["Chăm sóc da", "Trang điểm", "Thực phẩm chức năng"], ["Kem chống nắng", "Son môi", "Vitamin C"]),
    "Thực phẩm & Đồ uống": ((15_000, 600_000), ["Đồ ăn vặt", "Cà phê & Trà", "Thực phẩm khô"], ["Bánh tráng trộn", "Cà phê rang xay", "Hạt điều"]),
    "Máy tính & Laptop": ((200_000, 40_000_000), ["Laptop", "Chuột & Bàn phím", "Linh kiện"], ["Laptop văn phòng", "Chuột không dây", "SSD"]),
}
ADJ = ["cao cấp", "chính hãng", "giá rẻ", "bản mới", "hot trend", "loại 1", "nhập khẩu", "tiện lợi"]

CARRIERS = ["GHN", "GHTK", "ViettelPost", "JT"]
SALE_DAYS = [(1, 1), (2, 2), (3, 3), (4, 4), (5, 5), (6, 6), (7, 7), (8, 8), (9, 9), (10, 10), (11, 11), (12, 12)]
# ngày sale lớn có trọng số cao hơn
BIG_SALES = {(9, 9): 3.0, (10, 10): 3.0, (11, 11): 5.0, (12, 12): 4.0, (6, 6): 2.5}


def rand_name(rng):
    return f"{rng.choice(HO)} {rng.choice(DEM)} {rng.choice(TEN)}"


def pick_province(rng, messy_rate=0.0):
    names = [p[0] for p in PROVINCES]
    weights = [p[1] for p in PROVINCES]
    idx = rng.choices(range(len(PROVINCES)), weights=weights)[0]
    std, _, variants = PROVINCES[idx]
    if variants and rng.random() < messy_rate:
        return rng.choice(variants)
    return std


def build_dimensions(rng, n_customers, n_sellers, n_products):
    # categories
    cats, leaf_info = [], []
    cid = 1
    for root, (price_rng, children, templates) in CATEGORY_TREE.items():
        root_id = cid
        cats.append((root_id, root, None))
        cid += 1
        for i, ch in enumerate(children):
            cats.append((cid, ch, root_id))
            leaf_info.append((cid, price_rng, templates[i % len(templates)]))
            cid += 1
    categories = pd.DataFrame(cats, columns=["category_id", "name_vi", "parent_id"])

    # customers
    total_days = (END - START).days
    cust = []
    for i in range(1, n_customers + 1):
        name = rand_name(rng)
        signup = START + timedelta(days=int(total_days * rng.random() ** 1.3))
        email = f"user{i}@example.com" if rng.random() > 0.05 else None
        cust.append((i, name, email, pick_province(rng, messy_rate=0.12), signup))
    customers = pd.DataFrame(cust, columns=["customer_id", "full_name", "email", "province", "signup_date"])

    # sellers
    sel = []
    for i in range(1, n_sellers + 1):
        sel.append((i, f"Shop {rng.choice(TEN)} {rng.choice(['Store', 'Official', 'Mall', 'Home', '88', 'Plus'])} {i}",
                    pick_province(rng), rng.random() < 0.15,
                    START + timedelta(days=int(total_days * 0.6 * rng.random()))))
    sellers = pd.DataFrame(sel, columns=["seller_id", "shop_name", "province", "is_mall", "joined_date"])

    # products
    prods = []
    for i in range(1, n_products + 1):
        cat_id, (lo, hi), tpl = rng.choice(leaf_info)
        price = int(np.exp(rng.uniform(np.log(lo), np.log(hi))) // 1000 * 1000) or lo
        created = datetime.combine(START + timedelta(days=int(total_days * 0.7 * rng.random())), datetime.min.time())
        prods.append((i, rng.randint(1, n_sellers), cat_id, f"{tpl} {rng.choice(ADJ)} #{i}", max(price, 5000), created))
    products = pd.DataFrame(prods, columns=["product_id", "seller_id", "category_id", "name", "price", "created_at"])

    # vouchers: mỗi tháng 1-2 voucher quanh ngày sale + vài voucher freeship
    vouchers, vid = [], 1
    d = START
    while d <= END:
        for (m, dd) in SALE_DAYS:
            if d.month == m and d.day == dd:
                vouchers.append((vid, f"SALE{m}{dd}_{d.year}", "percent", rng.choice([5, 8, 10, 15]),
                                 rng.choice([100_000, 200_000, 300_000]), d - timedelta(days=1), d + timedelta(days=1)))
                vid += 1
                vouchers.append((vid, f"GIAM{m}{dd}_{d.year}", "fixed", rng.choice([20_000, 30_000, 50_000]),
                                 rng.choice([150_000, 250_000]), d, d))
                vid += 1
        d += timedelta(days=1)
    # voucher quanh năm
    for y in range(START.year, END.year + 1):
        vouchers.append((vid, f"NEWUSER{y}", "fixed", 30_000, 100_000, date(y, 1, 1), date(y, 12, 31)))
        vid += 1
    voucher_df = pd.DataFrame(vouchers, columns=["voucher_id", "code", "discount_type", "value", "min_order_value",
                                                 "start_date", "end_date"])
    return categories, customers, sellers, products, voucher_df


def day_weights():
    days = [START + timedelta(days=i) for i in range((END - START).days + 1)]
    w = []
    for d in days:
        growth = 1 + 1.2 * ((d - START).days / (END - START).days)       # tăng trưởng theo thời gian
        dow = 1.15 if d.weekday() >= 5 else 1.0
        sale = BIG_SALES.get((d.month, d.day), 1.8 if d.day == d.month else 1.0)
        payday = 1.15 if d.day in (1, 2, 15, 16, 30) else 1.0
        w.append(growth * dow * sale * payday)
    w = np.array(w)
    return days, w / w.sum()


def generate_orders(rng, nprng, n_orders, customers, products, vouchers):
    n_cust, n_prod = len(customers), len(products)
    days, probs = day_weights()
    day_idx = nprng.choice(len(days), size=n_orders, p=probs)
    # giờ VN: cao điểm 11-13h và 19-23h
    hour_w = np.array([1, 1, .5, .3, .3, .5, 1, 2, 3, 3, 3.5, 4, 4, 3.5, 3, 3, 3, 3.5, 4, 5, 6, 6, 5, 3], dtype=float)
    hour_w /= hour_w.sum()
    hours_vn = nprng.choice(24, size=n_orders, p=hour_w)

    # độ phổ biến sản phẩm kiểu Zipf; khách mua lặp (cohort/retention có ý nghĩa)
    prod_pop = 1 / np.arange(1, n_prod + 1) ** 0.8
    prod_pop /= prod_pop.sum()
    perm = nprng.permutation(n_prod)
    cust_pop = nprng.pareto(2.0, n_cust) + 1
    cust_pop /= cust_pop.sum()
    signup = pd.to_datetime(customers["signup_date"]).dt.date.values
    prod_price = dict(zip(products["product_id"], products["price"]))

    vouch = vouchers.to_dict("records")
    now_cut = END - timedelta(days=10)

    orders, items, payments, shipments, reviews = [], [], [], [], []
    oi_id = pay_id = ship_id = rev_id = 1

    for k in range(n_orders):
        oid = 10_000_000 + k + 1
        d = days[day_idx[k]]
        # chọn khách đã đăng ký trước ngày đặt
        for _ in range(8):
            c = int(nprng.choice(n_cust, p=cust_pop))
            if signup[c] <= d:
                break
        else:
            c = int(nprng.integers(0, n_cust))
            d = max(d, signup[c])
        cust_id = c + 1

        vn_dt = datetime.combine(d, datetime.min.time()) + timedelta(hours=int(hours_vn[k]),
                                                                    minutes=int(rng.randint(0, 59)),
                                                                    seconds=int(rng.randint(0, 59)))
        order_ts = vn_dt - timedelta(hours=7)  # lưu UTC

        # items
        n_items = int(nprng.choice([1, 2, 3, 4], p=[.62, .25, .09, .04]))
        subtotal = 0
        order_items = []
        for _ in range(n_items):
            pid = int(perm[nprng.choice(n_prod, p=prod_pop)]) + 1
            qty = int(nprng.choice([1, 2, 3], p=[.8, .15, .05]))
            unit = int(prod_price[pid] * rng.uniform(0.85, 1.0) // 1000 * 1000) or prod_price[pid]
            order_items.append((oi_id, oid, pid, qty, unit))
            subtotal += qty * unit
            oi_id += 1

        # voucher
        voucher_id, disc = None, 0
        if rng.random() < 0.38:
            ok = [v for v in vouch if v["start_date"] <= d <= v["end_date"] and subtotal >= v["min_order_value"]]
            if ok:
                v = rng.choice(ok)
                voucher_id = int(v["voucher_id"])
                disc = int(subtotal * v["value"] / 100) if v["discount_type"] == "percent" else int(v["value"])
                disc = min(disc, subtotal)

        ship_fee = 0 if (subtotal >= 300_000 and rng.random() < 0.6) else rng.choice([15_000, 22_000, 30_000, 35_000, 45_000])
        total = subtotal - disc + ship_fee

        # trạng thái
        if d > now_cut and rng.random() < 0.7:
            status = "delivering"
        else:
            r = rng.random()
            status = "completed" if r < 0.87 else ("cancelled" if r < 0.95 else "returned")

        orders.append((oid, cust_id, order_ts, status, voucher_id, ship_fee))
        items.extend(order_items)

        # payments
        split = rng.random() < 0.12 and total > 100_000
        if split:
            part = int(total * rng.uniform(0.3, 0.7) // 1000 * 1000)
            plan = [("momo", part), ("COD", total - part)]
        else:
            plan = [(rng.choices(["COD", "momo", "vnpay", "card"], weights=[45, 28, 17, 10])[0], total)]
        for method, amt in plan:
            if status == "cancelled":
                pst = "refunded" if method != "COD" else "pending"
                pts = (order_ts + timedelta(minutes=rng.randint(1, 30))) if method != "COD" else None
            elif status == "returned":
                pst, pts = "refunded", order_ts + timedelta(days=rng.randint(3, 9))
            elif status == "delivering":
                pst = "pending" if method == "COD" else "paid"
                pts = None if method == "COD" else order_ts + timedelta(minutes=rng.randint(1, 30))
            else:
                pst = "paid"
                pts = order_ts + (timedelta(days=rng.randint(1, 6)) if method == "COD" else timedelta(minutes=rng.randint(1, 30)))
            payments.append((pay_id, oid, method, amt, pts, pst))
            pay_id += 1

        # shipments (đơn bị hủy sớm thì không có)
        delivered_ts = None
        if status != "cancelled" or rng.random() < 0.25:
            shipped = order_ts + timedelta(hours=rng.randint(4, 48))
            if status == "completed":
                delivered_ts = shipped + timedelta(days=rng.randint(1, 6), hours=rng.randint(0, 20))
                sst = "delivered"
            elif status == "returned":
                delivered_ts = shipped + timedelta(days=rng.randint(1, 5))
                sst = "returned"
            elif status == "delivering":
                sst = "in_transit"
            else:
                sst = "failed"
            shipments.append((ship_id, oid, rng.choice(CARRIERS), shipped, delivered_ts, sst))
            ship_id += 1

        # reviews
        if status == "completed" and delivered_ts is not None:
            for (it_id, _, _, _, _) in order_items:
                if rng.random() < 0.35:
                    rating = rng.choices([1, 2, 3, 4, 5], weights=[5, 4, 9, 27, 55])[0]
                    reviews.append((rev_id, it_id, rating, delivered_ts + timedelta(days=rng.randint(1, 10))))
                    rev_id += 1

    return (
        pd.DataFrame(orders, columns=["order_id", "customer_id", "order_ts", "status", "voucher_id", "shipping_fee"]),
        pd.DataFrame(items, columns=["order_item_id", "order_id", "product_id", "quantity", "unit_price"]),
        pd.DataFrame(payments, columns=["payment_id", "order_id", "method", "amount", "paid_ts", "status"]),
        pd.DataFrame(shipments, columns=["shipment_id", "order_id", "carrier", "shipped_ts", "delivered_ts", "status"]),
        pd.DataFrame(reviews, columns=["review_id", "order_item_id", "rating", "created_at"]),
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--orders", type=int, default=40_000)
    ap.add_argument("--customers", type=int, default=6_000)
    ap.add_argument("--sellers", type=int, default=300)
    ap.add_argument("--products", type=int, default=3_000)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    nprng = np.random.default_rng(args.seed)

    categories, customers, sellers, products, vouchers = build_dimensions(
        rng, args.customers, args.sellers, args.products)
    orders, items, payments, shipments, reviews = generate_orders(
        rng, nprng, args.orders, customers, products, vouchers)

    DB_PATH.parent.mkdir(exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()
    con = duckdb.connect(str(DB_PATH))
    con.execute(SCHEMA_PATH.read_text(encoding="utf-8"))
    tables = {"categories": categories, "customers": customers, "sellers": sellers, "products": products,
              "vouchers": vouchers, "orders": orders, "order_items": items, "payments": payments,
              "shipments": shipments, "reviews": reviews}
    for name, df in tables.items():
        con.register("tmp_df", df)
        con.execute(f"INSERT INTO {name} SELECT * FROM tmp_df")
        con.unregister("tmp_df")
        print(f"{name:12s} {len(df):>8,} rows")
    con.close()
    print(f"\nĐã tạo {DB_PATH}")


if __name__ == "__main__":
    main()
