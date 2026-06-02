import csv
import os


os.environ["DATABASE_URL"] = "sqlite://"

from app import app
from models import Restaurant, Special, db
from seed import seed_database


def test_launch_seed_populates_empty_database_without_resetting_existing_data(tmp_path, monkeypatch):
    csv_path = tmp_path / "restaurants.csv"
    fieldnames = [
        "name",
        "full_address",
        "street",
        "city",
        "postal_code",
        "us_state",
        "country",
        "latitude",
        "longitude",
        "site",
        "phone",
        "type",
        "category",
        "subtypes",
        "rating",
        "reviews",
        "business_status",
        "working_hours",
        "google_id",
        "place_id",
        "reviews_link",
        "photo",
        "query",
        "scraped_zip",
        "source",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(
            {
                **{field: "" for field in fieldnames},
                "name": "Launch Cafe",
                "city": "Mount Vernon",
                "place_id": "launch-cafe",
            }
        )

    monkeypatch.setattr("seed.CSV_PATH", csv_path)
    monkeypatch.setattr("seed.seed_demo_specials", lambda session: (0, []))

    with app.app_context():
        db.drop_all()
        db.create_all()
        first = seed_database(reset=False)
        db.session.add(Special(restaurant_id=1, title="Keep me", source="manual"))
        db.session.commit()
        second = seed_database(reset=False)

        assert first["restaurants"] == second["restaurants"] == 1
        assert Restaurant.query.one().name == "Launch Cafe"
        assert Special.query.one().title == "Keep me"

        db.session.remove()
        db.drop_all()
