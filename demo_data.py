from datetime import timedelta

from models import Restaurant, Special, utc_now


DEMO_SPECIALS = [
    {
        "key": "adrift-salmon",
        "restaurant": "Adrift Restaurant",
        "title": "Cedar Plank Salmon Dinner",
        "description": "Sample post: local salmon with roasted market vegetables and herb butter.",
        "price": "$28",
        "photo_url": "https://images.unsplash.com/photo-1467003909585-2f8a72700288?auto=format&fit=crop&w=900&q=80",
    },
    {
        "key": "old-edison-burger",
        "restaurant": "The Old Edison",
        "title": "Smash Burger and Pint",
        "description": "Sample post: a double smash burger, seasoned fries, and a draft pint.",
        "price": "$18",
        "photo_url": "https://images.unsplash.com/photo-1568901346375-23c9450c58cd?auto=format&fit=crop&w=900&q=80",
    },
    {
        "key": "terramar-pizza",
        "restaurant": "Terramar Brewstillery",
        "title": "Wood-Fired Mushroom Pizza",
        "description": "Sample post: roasted mushrooms, mozzarella, herbs, and a crisp wood-fired crust.",
        "price": "$19",
        "photo_url": "https://images.unsplash.com/photo-1574071318508-1cdbab80d002?auto=format&fit=crop&w=900&q=80",
    },
    {
        "key": "dads-diner-bbq",
        "restaurant": "Dad's Diner Old School BBQ",
        "title": "Pitmaster Plate",
        "description": "Sample post: smoked brisket, pulled pork, slaw, and a rotating house side.",
        "price": "$24",
        "photo_url": "https://images.unsplash.com/photo-1529193591184-b1d58069ecdd?auto=format&fit=crop&w=900&q=80",
    },
    {
        "key": "chuckanut-oysters",
        "restaurant": "Chuckanut Manor Seafood & Grill",
        "title": "Local Oyster Happy Hour",
        "description": "Sample post: a half dozen local oysters with mignonette and lemon.",
        "price": "$16",
        "photo_url": "https://images.unsplash.com/photo-1498579397066-22750a3cb424?auto=format&fit=crop&w=900&q=80",
    },
    {
        "key": "farm-to-market-pastry",
        "restaurant": "Farm To Market Bakery",
        "title": "Fresh Pastry Box",
        "description": "Sample post: today's bakery selection packed as a shareable take-home box.",
        "price": "$15",
        "photo_url": "https://images.unsplash.com/photo-1509440159596-0249088772ff?auto=format&fit=crop&w=900&q=80",
    },
]


def seed_demo_specials(session):
    now = utc_now()
    seeded = 0
    skipped = []
    for item in DEMO_SPECIALS:
        restaurant = Restaurant.query.filter_by(name=item["restaurant"]).first()
        if not restaurant:
            skipped.append(item["restaurant"])
            continue
        marker = f'demo:{item["key"]}'
        special = Special.query.filter_by(source="demo", raw_text=marker).first()
        if not special:
            special = Special(restaurant_id=restaurant.id, source="demo", raw_text=marker)
            session.add(special)
        special.restaurant_id = restaurant.id
        special.title = item["title"]
        special.description = item["description"]
        special.price = item["price"]
        special.photo_url = item["photo_url"]
        special.status = "published"
        special.published_at = now
        special.expires_at = now + timedelta(days=14)
        seeded += 1
    session.commit()
    return seeded, skipped
