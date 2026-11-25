"""On-demand, API-free reads of public Google Maps review cards."""
import os
import re
import subprocess
import threading
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

from belive.connectors import google_review_share_link
from belive.store import digest

BATCH_LIMIT = 10
CARD = '.jftiEf[data-review-id]'
REVIEW_PANE = '.m6QErb.DxyBCb.kA9KIf.dS8AEf:visible'
STARS = re.compile(r'^[1-5] stars?\s*$')
_import_lock = threading.Lock()
_google_assets = {'www.google.com', 'google.com', 'maps.google.com', 'maps.app.goo.gl',
                  'maps.googleapis.com', 'maps.gstatic.com', 'www.gstatic.com',
                  'fonts.gstatic.com', 'fonts.googleapis.com', 'lh3.googleusercontent.com',
                  'ssl.gstatic.com', 'streetviewpixels-pa.googleapis.com'}


def review_identity(url):
    if not url:
        return None
    try:
        parsed = urlsplit(google_review_share_link(url))
    except ValueError:
        return None
    # Maps adds the viewport and tracking query to the same contributor/place link.
    match = re.match(r'^/maps/contrib/([0-9]+)/place/([A-Za-z0-9_-]+)(?:/|$)', parsed.path)
    return match.groups() if match else (parsed.netloc.lower(), parsed.path.rstrip('/'))


def google_listing_link(value):
    message = 'Copy the full Google Maps listing URL from the Chrome address bar.'
    if not isinstance(value, str) or len(value) > 2000 or re.search(r'\s', value):
        raise ValueError(message)
    parsed = urlsplit(value)
    if (parsed.scheme != 'https' or parsed.netloc.lower() not in {'www.google.com', 'google.com', 'maps.google.com'}
            or not re.match(r'^/maps/place/[^/]+', parsed.path)):
        raise ValueError(message)
    return value


def _allow_google_request(route):
    request = route.request
    target = urlsplit(request.url)
    if target.scheme != 'https' or target.netloc.lower() not in _google_assets:
        route.abort()
    else:
        route.continue_()


def review_chrome_profile():
    local_data = os.environ.get('LOCALAPPDATA')
    if not local_data:
        return None
    return Path(local_data) / 'BeLive' / 'ReviewChrome'


