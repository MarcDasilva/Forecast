from __future__ import annotations

import argparse
import re
from pathlib import Path

from playwright.sync_api import Playwright, TimeoutError as PlaywrightTimeoutError, sync_playwright


DEFAULT_URL = "https://www.er-watch.ca/"
WAIT_TIME_PATTERN = re.compile(r"^\d+h \d+m$|^\d+ min$|^-$|^\u2014$|^-1h -1m$")


def extract_hospital_wait_time(page, hospital_name: str) -> str:
    card = page.locator("article").filter(
        has=page.get_by_role("heading", name=hospital_name, exact=True)
    )

    if card.count() == 0:
        raise ValueError(f"Hospital card not found for '{hospital_name}'.")

    paragraphs = card.first.locator("p").all_inner_texts()
    for paragraph in paragraphs:
        value = paragraph.strip()
        if WAIT_TIME_PATTERN.match(value):
            return value

    raise ValueError(f"Wait time not found for '{hospital_name}'.")


def search_location(page, location: str) -> None:
    search_box = page.get_by_role("textbox", name="Search by city or address...")
    search_box.click()
    search_box.fill(location)
    page.get_by_role("button", name=re.compile(rf"^{re.escape(location)}")).first.click()


def run(
    playwright: Playwright,
    *,
    location: str,
    hospitals: list[str],
    url: str,
    video_dir: Path,
    headless: bool,
) -> tuple[dict[str, str], str]:
    video_dir.mkdir(parents=True, exist_ok=True)

    browser = playwright.chromium.launch(headless=headless)
    context = browser.new_context(
        record_video_dir=str(video_dir),
        record_video_size={"width": 1280, "height": 720},
        viewport={"width": 1280, "height": 720},
    )
    page = context.new_page()

    try:
        page.goto(url, wait_until="domcontentloaded")
        search_location(page, location)

        results: dict[str, str] = {}
        for hospital in hospitals:
            heading = page.get_by_role("heading", name=hospital, exact=True).first
            heading.wait_for(state="visible", timeout=15_000)
            results[hospital] = extract_hospital_wait_time(page, hospital)

        page.wait_for_timeout(1_000)
        context.close()
        video_path = page.video.path()
        browser.close()
        return results, video_path
    except PlaywrightTimeoutError as exc:
        context.close()
        browser.close()
        raise RuntimeError("Timed out while interacting with the page.") from exc
    except Exception:
        context.close()
        browser.close()
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape ER wait times for one or more hospitals and record the session."
    )
    parser.add_argument(
        "--location",
        default="Waterloo",
        help="Location to enter in the ER Watch search box.",
    )
    parser.add_argument(
        "--hospital",
        action="append",
        required=True,
        dest="hospitals",
        help="Hospital heading text to scrape. Pass this flag multiple times.",
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_URL,
        help="Page URL to open.",
    )
    parser.add_argument(
        "--video-dir",
        default="web_scraping/videos",
        help="Directory where Playwright should save recorded video.",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Show the browser window instead of running headless.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    with sync_playwright() as playwright:
        results, video_path = run(
            playwright,
            location=args.location,
            hospitals=args.hospitals,
            url=args.url,
            video_dir=Path(args.video_dir),
            headless=not args.headed,
        )

    for hospital, wait_time in results.items():
        print(f"{hospital}: {wait_time}")
    print(f"Video saved to: {video_path}")


if __name__ == "__main__":
    main()
