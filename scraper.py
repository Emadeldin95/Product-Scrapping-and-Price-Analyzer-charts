import asyncio
import time
from urllib.parse import urlencode
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError, Error as PlaywrightError
import pandas as pd

class Scraper:
    def __init__(self, url, keywords=None):
        self.url = url
        self.keywords = keywords
        self.data = []
        self.running = True
        self.max_retries = 3  # Number of retries for network errors

    async def start_scraping(self, update_callback):
        for attempt in range(self.max_retries):
            try:
                async with async_playwright() as p:
                    browser = await p.chromium.launch(headless=False, slow_mo=500)  # Debugging mode

                    # ✅ Use browser context to set user-agent
                    context = await browser.new_context(
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                    )
                    page = await context.new_page()

                    is_noon = "noon.com" in self.url

                    # ✅ Skip Noon Search Bar - Use URL Instead
                    if is_noon and self.keywords:
                        search_params = urlencode({"q": self.keywords})
                        self.url = f"{self.url.rstrip('/')}/search?{search_params}"

                    try:
                        print(f"🔄 Navigating to {self.url}")
                        await page.goto(self.url, wait_until="domcontentloaded", timeout=60000)  # Increased timeout
                        print("✅ Page loaded successfully!")

                    except PlaywrightTimeoutError:
                        print(f"⚠ Failed to load {self.url}, retrying...")
                        await browser.close()
                        continue

                    # ✅ Scroll Down to Trigger Lazy Loading
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await asyncio.sleep(3)  # Allow time for JavaScript to render products

                    # **Dynamic Product Selectors**
                    product_selectors = {
                        "default": [
                            '.product-wrapper',  # General product container
                            'li.entry.has-media',
                            '.product'
                        ],
                        "noon": 'div.ProductBoxVertical_rocketBadgeBevel__lM0Ee'
                    }

                    next_page_selectors = {
                        "default": 'a.next.page-numbers',
                        "noon": 'a.PlpPagination_arrowLink__QSqKF[aria-disabled="false"]'
                    }

                    product_selector = product_selectors["noon"] if is_noon else product_selectors["default"]
                    next_page_selector = next_page_selectors["noon"] if is_noon else next_page_selectors["default"]

                    while self.running:
                        if is_noon:
                            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                            await asyncio.sleep(2)

                        product_container = []
                        if isinstance(product_selector, list):
                            for selector in product_selector:
                                product_container = await page.query_selector_all(selector)
                                if product_container:
                                    break
                        else:
                            product_container = await page.query_selector_all(product_selector)

                        if not product_container:
                            print("⚠ No products found. Check selectors!")
                            break

                        print(f"✅ Found {len(product_container)} products!")

                        for product in product_container:
                            if not self.running:
                                break

                            name_element = await product.query_selector('[data-qa="product-name"]') or \
                                           await product.query_selector('h3.heading-title.product-name a') or \
                                           await product.query_selector('h2 a') or \
                                           await product.query_selector('h3')
                            name = await name_element.inner_text() if name_element else "N/A"

                            price_element = await product.query_selector('strong.Price_amount__2sXa7') or \
                                            await product.query_selector('.price bdi') or \
                                            await product.query_selector('.woocommerce-Price-amount.amount')
                            price = await price_element.inner_text() if price_element else "N/A"

                            link_element = await product.query_selector('a')
                            link = await link_element.get_attribute("href") if link_element else "N/A"
                            if is_noon and link.startswith("/"):
                                link = f"https://www.noon.com{link}"

                            image_element = await product.query_selector('img')
                            image = await image_element.get_attribute("src") if image_element else "N/A"

                            self.data.append({
                                "Name": name,
                                "Price": price,
                                "Link": link,
                                "Image": image
                            })
                            update_callback(self.data)

                        next_page_button = await page.query_selector(next_page_selector)
                        if next_page_button:
                            print("🔄 Moving to the next page...")
                            await next_page_button.click()
                            await page.wait_for_load_state("networkidle")
                        else:
                            break

                    await browser.close()
                    break

            except (PlaywrightTimeoutError, PlaywrightError) as e:
                print(f"⚠ Playwright error encountered (Attempt {attempt + 1}/{self.max_retries}): {e}")
                time.sleep(3)

            except Exception as e:
                print(f"⚠ Unexpected error (Attempt {attempt + 1}/{self.max_retries}): {e}")
                time.sleep(3)

        print("✅ Scraping completed!")

    def stop(self):
        self.running = False

    def get_data(self):
        return pd.DataFrame(self.data)