def open_review_chrome_sign_in():
    profile = review_chrome_profile()
    if profile is None:
        raise ValueError('Collector sign-in setup is available on Windows with Chrome installed.')
    roots = (os.environ.get(key) for key in ('ProgramFiles', 'ProgramFiles(x86)', 'LOCALAPPDATA'))
    chrome = next((candidate for root in roots if root
                   if (candidate := Path(root)/'Google'/'Chrome'/'Application'/'chrome.exe').is_file()), None)
    if chrome is None:
        raise ValueError('Google Chrome is required for collector sign-in.')
    if not _import_lock.acquire(blocking=False):
        raise ValueError('Wait for the current review import before opening collector sign-in.')
    try:
        profile.mkdir(parents=True, exist_ok=True)
        subprocess.Popen([str(chrome), f'--user-data-dir={profile}', '--new-window', '--no-first-run',
                          'https://accounts.google.com/'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        raise ValueError('BeLive could not open its Chrome sign-in window.') from None
    finally:
        _import_lock.release()


@contextmanager
def _google_page(*, headless, profile=None):
    try:
        from playwright.sync_api import Error as PlaywrightError, sync_playwright
    except ImportError:
        raise ValueError('Browser import needs Playwright. Run python -m pip install -r requirements-dev.txt in BeLive.') from None
    if not _import_lock.acquire(blocking=False):
        raise ValueError('A Google Maps import is already running. Wait for it to finish.')

    try:
        with sync_playwright() as playwright:
            if profile is not None:
                try:
                    context = playwright.chromium.launch_persistent_context(
                        profile, channel='chrome', headless=headless, timeout=9000, locale='en-MY',
                        accept_downloads=False, service_workers='block',
                    )
                except PlaywrightError:
                    raise ValueError('Close the separate BeLive Chrome window completely before collecting reviews.') from None
                try:
                    context.route('**/*', _allow_google_request)
                    yield context.new_page()
                finally:
                    context.close()
                return
            try:
                browser = playwright.chromium.launch(channel='chrome', headless=headless, timeout=9000)
            except PlaywrightError:
                raise ValueError('Browser import could not start Google Chrome. Check that Chrome is installed.') from None
            with browser:
                context = browser.new_context(locale='en-MY', accept_downloads=False, service_workers='block')
                context.route('**/*', _allow_google_request)
                yield context.new_page()
    except PlaywrightError:
        raise ValueError('Chrome did not display the requested public Google Maps review content.') from None
    finally:
        _import_lock.release()


def _review_card(card, max_rating=5):
    review_id = card.get_attribute('data-review-id', timeout=3500)
    labels = card.locator('[aria-label]:visible').evaluate_all(
        'nodes => nodes.map(node => node.getAttribute("aria-label"))'
    )
    label = next((value for value in labels if STARS.fullmatch(value)), '')
    words = card.locator('.wiI7pd:visible')
    if not review_id or not label or int(label[0]) > max_rating or not words.count():
        return None
    more = card.locator('button[jsaction*=".review.expandReview"]:visible')
    if more.count() == 1:
        more.click(timeout=3500)
    text = words.first.inner_text(timeout=3500).strip()
    if len(text) < 10:
        return None
    return {'source_id': 'google-browser-'+digest(review_id), 'rating': int(label[0]), 'description': text[:6000]}


def _open_review(page, url, *, max_rating=5):
    response = page.goto(url, wait_until='domcontentloaded', timeout=12000)
    if not response or not response.ok:
        raise ValueError('Google Maps did not open that review. Try its individual Share link.')
    cards = page.locator(CARD + ':visible')
    if not review_identity(page.url):
        if page.get_by_role('tab', name=re.compile(r'^Reviews for ')).count():
            raise ValueError('This link opens a listing. Use the listing collection button or Share on one review.')
        if urlsplit(url).netloc.lower() != 'maps.app.goo.gl':
            raise ValueError('Google Maps did not show an individual review for that link.')
    cards.first.wait_for(state='visible', timeout=9000)
    if cards.count() != 1:
        raise ValueError('This link opens more than one review. Use Share on the review you want.')
    review = _review_card(cards.first, max_rating)
    if review:
        review['review_url'] = page.url if review_identity(page.url) else url
    return review


def read_browser_review(value):
    """Read the review a signed-out browser shows for one individual link."""
    try:
        url = google_review_share_link(value)
    except ValueError:
        raise ValueError('Use the individual Google Maps review link from Share on that review.') from None
    with _google_page(headless=True) as page:
        review = _open_review(page, url)
    if not review:
        raise ValueError('Google Maps did not show enough written review text to import.')
    return review


def _scroll_review_list(page):
    from playwright.sync_api import TimeoutError as PlaywrightTimeout

    pane = page.locator(REVIEW_PANE).last
    try:
        pane.hover(timeout=1500)
    except PlaywrightTimeout:
        return False
    page.mouse.wheel(0, 650)
    return True


def _review_ids(cards):
    return cards.evaluate_all('nodes => nodes.map(node => node.dataset.reviewId)')


def _collect_listing(page, url):
    from playwright.sync_api import TimeoutError as PlaywrightTimeout

    response = page.goto(url, wait_until='domcontentloaded', timeout=14000)
    if not response or not response.ok:
        raise ValueError('Chrome could not open the Google Maps listing.')
    google_listing_link(page.url)
    tab = page.get_by_role('tab', name=re.compile(r'^Reviews(?: for .+)?$', re.I))
    tab.wait_for(timeout=9000)
    if tab.get_attribute('aria-selected') != 'true':
        tab.click(timeout=4500)

    filter_stalled = False
    try:
        page.get_by_role('button', name='Sort reviews', exact=True).click(timeout=3000)
        page.get_by_role('menuitemradio', name='Lowest rating', exact=True).click(timeout=2500)
    except PlaywrightTimeout:
        filter_stalled = True
        page.keyboard.press('Escape')

    cards = page.locator(CARD + ':visible')
    low_cards = cards.filter(has=page.locator('[aria-label="1 star"], [aria-label="2 stars"]'))
    reviews = {}
    examined = set()
    empty_scrolls = 0
    for attempt in range(11):
        for card in low_cards.all():
            try:
                visible_id = card.get_attribute('data-review-id', timeout=1000)
                if visible_id in examined:
                    continue
                review = _review_card(card, max_rating=2)
            except PlaywrightTimeout:
                continue  # Maps can replace review rows during scrolling.
            examined.add(visible_id)
            if review:
                review['listing_url'] = url
                reviews[review['source_id']] = review
            if len(reviews) >= BATCH_LIMIT:
                return list(reviews.values())

        if attempt == 10:
            break
        previous_ids = _review_ids(cards)
        if not _scroll_review_list(page):
            break
        # The Maps spinner can stay open until the review panel is scrolled.
        # Compare IDs because Maps can recycle rows without growing the list.
        try:
            page.wait_for_function(
                """({selector, previous}) => Array.from(document.querySelectorAll(selector))
                    .some(card => card.getClientRects().length && !previous.includes(card.dataset.reviewId))""",
                arg={'selector': CARD, 'previous': previous_ids}, timeout=1800,
            )
        except PlaywrightTimeout:
            empty_scrolls += 1
            if empty_scrolls == 2:
                break
        else:
            empty_scrolls = 0

    if not reviews and filter_stalled:
        raise ValueError('Google Maps did not show readable low-rated reviews after scrolling. Try individual Share links.')
    return list(reviews.values())


def read_browser_review_batch(value):
    """Read up to ten 1–2 star written reviews from one listing or individual links."""
    if not isinstance(value, str) or len(value) > BATCH_LIMIT * 2001:
        raise ValueError('Enter a Google Maps listing URL or up to 10 individual Google review links.')
    links = list(dict.fromkeys(line.strip() for line in value.splitlines() if line.strip()))
    if not 1 <= len(links) <= BATCH_LIMIT:
        raise ValueError('Enter a Google Maps listing URL or up to 10 individual Google review links.')
    try:
        listing = google_listing_link(links[0]) if len(links) == 1 else None
    except ValueError:
        listing = None

    if listing:
        profile = review_chrome_profile()
        with _google_page(headless=True, profile=profile if profile and profile.is_dir() else None) as page:
            return _collect_listing(page, listing), 0

    links = [google_review_share_link(link) for link in links]
    reviews = {}
    skipped = 0
    with _google_page(headless=True) as page:
        from playwright.sync_api import Error as PlaywrightError
        for link in links:
            try:
                review = _open_review(page, link, max_rating=2)
            except (ValueError, PlaywrightError):
                review = None
            if not review or review['source_id'] in reviews:
                skipped += 1
                continue
            reviews[review['source_id']] = review
    return list(reviews.values()), skipped
