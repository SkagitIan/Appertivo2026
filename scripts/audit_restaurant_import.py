import argparse
import csv
import json
import sqlite3
from collections import Counter
from pathlib import Path


def normalize(value):
    return " ".join((value or "").strip().casefold().split())


def load_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as csv_file:
        return list(csv.DictReader(csv_file))


def load_database(path):
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        columns = [
            row["name"]
            for row in connection.execute("pragma table_info(restaurant)").fetchall()
        ]
        rows = [
            dict(row)
            for row in connection.execute(
                f"select {', '.join(columns)} from restaurant"
            ).fetchall()
        ]
    finally:
        connection.close()
    return columns, rows


def populated_columns(rows):
    return {
        column: sum(bool((row.get(column) or "").strip()) for row in rows)
        for column in rows[0]
    }


def key_duplicates(rows, column):
    values = [normalize(row.get(column)) for row in rows]
    return {
        value: count
        for value, count in Counter(value for value in values if value).items()
        if count > 1
    }


def match_rows(csv_rows, database_rows):
    database_by_place_id = {
        normalize(row.get("place_id")): row
        for row in database_rows
        if normalize(row.get("place_id"))
    }
    database_by_google_id = {
        normalize(row.get("google_id")): row
        for row in database_rows
        if normalize(row.get("google_id"))
    }
    database_by_name_address = {
        (normalize(row.get("name")), normalize(row.get("full_address"))): row
        for row in database_rows
        if normalize(row.get("name")) and normalize(row.get("full_address"))
    }

    matches = []
    unmatched = []
    for row in csv_rows:
        match = None
        match_type = None
        for match_type, key, index in [
            ("place_id", normalize(row.get("place_id")), database_by_place_id),
            ("google_id", normalize(row.get("google_id")), database_by_google_id),
            (
                "name_full_address",
                (normalize(row.get("name")), normalize(row.get("full_address"))),
                database_by_name_address,
            ),
        ]:
            if key and key in index:
                match = index[key]
                break
        if match:
            matches.append((match_type, row, match))
        else:
            unmatched.append(row)
    return matches, unmatched


def changed_fields(matches, comparable_columns):
    changed = Counter()
    for _, csv_row, database_row in matches:
        for column in comparable_columns:
            left = csv_row.get(column)
            right = database_row.get(column)
            if normalize(str(left or "")) != normalize(str(right or "")):
                changed[column] += 1
    return dict(changed.most_common())


def summarize(csv_path, database_path):
    csv_rows = load_csv(csv_path)
    database_columns, database_rows = load_database(database_path)
    csv_columns = list(csv_rows[0]) if csv_rows else []
    database_column_set = set(database_columns)
    csv_column_set = set(csv_columns)
    comparable_columns = sorted(csv_column_set & database_column_set)
    matches, unmatched_csv = match_rows(csv_rows, database_rows)
    matched_database_ids = {database_row["id"] for _, _, database_row in matches}
    unmatched_database = [
        row for row in database_rows if row["id"] not in matched_database_ids
    ]

    return {
        "csv_path": str(csv_path),
        "database_path": str(database_path),
        "csv_rows": len(csv_rows),
        "database_rows": len(database_rows),
        "csv_columns": csv_columns,
        "database_columns": database_columns,
        "csv_columns_missing_from_model": sorted(csv_column_set - database_column_set),
        "model_columns_missing_from_csv": sorted(database_column_set - csv_column_set),
        "csv_populated_columns": populated_columns(csv_rows) if csv_rows else {},
        "csv_duplicate_place_ids": key_duplicates(csv_rows, "place_id"),
        "csv_duplicate_google_ids": key_duplicates(csv_rows, "google_id"),
        "database_duplicate_google_ids": key_duplicates(database_rows, "google_id"),
        "match_types": dict(Counter(match_type for match_type, _, _ in matches)),
        "matched_csv_rows": len(matches),
        "new_csv_rows": len(unmatched_csv),
        "database_rows_absent_from_csv": len(unmatched_database),
        "changed_fields_for_matches": changed_fields(matches, comparable_columns),
        "new_csv_restaurants": [
            {
                "name": row.get("name"),
                "address": row.get("address") or row.get("full_address"),
                "place_id": row.get("place_id"),
                "primary_type": row.get("primary_type"),
                "scraped_zip": row.get("scraped_zip"),
            }
            for row in unmatched_csv
        ],
        "database_restaurants_absent_from_csv": [
            {
                "id": row.get("id"),
                "name": row.get("name"),
                "full_address": row.get("full_address"),
                "place_id": row.get("place_id"),
                "source_query": row.get("query"),
                "scraped_zip": row.get("scraped_zip"),
            }
            for row in unmatched_database
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path", type=Path)
    parser.add_argument(
        "--database",
        type=Path,
        default=Path(__file__).parents[1] / "instance" / "appertivo.db",
    )
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args()
    report = summarize(args.csv_path, args.database)
    if args.summary:
        report.pop("new_csv_restaurants")
        report.pop("database_restaurants_absent_from_csv")
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
