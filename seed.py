import csv
import json
from pathlib import Path

from app import app
from demo_data import seed_demo_specials
from models import Restaurant, db
from services import slugify


CSV_PATH = Path(__file__).with_name("skagit_restaurants_master.csv")

# Keep this explicit so reviewing additions and removals is straightforward.
CHAIN_NAMES = {
    "a&w restaurant",
    "applebee's grill + bar",
    "arby's",
    "bigfoot java",
    "bob's burgers & brew burlington",
    "burger king",
    "burgermaster",
    "carl's jr.",
    "chipotle mexican grill",
    "coconut kenny's pizza - anacortes",
    "coconut kenny's pizza - burlington",
    "coconut kenny's pizza - sedro-woolley",
    "denny's restaurant",
    "diedrich espresso anacortes",
    "diedrich espresso burlington blvd",
    "diedrich espresso burlington on 99",
    "diedrich espresso sedro woolley cook rd",
    "diedrich espresso sedro woolley moore st",
    "diedrich espresso sedro woolley on hwy 20",
    "domino's pizza",
    "fred meyer",
    "haggen",
    "hot stuff pizza",
    "ihop",
    "jack in the box",
    "jersey mike's subs",
    "jimmy john's",
    "krispy krunchy chicken",
    "little caesars pizza",
    "mcdonald's",
    "mod pizza",
    "mountain mike's pizza",
    "olive garden italian restaurant",
    "panda express",
    "panera bread",
    "papa murphy's | take 'n' bake pizza",
    "pizza factory",
    "pizza hut",
    "pizza hut express",
    "popeyes louisiana kitchen",
    "red robin gourmet burgers and brews",
    "round table pizza",
    "safeway",
    "safeway bakery",
    "safeway deli",
    "starbucks",
    "starbucks coffee company",
    "subway",
    "taco bell",
    "taco time",
    "teriyaki time",
    "the burger den",
    "walmart bakery",
    "walmart deli",
    "walmart supercenter",
    "wendy's",
    "whidbey coffee",
    "wingstop",
    "woods coffee",
}


def optional_float(value):
    return float(value) if value else None


def optional_int(value):
    return int(float(value)) if value else None


def optional_json(value):
    return json.loads(value) if value else None


def unique_slug(row, used_slugs):
    candidates = [
        row["name"],
        f'{row["name"]}-{row["city"]}',
        f'{row["name"]}-{row["city"]}-{row["postal_code"]}',
        f'{row["name"]}-{row["place_id"]}',
    ]
    for candidate in candidates:
        slug = slugify(candidate)
        if slug not in used_slugs:
            used_slugs.add(slug)
            return slug
    raise ValueError(f'Could not create a unique slug for {row["name"]}')


def restaurant_from_row(row, used_slugs):
    return Restaurant(
        name=row["name"],
        slug=unique_slug(row, used_slugs),
        full_address=row["full_address"],
        street=row["street"],
        city=row["city"],
        postal_code=row["postal_code"],
        us_state=row["us_state"],
        country=row["country"],
        latitude=optional_float(row["latitude"]),
        longitude=optional_float(row["longitude"]),
        site=row["site"],
        phone=row["phone"],
        type=row["type"],
        category=row["category"],
        subtypes=row["subtypes"],
        rating=optional_float(row["rating"]),
        reviews=optional_int(row["reviews"]),
        business_status=row["business_status"],
        working_hours=optional_json(row["working_hours"]),
        google_id=row["google_id"],
        place_id=row["place_id"],
        reviews_link=row["reviews_link"],
        photo=row["photo"],
        source_query=row["query"],
        scraped_zip=row["scraped_zip"],
        source=row["source"],
    )


def seed_database(reset=False):
    if reset:
        db.drop_all()
        db.create_all()

    imported = 0
    excluded_chains = []
    if Restaurant.query.count() == 0:
        used_slugs = set()
        with CSV_PATH.open(newline="", encoding="utf-8-sig") as csv_file:
            for row in csv.DictReader(csv_file):
                if row["name"].strip().casefold() in CHAIN_NAMES:
                    excluded_chains.append(row["name"])
                    continue
                db.session.add(restaurant_from_row(row, used_slugs))
                imported += 1
        db.session.commit()

    demos_seeded, demos_skipped = seed_demo_specials(db.session)
    return {
        "restaurants": imported or Restaurant.query.count(),
        "excluded_chains": len(excluded_chains),
        "demo_specials": demos_seeded,
        "demo_skipped": demos_skipped,
    }


if __name__ == "__main__":
    with app.app_context():
        result = seed_database(reset=True)
        print(f"Seeded {result['restaurants']} independent restaurants.")
        print(f"Excluded {result['excluded_chains']} chain locations.")
        print(f"Seeded {result['demo_specials']} launch-preview specials.")
        if result["demo_skipped"]:
            print(f"Skipped {len(result['demo_skipped'])} demo restaurants: {', '.join(result['demo_skipped'])}")
