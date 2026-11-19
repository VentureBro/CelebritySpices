import os
import subprocess
import sys

import psycopg


START_MOVEMENT_ID = int(
    os.environ.get(
        "BLOCKCHAIN_START_MOVEMENT_ID",
        "31",
    )
)


def get_next_pending():
    with psycopg.connect(
        host="127.0.0.1",
        port=5432,
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
    ) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    id,
                    movement_type,
                    quantity_before,
                    quantity_after
                FROM inventory_movements
                WHERE id >= %s
                  AND blockchain_signature IS NULL
                ORDER BY id ASC
                LIMIT 1
                """,
                (START_MOVEMENT_ID,),
            )

            return cur.fetchone()


def main():
    row = get_next_pending()

    if row is None:
        print(
            "No pending blockchain audits "
            f"at or above movement "
            f"{START_MOVEMENT_ID}."
        )
        return

    movement_id = row[0]

    print(
        "===== NEXT BLOCKCHAIN AUDIT ====="
    )
    print("Movement:", movement_id)
    print("Type:", row[1])
    print(
        "Quantity:",
        f"{row[2]} -> {row[3]}",
    )

    result = subprocess.run(
        [
            sys.executable,
            "send_movement.py",
            str(movement_id),
        ],
        check=False,
    )

    if result.returncode != 0:
        raise SystemExit(
            result.returncode
        )


if __name__ == "__main__":
    main()
