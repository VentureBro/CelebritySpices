import os
import subprocess
import sys
import time


POLL_SECONDS = int(
    os.environ.get(
        "BLOCKCHAIN_POLL_SECONDS",
        "10",
    )
)


def main():
    print(
        "Blockchain audit worker started."
    )
    print(
        "Polling every",
        POLL_SECONDS,
        "seconds."
    )

    while True:
        result = subprocess.run(
            [
                sys.executable,
                "process_next.py",
            ],
            check=False,
        )

        if result.returncode != 0:
            print(
                "Audit cycle failed. "
                "Will retry after delay."
            )

        time.sleep(
            POLL_SECONDS
        )


if __name__ == "__main__":
    main()
