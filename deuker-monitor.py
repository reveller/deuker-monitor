#!/usr/bin/env python3
"""
Miami-Dade Clerk of Court Docket Monitor
Monitors defendant search results for new docket entries across all cases

Author: Created for monitoring Miami-Dade court cases
Python Version: 3.11.9
"""

import requests
from bs4 import BeautifulSoup
import time
import json
import re
from datetime import datetime
from pathlib import Path
from typing import List, Set, Dict, Optional
import hashlib
import logging
import argparse
from dataclasses import dataclass, asdict
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright, Browser, Page, Playwright


@dataclass
class Charge:
    """Represents a single charge"""
    case_number: str
    sequence_number: str
    charge_description: str
    charge_type: str
    disposition: str
    timestamp_found: str


@dataclass
class DocketEntry:
    """Represents a single docket entry"""
    case_number: str
    din: str
    date: str
    docket_description: str
    book_page: str
    timestamp_found: str
    has_document: bool = False
    document_downloaded: bool = False
    document_filename: str = ""


@dataclass
class CaseInfo:
    """Represents a case with its docket entries and charges"""
    case_number: str
    filed_date: str
    closed_date: str
    first_charge: str
    balance_due: str
    charge_count: int
    docket_count: int
    last_checked: str


@dataclass
class IceDetaineeStatus:
    """Represents ICE detainee locator status"""
    full_name: str
    country_of_birth: str
    status: str              # e.g., "In ICE Custody"
    state: str               # e.g., "CA"
    detention_facility: str  # e.g., "CALIFORNIA CITY CORRECTIONS CENTER"
    last_checked: str
    first_seen: str


class MiamiDadeCourtMonitor:
    """Monitor Miami-Dade court cases for docket updates"""
    
    BASE_URL = "https://www2.miamidadeclerk.gov"
    SEARCH_URL = "https://www2.miamidadeclerk.gov/cjis/"

    def __init__(self,
                 defendant_first_name: str,
                 defendant_last_name: str,
                 defendant_sex: str = "Male",
                 poll_interval: int = 300,
                 data_file: str = "docket_monitor_data.json",
                 headless: bool = True,
                 skip_state: bool = False,
                 notification_sms: str = "",
                 notification_email: str = "",
                 download_documents: bool = True,
                 documents_dir: str = "court_documents",
                 filter_case_number: str = "",
                 enable_screenshots: bool = False,
                 smtp_server: str = "",
                 smtp_port: int = 587,
                 smtp_username: str = "",
                 smtp_password: str = "",
                 smtp_from_address: str = "",
                 twilio_account_sid: str = "",
                 twilio_auth_token: str = "",
                 twilio_phone_number: str = "",
                 ice_monitoring: bool = False,
                 country_of_birth: str = "",
                 dob_month: str = "",
                 dob_day: str = "",
                 dob_year: str = ""):
        """
        Initialize the monitor

        Args:
            defendant_first_name: Defendant's first name
            defendant_last_name: Defendant's last name
            defendant_sex: Defendant's sex (Male/Female)
            poll_interval: Seconds between checks (default: 300 = 5 minutes)
            data_file: File to store tracking data
            headless: Run browser in headless mode (default: True)
            skip_state: Skip loading/saving state (--all mode)
            notification_sms: Phone number for SMS notifications (E.164 format, e.g., +12345678900)
            notification_email: Email address for email notifications
            download_documents: Automatically download court documents (default: True)
            documents_dir: Directory to store downloaded documents (default: court_documents)
            filter_case_number: Monitor only this specific case number (e.g., F-25-024652 or F25024652)
            enable_screenshots: Enable debug screenshots (default: False)
            smtp_server: SMTP server for email (e.g., smtp.gmail.com)
            smtp_port: SMTP port (default: 587)
            smtp_username: SMTP username
            smtp_password: SMTP password
            smtp_from_address: SMTP from address (defaults to smtp_username)
            twilio_account_sid: Twilio Account SID for SMS
            twilio_auth_token: Twilio Auth Token for SMS
            twilio_phone_number: Twilio phone number for SMS
        """
        self.defendant_first_name = defendant_first_name
        self.defendant_last_name = defendant_last_name
        self.defendant_sex = defendant_sex
        self.poll_interval = poll_interval
        self.data_file = Path(data_file)
        self.seen_charges: Set[str] = set()
        self.seen_dockets: Set[str] = set()
        self.seen_documents: Set[str] = set()  # Track downloaded documents
        self.case_info: Dict[str, CaseInfo] = {}
        self.headless = headless
        self.skip_state = skip_state
        self.notification_sms = notification_sms
        self.notification_email = notification_email
        self.download_documents = download_documents
        self.documents_dir = Path(documents_dir)
        self.enable_screenshots = enable_screenshots
        self.screenshots_dir = Path("screenshots")
        self.screenshot_counter = 0

        # SMTP configuration
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.smtp_username = smtp_username
        self.smtp_password = smtp_password
        self.smtp_from_address = smtp_from_address or smtp_username

        # Twilio configuration
        self.twilio_account_sid = twilio_account_sid
        self.twilio_auth_token = twilio_auth_token
        self.twilio_phone_number = twilio_phone_number

        # ICE detainee locator configuration
        self.ice_monitoring = ice_monitoring
        self.country_of_birth = country_of_birth
        self.dob_month = dob_month
        self.dob_day = dob_day
        self.dob_year = dob_year
        self.ice_status: Optional[IceDetaineeStatus] = None
        self.ice_check_failures: int = 0

        # Create screenshots directory if screenshots are enabled
        if self.enable_screenshots:
            self.screenshots_dir.mkdir(exist_ok=True)

        # Set up logging first (needed by _normalize_case_number)
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('docket_monitor.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)

        self.filter_case_number = self._normalize_case_number(filter_case_number) if filter_case_number else ""
        # #region agent log
        with open('/home/sfeltner/Projects/deuker-monitor/.cursor/debug.log', 'a') as f:
            import json as json_module
            f.write(json_module.dumps({'sessionId':'debug-session','runId':'post-fix','hypothesisId':'E','location':'deuker-monitor.py:127','message':'Filter case number initialized in __init__','data':{'original':filter_case_number,'normalized':self.filter_case_number},'timestamp':int(time.time()*1000)})+'\n')
        # #endregion
        print(f"🔍 DEBUG: __init__ - filter_case_number param = '{filter_case_number}', normalized = '{self.filter_case_number}'")

        # Create documents directory if download is enabled
        if self.download_documents:
            self.documents_dir.mkdir(exist_ok=True)

        # Playwright objects - will be initialized in _init_browser()
        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None

        # Load previous state
        self._load_state()

    def _normalize_case_number(self, case_number: str) -> str:
        """
        Normalize case number to standard format with dashes

        Args:
            case_number: Case number with or without dashes (e.g., F-25-024652 or F25024652)

        Returns:
            Case number in standard format with dashes (e.g., F-25-024652)
        """
        if not case_number:
            return ""

        # Remove all existing dashes and spaces
        clean = case_number.replace('-', '').replace(' ', '').upper()

        # Expected format: F25024652 (letter + 8 digits)
        # Convert to: F-25-024652
        if len(clean) == 9 and clean[0].isalpha() and clean[1:].isdigit():
            normalized = f"{clean[0]}-{clean[1:3]}-{clean[3:]}"
            self.logger.debug(f"Normalized case number: {case_number} -> {normalized}")
            # #region agent log
            with open('/home/sfeltner/Projects/deuker-monitor/.cursor/debug.log', 'a') as f:
                import json as json_module
                f.write(json_module.dumps({'sessionId':'debug-session','runId':'run1','hypothesisId':'C','location':'deuker-monitor.py:160','message':'Case number normalized','data':{'input':case_number,'clean':clean,'normalized':normalized,'len_clean':len(clean),'is_alpha':clean[0].isalpha() if clean else False,'is_digit':clean[1:].isdigit() if len(clean)>1 else False},'timestamp':int(time.time()*1000)})+'\n')
            # #endregion
            return normalized
        else:
            # Already has dashes or unknown format, return as-is
            self.logger.warning(f"Case number format not recognized: {case_number}")
            # #region agent log
            with open('/home/sfeltner/Projects/deuker-monitor/.cursor/debug.log', 'a') as f:
                import json as json_module
                f.write(json_module.dumps({'sessionId':'debug-session','runId':'run1','hypothesisId':'C','location':'deuker-monitor.py:166','message':'Case number normalization failed','data':{'input':case_number,'clean':clean,'len_clean':len(clean),'returning':case_number.upper()},'timestamp':int(time.time()*1000)})+'\n')
            # #endregion
            return case_number.upper()

    def _load_state(self):
        """Load previously seen charges, dockets, and case info"""
        if self.skip_state:
            self.logger.info("Skipping state loading (--all mode)")
            return

        if self.data_file.exists():
            try:
                with open(self.data_file, 'r') as f:
                    data = json.load(f)
                    self.seen_charges = set(data.get('seen_charges', []))
                    self.seen_dockets = set(data.get('seen_dockets', []))
                    self.seen_documents = set(data.get('seen_documents', []))
                    # Reconstruct case_info
                    for case_num, case_data in data.get('case_info', {}).items():
                        self.case_info[case_num] = CaseInfo(**case_data)
                    # Reconstruct ICE status
                    ice_data = data.get('ice_status')
                    if ice_data:
                        self.ice_status = IceDetaineeStatus(**ice_data)
                    self.ice_check_failures = data.get('ice_check_failures', 0)
                self.logger.info(f"Loaded {len(self.seen_charges)} seen charges, "
                               f"{len(self.seen_dockets)} seen dockets, "
                               f"{len(self.seen_documents)} downloaded documents, "
                               f"{len(self.case_info)} tracked cases")
            except Exception as e:
                self.logger.error(f"Error loading state: {e}")
                self.seen_charges = set()
                self.seen_dockets = set()
                self.seen_documents = set()
                self.case_info = {}
    
    def _save_state(self):
        """Save current state to file"""
        if self.skip_state:
            self.logger.info("Skipping state saving (--all mode)")
            return

        try:
            data = {
                'seen_charges': list(self.seen_charges),
                'seen_dockets': list(self.seen_dockets),
                'seen_documents': list(self.seen_documents),
                'case_info': {k: asdict(v) for k, v in self.case_info.items()},
                'last_updated': datetime.now().isoformat(),
                'defendant_first_name': self.defendant_first_name,
                'defendant_last_name': self.defendant_last_name,
                'defendant_sex': self.defendant_sex,
                'ice_status': asdict(self.ice_status) if self.ice_status else None,
                'ice_check_failures': self.ice_check_failures
            }
            with open(self.data_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            self.logger.error(f"Error saving state: {e}")

    def _init_browser(self):
        """Initialize Playwright browser"""
        try:
            self.logger.info("Initializing browser...")
            self.playwright = sync_playwright().start()
            self.browser = self.playwright.chromium.launch(headless=self.headless)
            self.page = self.browser.new_page()
            # Set a reasonable viewport size
            self.page.set_viewport_size({"width": 1920, "height": 1080})
            self.logger.info("Browser initialized successfully")
        except Exception as e:
            self.logger.error(f"Error initializing browser: {e}")
            raise

    def _take_screenshot(self, description: str = ""):
        """
        Take a screenshot and save it to the screenshots directory

        Args:
            description: Description of what action was performed (used in filename)
        """
        if not self.enable_screenshots:
            return

        if not self.page:
            return

        try:
            self.screenshot_counter += 1
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            safe_desc = re.sub(r'[^\w\s-]', '', description)[:50] if description else "screenshot"
            safe_desc = re.sub(r'[-\s]+', '-', safe_desc)
            filename = f"{self.screenshot_counter:04d}_{timestamp}_{safe_desc}.png"
            filepath = self.screenshots_dir / filename
            self.page.screenshot(path=str(filepath), full_page=True)
            self.logger.debug(f"📸 Screenshot saved: {filename}")
        except Exception as e:
            self.logger.debug(f"Error taking screenshot: {e}")

    def _close_browser(self):
        """Close Playwright browser and cleanup"""
        try:
            if self.page:
                self.page.close()
            if self.browser:
                self.browser.close()
            if self.playwright:
                self.playwright.stop()
            self.logger.info("Browser closed")
        except Exception as e:
            self.logger.error(f"Error closing browser: {e}")

    def _perform_defendant_search(self):
        """
        Navigate to search page and perform defendant search

        This method:
        1. Navigates to the main search page
        2. Clicks on "Defendant" search option
        3. Fills in the defendant information form
        4. Submits the search
        """
        try:
            self.logger.info("Navigating to search page...")
            self.page.goto(self.SEARCH_URL, wait_until="networkidle", timeout=60000)
            self._take_screenshot("01-initial-search-page")

            # Click on "Defendant" button/link
            self.logger.info("Clicking Defendant search option...")
            # Try multiple possible selectors for the Defendant button
            defendant_selectors = [
                'a:has-text("Defendant")',
                'button:has-text("Defendant")',
                '[href*="defendant"]',
                'text=Defendant'
            ]

            clicked = False
            for selector in defendant_selectors:
                try:
                    self.page.click(selector, timeout=5000)
                    clicked = True
                    self.logger.info(f"Clicked Defendant using selector: {selector}")
                    self._take_screenshot("02-after-click-defendant")
                    break
                except:
                    continue

            if not clicked:
                self.logger.error("Could not find Defendant search button")
                self._take_screenshot("02-error-defendant-button-not-found")
                return False

            # Wait for the form popup to appear
            time.sleep(2)

            # Fill in the form
            self.logger.info(f"Filling in search form for {self.defendant_first_name} {self.defendant_last_name}...")

            # First Name
            first_name_selectors = [
                'input[name="firstName"]',
                'input[id*="first"]',
                'input[placeholder*="First"]'
            ]
            for selector in first_name_selectors:
                try:
                    self.page.fill(selector, self.defendant_first_name, timeout=5000)
                    self.logger.debug(f"Filled first name using: {selector}")
                    self._take_screenshot("03-after-fill-first-name")
                    break
                except:
                    continue

            # Last Name
            last_name_selectors = [
                'input[name="lastName"]',
                'input[id*="last"]',
                'input[placeholder*="Last"]'
            ]
            for selector in last_name_selectors:
                try:
                    self.page.fill(selector, self.defendant_last_name, timeout=5000)
                    self.logger.debug(f"Filled last name using: {selector}")
                    self._take_screenshot("04-after-fill-last-name")
                    break
                except:
                    continue

            # Sex dropdown
            sex_selectors = [
                'select[name="sex"]',
                'select[id*="sex"]',
                'select[name="gender"]'
            ]
            for selector in sex_selectors:
                try:
                    self.page.select_option(selector, self.defendant_sex, timeout=5000)
                    self.logger.debug(f"Selected sex using: {selector}")
                    self._take_screenshot("05-after-select-sex")
                    break
                except:
                    continue

            # Click Search button
            self.logger.info("Submitting search...")
            search_button_selectors = [
                'button:has-text("Search")',
                'input[type="submit"]',
                'button[type="submit"]',
                '[value="Search"]'
            ]

            for selector in search_button_selectors:
                try:
                    self.page.click(selector, timeout=5000)
                    self.logger.info(f"Clicked search using: {selector}")
                    self._take_screenshot("06-after-click-search")
                    break
                except:
                    continue

            # Wait for results to load
            time.sleep(3)
            self.logger.info("Search submitted, waiting for results...")
            self._take_screenshot("07-search-results")

            return True

        except Exception as e:
            self.logger.error(f"Error performing defendant search: {e}")
            return False

    def _generate_charge_hash(self, case_number: str, seq_num: str,
                             charge_desc: str, charge_type: str) -> str:
        """Generate unique hash for a charge"""
        content = f"{case_number}|{seq_num}|{charge_desc}|{charge_type}"
        return hashlib.sha256(content.encode()).hexdigest()

    def _generate_docket_hash(self, case_number: str, din: str,
                             date: str, docket_desc: str) -> str:
        """Generate unique hash for a docket entry"""
        content = f"{case_number}|{din}|{date}|{docket_desc}"
        return hashlib.sha256(content.encode()).hexdigest()
    
    def _extract_case_links(self) -> List[Dict[str, str]]:
        """
        Extract case information from the defendant search results

        This method:
        1. Performs the defendant search
        2. Clicks on the defendant result
        3. Extracts case info from the popup table

        Returns:
            List of dicts with case_number, case_url, filed_date, etc.
        """
        cases = []

        try:
            # Perform the defendant search
            if not self._perform_defendant_search():
                self.logger.error("Failed to perform defendant search")
                return cases

            # Click on the defendant result (e.g., "DEUKER, RICARDO")
            self.logger.info(f"Clicking on defendant result for {self.defendant_last_name}, {self.defendant_first_name}...")

            # Try to click on the defendant name
            defendant_name = f"{self.defendant_last_name.upper()}, {self.defendant_first_name.upper()}"
            defendant_selectors = [
                f'text={defendant_name}',
                f':text("{self.defendant_last_name}")',
                '[class*="defendant"]',
                f'div:has-text("{self.defendant_last_name.upper()}")'
            ]

            clicked_defendant = False
            for selector in defendant_selectors:
                try:
                    self.page.click(selector, timeout=5000)
                    self.logger.info(f"Clicked defendant result using: {selector}")
                    self._take_screenshot("08-after-click-defendant-result")
                    clicked_defendant = True
                    break
                except:
                    continue

            if not clicked_defendant:
                self.logger.error("Could not find defendant result to click")
                self._take_screenshot("08-error-defendant-result-not-found")
                return cases

            # Wait for the popup with case information to appear
            time.sleep(2)
            self.logger.info("Extracting cases from popup...")
            self._take_screenshot("09-case-popup-opened")

            # Get the rendered HTML
            html = self.page.content()
            soup = BeautifulSoup(html, 'html.parser')

            # Find the table with case information in the popup
            # The popup should have headers: Case, Filed Date, Closed Date, First Charge, Balance Due
            table = soup.find('table')
            if not table:
                self.logger.warning("No case table found in popup")
                return cases

            rows = table.find_all('tr')
            self.logger.info(f"Found {len(rows)} rows in case table")

            for row in rows:
                cells = row.find_all('td')
                if len(cells) >= 4:  # Need at least Case, Filed Date, Closed Date, First Charge
                    try:
                        # Extract case number
                        case_cell = cells[0]
                        case_text = case_cell.get_text().strip()

                        # Extract case number - it's usually the first line or starts with F-
                        case_number = None
                        case_link = case_cell.find('a')

                        if case_link:
                            # If there's a link, use it
                            case_number = case_link.get_text().strip()
                            case_href = case_link.get('href', '')
                        else:
                            # No link - extract case number from text (e.g., "F-25-024957")
                            import re
                            match = re.search(r'(F-\d{2}-\d+)', case_text)
                            if match:
                                case_number = match.group(1)
                            else:
                                # Try to get first line
                                first_line = case_text.split('\n')[0].strip()
                                if first_line:
                                    case_number = first_line
                            case_href = None

                        if not case_number:
                            self.logger.debug(f"Could not extract case number from: {case_text[:50]}")
                            continue

                        # Build case URL
                        if case_href:
                            if not case_href.startswith('http'):
                                case_url = urljoin(self.BASE_URL, case_href)
                            else:
                                case_url = case_href
                        else:
                            # No href - will click on case number text later
                            case_url = f"{self.BASE_URL}/case/{case_number}"

                        # Extract other fields
                        filed_date = cells[1].get_text().strip() if len(cells) > 1 else ""
                        closed_date = cells[2].get_text().strip() if len(cells) > 2 else ""
                        first_charge = cells[3].get_text().strip() if len(cells) > 3 else ""
                        balance_due = cells[4].get_text().strip() if len(cells) > 4 else ""

                        cases.append({
                            'case_number': case_number,
                            'case_url': case_url,
                            'filed_date': filed_date,
                            'closed_date': closed_date,
                            'first_charge': first_charge,
                            'balance_due': balance_due
                        })

                        self.logger.debug(f"Found case: {case_number}")
                        # #region agent log
                        with open('/home/sfeltner/Projects/deuker-monitor/.cursor/debug.log', 'a') as f:
                            import json as json_module
                            f.write(json_module.dumps({'sessionId':'debug-session','runId':'run1','hypothesisId':'B','location':'deuker-monitor.py:491','message':'Case extracted from page','data':{'case_number':case_number,'case_text_preview':case_text[:50],'has_link':case_link is not None,'filter_case_number':self.filter_case_number},'timestamp':int(time.time()*1000)})+'\n')
                        # #endregion

                    except Exception as e:
                        self.logger.debug(f"Error parsing case row: {e}")
                        continue

        except Exception as e:
            self.logger.error(f"Error extracting case links: {e}")
            import traceback
            self.logger.debug(traceback.format_exc())

        return cases
    
    def _fetch_case_details(self, case_url: str, case_number: str) -> tuple[List[Charge], List[DocketEntry], int, int]:
        """
        Fetch all charges and docket entries for a specific case

        Args:
            case_url: URL to the case details page
            case_number: Case number for reference

        Returns:
            Tuple of (charges_list, dockets_list, new_documents_count, total_documents_count)
        """
        charges = []
        dockets = []
        new_documents_count = 0
        total_documents_count = 0

        try:
            # Click on the case number link to view docket details
            self.logger.info(f"Clicking on case {case_number} to view docket...")

            # First check if the case number is visible on the page
            html = self.page.content()
            if case_number in html:
                self.logger.debug(f"Case number {case_number} found in page content")
            else:
                self.logger.warning(f"Case number {case_number} NOT found in page content!")
                self.logger.debug(f"Page contains: {html[:500]}...")

            case_link_selectors = [
                f'a:has-text("{case_number}")',
                f'text={case_number}',
                f'[href*="{case_number}"]'
            ]

            clicked_case = False
            for selector in case_link_selectors:
                try:
                    self.logger.debug(f"Trying selector: {selector}")
                    self.page.click(selector, timeout=5000)
                    self.logger.info(f"✓ Clicked case {case_number} using: {selector}")
                    self._take_screenshot(f"10-after-click-case-{case_number}")
                    clicked_case = True
                    break
                except Exception as e:
                    self.logger.debug(f"Selector {selector} failed: {e}")
                    continue

            if not clicked_case:
                self.logger.warning(f"Could not click case {case_number}, trying URL navigation...")
                self._take_screenshot(f"10-error-case-click-failed-{case_number}")
                # Fallback: try to navigate directly if clicking didn't work
                if case_url:
                    self.page.goto(case_url, wait_until="networkidle", timeout=60000)
                    self._take_screenshot(f"10-after-navigate-case-{case_number}")
                else:
                    self.logger.error(f"No URL available for case {case_number}, cannot navigate!")
                    return charges, dockets

            # Wait for case page to load
            time.sleep(2)
            self.logger.debug(f"Case page loaded, URL: {self.page.url}")
            self._take_screenshot(f"11-case-page-loaded-{case_number}")

            # STEP 1: Expand and parse CHARGES section
            self.logger.info(f"Expanding CHARGES section for {case_number}...")

            # Check if CHARGES text exists on the page
            html = self.page.content()
            if 'CHARGES' in html.upper():
                self.logger.debug("'CHARGES' text found in page")
            else:
                self.logger.warning("'CHARGES' text NOT found in page!")

            try:
                # Try to click on CHARGES header to expand it
                charges_selectors = [
                    'text=CHARGES',
                    ':has-text("CHARGES")',
                    '[class*="charges"]'
                ]
                clicked_charges = False
                for selector in charges_selectors:
                    try:
                        self.logger.debug(f"Trying CHARGES selector: {selector}")
                        self.page.click(selector, timeout=3000)
                        self.logger.info(f"✓ Clicked CHARGES using: {selector}")
                        self._take_screenshot(f"12-after-click-charges-{case_number}")
                        clicked_charges = True
                        time.sleep(1)
                        break
                    except Exception as e:
                        self.logger.debug(f"CHARGES selector {selector} failed: {e}")
                        continue

                if not clicked_charges:
                    self.logger.warning("Could not click CHARGES section - may already be expanded or not found")
                    self._take_screenshot(f"12-charges-not-clickable-{case_number}")
            except Exception as e:
                self.logger.warning(f"Error expanding CHARGES section: {e}")

            # Parse CHARGES table
            html = self.page.content()
            soup = BeautifulSoup(html, 'html.parser')

            # Find all tables and look for the one with charges
            for table in soup.find_all('table'):
                headers = table.find_all('th')
                if headers:
                    header_text = ' '.join([h.get_text() for h in headers]).lower()
                    if 'seq no' in header_text and 'charge' in header_text:
                        # This is the charges table
                        self.logger.debug(f"Found CHARGES table for {case_number}")
                        rows = table.find_all('tr')
                        for row in rows[1:]:  # Skip header
                            cells = row.find_all('td')
                            if len(cells) >= 3:
                                try:
                                    seq_no = cells[0].get_text().strip()
                                    charge_desc = cells[1].get_text().strip()
                                    charge_type = cells[2].get_text().strip()
                                    disposition = cells[3].get_text().strip() if len(cells) > 3 else ""

                                    charge = Charge(
                                        case_number=case_number,
                                        sequence_number=seq_no,
                                        charge_description=charge_desc,
                                        charge_type=charge_type,
                                        disposition=disposition,
                                        timestamp_found=datetime.now().isoformat()
                                    )
                                    charges.append(charge)
                                    self.logger.debug(f"Found charge: {seq_no} - {charge_desc}")
                                except Exception as e:
                                    self.logger.debug(f"Error parsing charge row: {e}")
                        break

            # STEP 2: Expand and parse DOCKETS section
            self.logger.info(f"Expanding DOCKETS section for {case_number}...")

            # Check if DOCKETS text exists on the page
            html = self.page.content()
            if 'DOCKETS' in html.upper():
                self.logger.debug("'DOCKETS' text found in page")
            else:
                self.logger.warning("'DOCKETS' text NOT found in page!")

            try:
                # Try to click on DOCKETS header to expand it
                dockets_selectors = [
                    'text=DOCKETS',
                    ':has-text("DOCKETS")',
                    '[class*="dockets"]'
                ]
                clicked_dockets = False
                for selector in dockets_selectors:
                    try:
                        self.logger.debug(f"Trying DOCKETS selector: {selector}")
                        self.page.click(selector, timeout=3000)
                        self.logger.info(f"✓ Clicked DOCKETS using: {selector}")
                        self._take_screenshot(f"13-after-click-dockets-{case_number}")
                        clicked_dockets = True
                        time.sleep(1)
                        break
                    except Exception as e:
                        self.logger.debug(f"DOCKETS selector {selector} failed: {e}")
                        continue

                if not clicked_dockets:
                    self.logger.warning("Could not click DOCKETS section - may already be expanded or not found")
                    self._take_screenshot(f"13-dockets-not-clickable-{case_number}")
            except Exception as e:
                self.logger.warning(f"Error expanding DOCKETS section: {e}")

            # Parse DOCKETS table
            html = self.page.content()
            soup = BeautifulSoup(html, 'html.parser')

            # Find all tables and look for the one with dockets
            for table in soup.find_all('table'):
                headers = table.find_all('th')
                if headers:
                    header_text = ' '.join([h.get_text() for h in headers]).lower()
                    if 'din' in header_text and 'docket' in header_text:
                        # This is the dockets table
                        self.logger.debug(f"Found DOCKETS table for {case_number}")
                        rows = table.find_all('tr')
                        for row in rows[1:]:  # Skip header
                            cells = row.find_all('td')
                            if len(cells) >= 4:
                                try:
                                    # Columns: View Image, Din, Date, Book/Page, Docket
                                    # Check if first cell has a "View Docket Image" link/icon
                                    has_document = False
                                    view_image_cell = cells[0]

                                    # Look for document indicators: img, a, svg tags, or span with role="button"
                                    if (view_image_cell.find('img') or
                                        view_image_cell.find('a') or
                                        view_image_cell.find('svg') or
                                        view_image_cell.find('span', {'role': 'button', 'aria-label': 'View Docket Image'})):
                                        # Check for image or link in the first column
                                        has_document = True
                                        self.logger.debug(f"Document available for Din {cells[1].get_text().strip()}")

                                    din = cells[1].get_text().strip()
                                    date = cells[2].get_text().strip()
                                    book_page = cells[3].get_text().strip() if len(cells) > 3 else ""
                                    docket_desc = cells[4].get_text().strip() if len(cells) > 4 else ""

                                    docket = DocketEntry(
                                        case_number=case_number,
                                        din=din,
                                        date=date,
                                        docket_description=docket_desc,
                                        book_page=book_page,
                                        timestamp_found=datetime.now().isoformat(),
                                        has_document=has_document
                                    )
                                    dockets.append(docket)
                                    self.logger.debug(f"Found docket: {din} - {docket_desc[:50]}")
                                except Exception as e:
                                    self.logger.debug(f"Error parsing docket row: {e}")
                        break

            # Log summary of what was found
            self.logger.info(f"✓ Extracted {len(charges)} charge(s) and {len(dockets)} docket(s) from {case_number}")

            if not charges and not dockets:
                self.logger.warning(f"No charges or dockets found for {case_number}")

            # Download documents if enabled and documents are available
            if self.download_documents and any(d.has_document for d in dockets):
                new_docs, total_docs = self._download_case_documents(case_number, dockets)
                new_documents_count += new_docs
                total_documents_count += total_docs

            # Check for "Extra Documents" tab
            if self.download_documents:
                new_docs, total_docs = self._check_extra_documents_tab(case_number)
                new_documents_count += new_docs
                total_documents_count += total_docs

        except Exception as e:
            self.logger.error(f"Error fetching case details for {case_number}: {e}")
            import traceback
            self.logger.debug(traceback.format_exc())

        return charges, dockets, new_documents_count, total_documents_count

    def _download_case_documents(self, case_number: str, dockets: List[DocketEntry]) -> tuple[int, int]:
        """
        Download documents for dockets that have them available

        Args:
            case_number: The case number
            dockets: List of docket entries to check for documents

        Returns:
            Tuple of (new_documents_count, total_documents_count)
        """
        import os
        import re

        new_documents_count = 0
        total_documents_count = 0

        self.logger.info(f"Checking for documents to download in {case_number}...")

        # Ensure DOCKETS section is expanded
        try:
            # Look for DOCKETS button/tab and click it if not already expanded
            dockets_selectors = [
                ':has-text("DOCKETS")',
                'text=DOCKETS',
                'button:has-text("DOCKETS")',
            ]

            for selector in dockets_selectors:
                try:
                    dockets_btn = self.page.locator(selector)
                    if dockets_btn.count() > 0:
                        self.logger.debug(f"Clicking DOCKETS section to expand...")
                        dockets_btn.first.click(timeout=3000)
                        time.sleep(1)  # Wait for expansion
                        self.logger.debug("DOCKETS section expanded")
                        break
                except:
                    pass
        except Exception as e:
            self.logger.debug(f"Error expanding DOCKETS section: {e}")

        for docket in dockets:
            if not docket.has_document:
                continue

            # Count this document (whether new or already seen)
            total_documents_count += 1

            # Create a unique identifier for this document
            doc_id = f"{case_number}_{docket.din}_{docket.docket_description}"

            # Check if we've already downloaded this document
            if doc_id in self.seen_documents:
                self.logger.debug(f"Document already downloaded: {doc_id}")
                continue

            # This is a new document
            new_documents_count += 1

            try:
                # Create case-specific subdirectory
                case_dir = self.documents_dir / case_number
                case_dir.mkdir(parents=True, exist_ok=True)

                # Generate safe filename: docket_description.pdf (no need for case_number prefix since it's in folder)
                # Clean docket description to be filesystem-safe
                safe_desc = re.sub(r'[^\w\s-]', '', docket.docket_description)
                safe_desc = re.sub(r'[-\s]+', '-', safe_desc)
                safe_desc = safe_desc[:100]  # Limit length
                filename = f"{safe_desc}.pdf"
                filepath = case_dir / filename

                # If file already exists, add a counter
                counter = 1
                original_filepath = filepath
                while filepath.exists():
                    filename = f"{safe_desc}-{counter}.pdf"
                    filepath = case_dir / filename
                    counter += 1

                self.logger.info(f"Downloading document for Din {docket.din}: {case_number}/{filename}")

                # Strategy: Click "View Image" button, wait for viewer, click download button
                self.logger.debug(f"Attempting to open document viewer for Din {docket.din}")

                # Step 1: Find and click the "View Image" button
                desc_search = docket.docket_description[:30].strip()
                self.logger.debug(f"Looking for row with description: {desc_search}")

                # Find all rows, check if they contain this docket description
                rows = self.page.locator('table tr')
                clicked_view = False
                viewer_page = None  # Will hold the popup page if opened

                for i in range(rows.count()):
                    row = rows.nth(i)
                    row_text = row.inner_text()

                    # Check if this row contains the docket description
                    if desc_search in row_text:
                        self.logger.debug(f"Found matching row for Din {docket.din}")

                        # Click the view image button
                        try:
                            # Find all spans with View Docket Image in this row
                            view_buttons = row.locator('span[role="button"][aria-label="View Docket Image"]')
                            button_count = view_buttons.count()
                            self.logger.debug(f"Found {button_count} View Image buttons in row")

                            if button_count > 0:
                                self.logger.debug(f"Clicking View Image button...")

                                # Get current page count before click
                                initial_pages = len(self.page.context.pages)
                                current_url = self.page.url

                                # Try to scroll the button into view and click it
                                try:
                                    # Scroll the row into view first
                                    row.scroll_into_view_if_needed()
                                    time.sleep(0.5)

                                    # Try the last button (usually desktop version)
                                    last_btn = view_buttons.last
                                    last_btn.scroll_into_view_if_needed()
                                    time.sleep(0.5)

                                    # Click and wait for React PDF Viewer to load
                                    self.logger.debug("Clicking for React PDF Viewer...")
                                    last_btn.dispatch_event('click', {'bubbles': True, 'cancelable': True})
                                    clicked_view = True
                                    self.logger.debug("Click event dispatched, waiting for React components...")

                                    # Wait longer for React components to mount
                                    time.sleep(2)

                                    # Look for modal, overlay, or dialog that might contain the viewer
                                    modal_selectors = [
                                        '.modal',
                                        '[role="dialog"]',
                                        '.rpv-core__modal',
                                        '.rpv-core__viewer',
                                        'div[class*="modal"]',
                                        'div[class*="dialog"]',
                                        'div[class*="overlay"]',
                                    ]

                                    viewer_found = False
                                    for modal_sel in modal_selectors:
                                        modal = self.page.locator(modal_sel)
                                        if modal.count() > 0:
                                            self.logger.debug(f"Found modal/overlay with selector: {modal_sel}")
                                            viewer_found = True
                                            break

                                    if not viewer_found:
                                        # Check for new pages/tabs
                                        all_pages = self.page.context.pages
                                        if len(all_pages) > initial_pages:
                                            viewer_page = all_pages[-1]
                                            self.page = viewer_page
                                            self.logger.debug(f"Switched to new page: {viewer_page.url}")
                                            viewer_found = True
                                except Exception as js_error:
                                    self.logger.debug(f"JS click failed: {js_error}, trying regular click with force...")
                                    try:
                                        view_buttons.last.click(force=True, timeout=5000)
                                        clicked_view = True
                                        self.logger.debug("Button clicked with force=True")
                                    except Exception as force_error:
                                        self.logger.debug(f"Force click also failed: {force_error}")

                                # Don't wait - check immediately and then wait for viewer
                                # Check if a new page opened
                                current_pages = self.page.context.pages
                                if len(current_pages) > initial_pages:
                                    # New page/popup opened
                                    viewer_page = current_pages[-1]  # Last page is the new one
                                    self.logger.debug(f"New page opened: {viewer_page.url}")
                                    self.page = viewer_page
                                    self.logger.info(f"✓ Opened viewer in new page for Din {docket.din}")
                                elif self.page.url != current_url:
                                    # Current page navigated
                                    self.logger.info(f"✓ Navigated to viewer page: {self.page.url}")
                                else:
                                    # Viewer might be loading inline - wait for React PDF Viewer components
                                    self.logger.debug("Waiting for React PDF Viewer to load...")
                                    try:
                                        # Wait for the viewer container to appear (React PDF Viewer takes time to render)
                                        self.page.locator('.rpv-default-layout__container, .rpv-core__viewer').wait_for(state='attached', timeout=15000)
                                        self.logger.info(f"✓ React PDF Viewer loaded for Din {docket.din}")

                                        # Wait an additional moment for full render
                                        time.sleep(2)
                                    except:
                                        self.logger.warning(f"React PDF Viewer did not load - trying to find PDF URL directly...")

                                        # Try to extract PDF URL from page source/network
                                        try:
                                            # Look for PDF URL in the page
                                            pdf_url_pattern = r'(https?://[^\s<>"]+\.pdf[^\s<>"]*|/cjis/[^\s<>"]*docketimage[^\s<>"]*)'
                                            page_content = self.page.content()
                                            import re as re_module
                                            pdf_urls = re_module.findall(pdf_url_pattern, page_content)
                                            if pdf_urls:
                                                self.logger.debug(f"Found potential PDF URLs: {pdf_urls[:3]}")
                                        except:
                                            pass

                                break
                        except Exception as e:
                            self.logger.debug(f"View button click failed: {e}")

                        break

                if not clicked_view:
                    raise Exception(f"Could not open viewer for Din {docket.din}")

                # Use the consolidated React PDF Viewer download helper
                if self._handle_react_pdf_viewer_download(filepath, viewer_page, f"Din {docket.din}"):
                    # Success!
                    self.seen_documents.add(doc_id)
                    docket.document_downloaded = True
                    docket.document_filename = filename
                else:
                    raise Exception(f"Failed to download document for Din {docket.din}")

                # Small delay between downloads
                time.sleep(0.5)

            except Exception as e:
                self.logger.error(f"Error downloading document for Din {docket.din}: {e}")
                import traceback
                self.logger.debug(traceback.format_exc())

                # Try to close any popup pages and return to main page
                try:
                    pages = self.page.context.pages
                    # Close all pages except the first (main) page
                    for i in range(len(pages) - 1, 0, -1):
                        try:
                            pages[i].close()
                            self.logger.debug(f"Closed page {i}")
                        except:
                            pass
                    # Return to main page
                    if pages:
                        self.page = pages[0]
                        self.logger.debug("Returned to main page after error")
                except Exception as cleanup_error:
                    self.logger.debug(f"Error cleaning up pages: {cleanup_error}")

        return new_documents_count, total_documents_count

    def _handle_react_pdf_viewer_download(self, filepath, viewer_page=None, doc_label="document") -> bool:
        """
        Handle React PDF Viewer interaction and download after view button is clicked.
        This consolidates the common workflow for downloading from the React PDF Viewer.

        Args:
            filepath: Path object where to save the downloaded file
            viewer_page: Optional reference to viewer page if it opened in new tab
            doc_label: Label for logging (e.g., "Din 27", "Arrest Form Summary")

        Returns:
            True if download was successful, False otherwise
        """
        try:
            # Step 1: Wait for viewer to fully load
            self.logger.debug(f"Waiting for viewer to load...")
            time.sleep(5)  # Allow viewer to fully load

            # Step 2: Verify React PDF Viewer components are present
            viewer_container = self.page.locator('.rpv-default-layout__container')
            self.logger.debug(f"Viewer container count: {viewer_container.count()}")

            # Debug: Log page URL and check for common viewer elements
            self.logger.info(f"DEBUG: Current page URL: {self.page.url}")

            # Check for various viewer elements
            for selector in ['.rpv-default-layout__toolbar', '.rpv-toolbar__right', 'button[aria-label="Download"]', '[data-testid="get-file__download-button"]']:
                count = self.page.locator(selector).count()
                self.logger.info(f"DEBUG: Selector '{selector}' count: {count}")

            # Step 3: Find and click the download button using multiple selector strategies
            with self.page.expect_download(timeout=30000) as download_info:
                download_clicked = False

                # Strategy 1: Full CSS selector path (most specific)
                try:
                    download_btn = self.page.locator(
                        '#content > div > div > div.col-md-9 > div > div:nth-child(2) > div > div > div > '
                        'div.rpv-default-layout__container > div > div.rpv-default-layout__body > '
                        'div.rpv-default-layout__toolbar > div > div.rpv-toolbar__right > div:nth-child(4)'
                    )
                    if download_btn.count() > 0:
                        self.logger.debug(f"Clicking download button (full selector)...")
                        download_btn.first.click(force=True, timeout=5000)
                        download_clicked = True
                        self.logger.info(f"✓ Clicked download button for {doc_label}")
                except Exception as e:
                    self.logger.debug(f"Full CSS selector failed: {e}")

                # Strategy 2: Class-based selector (more flexible)
                if not download_clicked:
                    try:
                        download_btn = self.page.locator('.rpv-toolbar__right > div:nth-child(4)')
                        if download_btn.count() > 0:
                            self.logger.debug(f"Clicking download button (class selector)...")
                            download_btn.first.click(force=True, timeout=5000)
                            download_clicked = True
                            self.logger.info(f"✓ Clicked download button (class selector) for {doc_label}")
                    except Exception as e:
                        self.logger.debug(f"Class selector failed: {e}")

                # Strategy 3: Aria-label selector (most semantic)
                if not download_clicked:
                    try:
                        download_btn = self.page.locator('.rpv-default-layout__toolbar button[aria-label="Download"]')
                        if download_btn.count() > 0:
                            self.logger.debug(f"Clicking download button (aria-label)...")
                            download_btn.first.click(force=True, timeout=5000)
                            download_clicked = True
                            self.logger.info(f"✓ Clicked download button (aria-label) for {doc_label}")
                    except Exception as e:
                        self.logger.debug(f"Aria-label selector failed: {e}")

                if not download_clicked:
                    self.logger.error(f"Could not find download button for {doc_label}")
                    return False

            # Step 4: Save the downloaded file
            download = download_info.value
            download.save_as(filepath)
            self.logger.info(f"📥 Downloaded: {filepath.name}")

            # Step 5: Close the viewer popup/tab and return to original page
            try:
                if viewer_page:
                    viewer_page.close()
                    self.logger.debug("Closed viewer page")

                pages = self.page.context.pages
                if pages:
                    self.page = pages[0]
                    self.logger.debug("Returned to main page")
            except Exception as e:
                self.logger.debug(f"Error closing viewer page: {e}")

            return True

        except Exception as e:
            self.logger.error(f"Error in React PDF Viewer download for {doc_label}: {e}")
            return False

    def _check_extra_documents_tab(self, case_number: str) -> tuple[int, int]:
        """Check and download documents from the Extra Documents tab if it exists

        Returns:
            Tuple of (new_documents_count, total_documents_count)
        """
        import re

        new_documents_count = 0
        total_documents_count = 0

        try:
            self.logger.debug(f"Checking for Extra Documents tab in {case_number}...")

            # Look for "Extra Documents" tab/link
            html = self.page.content()
            if 'EXTRA DOCUMENTS' not in html.upper():
                self.logger.debug("No Extra Documents tab found")
                return new_documents_count, total_documents_count

            # Try to click on Extra Documents tab
            extra_docs_selectors = [
                'text=EXTRA DOCUMENTS',
                'text=Extra Documents',
                ':has-text("EXTRA DOCUMENTS")',
                ':has-text("Extra Documents")'
            ]

            clicked = False
            for selector in extra_docs_selectors:
                try:
                    self.logger.debug(f"Trying Extra Documents selector: {selector}")
                    self.page.click(selector, timeout=3000)
                    self.logger.info(f"✓ Clicked Extra Documents tab using: {selector}")
                    self._take_screenshot(f"14-after-click-extra-documents-{case_number}")
                    clicked = True
                    time.sleep(1)
                    break
                except Exception as e:
                    self.logger.debug(f"Extra Documents selector {selector} failed: {e}")
                    continue

            if not clicked:
                self.logger.debug("Could not click Extra Documents tab")
                self._take_screenshot(f"14-extra-documents-not-clickable-{case_number}")
                return new_documents_count, total_documents_count

            # Parse the Extra Documents table
            html = self.page.content()
            soup = BeautifulSoup(html, 'html.parser')

            # Find the Extra Documents table (has "document" column, NO "din" or "book" columns)
            extra_docs_table = None
            for table in soup.find_all('table'):
                headers = table.find_all('th')
                if headers and len(headers) >= 2:
                    header_text = ' '.join([h.get_text() for h in headers]).lower()
                    self.logger.debug(f"Found table with headers: {header_text}")

                    if ('view' in header_text or 'image' in header_text) and \
                       'document' in header_text and \
                       'din' not in header_text and \
                       'book' not in header_text:
                        extra_docs_table = table
                        self.logger.info(f"✓ Found Extra Documents table in {case_number}")
                        break

            if not extra_docs_table:
                self.logger.debug("Could not find Extra Documents table")
                return new_documents_count, total_documents_count

            rows = extra_docs_table.find_all('tr')
            self.logger.info(f"Found {len(rows)-1} row(s) in Extra Documents table")

            for row_index, row in enumerate(rows[1:], start=1):  # Skip header
                cells = row.find_all('td')
                if len(cells) >= 2:
                    try:
                        # Check if first cell has a view/download button
                        view_cell = cells[0]
                        if not (view_cell.find('img') or view_cell.find('a') or view_cell.find('svg') or
                                view_cell.find('span', {'role': 'button'})):
                            continue

                        # Count this document (whether new or already seen)
                        total_documents_count += 1

                        # Get document description from the last column
                        doc_desc = ""
                        if len(cells) >= 3:
                            doc_desc = cells[-1].get_text().strip()

                        # Fallback to searching all cells
                        if not doc_desc or len(doc_desc) < 3:
                            for cell in cells[1:]:
                                text = cell.get_text().strip()
                                if text and len(text) > 3:
                                    doc_desc = text
                                    break

                        if not doc_desc:
                            doc_desc = f"extra-doc-{row_index}"

                        # Create unique ID for this document
                        doc_id = f"{case_number}_extra_{doc_desc}"

                        # Check if already downloaded
                        if doc_id in self.seen_documents:
                            self.logger.debug(f"Extra document already downloaded: {doc_id}")
                            continue

                        # This is a new document
                        new_documents_count += 1

                        # Create case-specific subdirectory
                        case_dir = self.documents_dir / case_number
                        case_dir.mkdir(parents=True, exist_ok=True)

                        # Generate safe filename (no need for case_number prefix since it's in folder)
                        safe_desc = re.sub(r'[^\w\s-]', '', doc_desc)
                        safe_desc = re.sub(r'[-\s]+', '-', safe_desc)
                        safe_desc = safe_desc[:100]
                        filename = f"{safe_desc}.pdf"
                        filepath = case_dir / filename

                        # Handle duplicate filenames
                        counter = 1
                        while filepath.exists():
                            filename = f"{safe_desc}-{counter}.pdf"
                            filepath = case_dir / filename
                            counter += 1

                        self.logger.info(f"Downloading extra document: {case_number}/{filename}")

                        # For Extra Documents, find and click view button by looking for SVG icon
                        # Extra Documents uses a different structure than Dockets
                        clicked_view = False
                        viewer_page = None
                        initial_pages = 0  # Will be set when button is found
                        current_url = ""   # Will be set when button is found

                        self.logger.debug(f"Looking for Extra Doc view button for: {doc_desc}")

                        # Use same approach as working Dockets code
                        # Find all table rows and look for the one containing our document description
                        desc_search = doc_desc[:30].strip()  # Use first 30 chars for matching
                        self.logger.debug(f"Looking for row with description: {desc_search}")

                        rows = self.page.locator('table tr')
                        view_btn_found = False

                        for i in range(rows.count()):
                            row = rows.nth(i)
                            row_text = row.inner_text()

                            # Check if this row contains the document description
                            if desc_search in row_text:
                                self.logger.debug(f"Found matching row for Extra Doc: {doc_desc}")

                                # Look for view buttons - try multiple selector strategies
                                # Extra Documents may use different aria-labels than Dockets
                                view_button_selectors = [
                                    'span[role="button"][aria-label*="View"]',
                                    'span[role="button"]',
                                    'button[aria-label*="View"]',
                                    'button',
                                    'a[href*="viewDocument"]',
                                ]

                                for selector in view_button_selectors:
                                    try:
                                        view_buttons = row.locator(selector)
                                        button_count = view_buttons.count()

                                        if button_count > 0:
                                            self.logger.debug(f"Found {button_count} buttons with selector '{selector}' in Extra Doc row")

                                            # Get current state before clicking
                                            initial_pages = len(self.page.context.pages)
                                            current_url = self.page.url

                                            # Scroll the row into view
                                            try:
                                                row.scroll_into_view_if_needed()
                                                time.sleep(0.5)
                                            except:
                                                pass

                                            # Try to click the last button (usually desktop version)
                                            try:
                                                last_btn = view_buttons.last
                                                last_btn.scroll_into_view_if_needed()
                                                time.sleep(0.5)

                                                # Use dispatch_event like Dockets code (proven to work)
                                                self.logger.debug(f"Clicking Extra Doc view button with dispatch_event...")
                                                self.logger.debug(f"DEBUG: Before click - URL: {current_url}, Pages: {initial_pages}")
                                                last_btn.dispatch_event('click', {'bubbles': True, 'cancelable': True})
                                                clicked_view = True
                                                view_btn_found = True
                                                self.logger.info(f"✓ Clicked Extra Doc view button for: {doc_desc}")

                                                # Wait for viewer to start loading
                                                time.sleep(3)  # Longer wait for viewer initialization

                                                # Debug: Check what happened after click
                                                self.logger.debug(f"DEBUG: After click - URL: {self.page.url}, Pages: {len(self.page.context.pages)}")
                                                self._take_screenshot(f"14z-after-extra-doc-click-{case_number}")
                                                break
                                            except Exception as click_error:
                                                self.logger.debug(f"Click failed with selector '{selector}': {click_error}")
                                                continue
                                    except Exception as e:
                                        self.logger.debug(f"Selector {selector} failed: {e}")
                                        continue

                                if view_btn_found:
                                    break

                        if not view_btn_found:
                            self.logger.warning(f"Could not find/click view button for: {doc_desc}")
                            continue

                        # Wait additional time for viewer to load
                        time.sleep(2)

                        # Track if we navigated inline (same page, different URL)
                        navigated_inline = False
                        viewer_loaded = False
                        
                        # Check if new page opened
                        current_pages = self.page.context.pages
                        if len(current_pages) > initial_pages:
                            # New page/popup opened
                            viewer_page = current_pages[-1]
                            self.page = viewer_page
                            self.logger.info(f"✓ Opened viewer in new page for {doc_desc}")
                            # Wait a bit more for viewer to initialize
                            time.sleep(2)
                            # Assume viewer is available when new page opens
                            viewer_loaded = True
                            self._take_screenshot(f"14a-after-extra-documents-viewer-loaded-{case_number}")
                        elif self.page.url != current_url:
                            # Current page navigated inline
                            navigated_inline = True
                            viewer_loaded = False
                            self.logger.info(f"✓ Navigated to viewer page (inline): {self.page.url}")
                            # Wait for React PDF Viewer to load on current page
                            try:
                                self.page.locator('.rpv-default-layout__container, .rpv-core__viewer').wait_for(
                                    state='attached', timeout=15000
                                )
                                self.logger.info(f"✓ React PDF Viewer loaded inline for {doc_desc}")
                                time.sleep(2)  # Additional wait for full render
                                viewer_loaded = True
                                self._take_screenshot(f"14b-after-extra-documents-viewer-loaded-{case_number}")
                            except Exception as e:
                                self._take_screenshot(f"14e-failed-extra-documents-viewer-loaded-{case_number}")
                                self.logger.warning(f"React PDF Viewer did not load within timeout: {e}")
                                viewer_loaded = False
                        else:
                            # No navigation detected - wait for viewer to load inline
                            # This matches the Dockets code approach
                            self.logger.debug("No navigation detected, waiting for React PDF Viewer to load...")
                            viewer_loaded = False
                            try:
                                # Wait for the viewer container to appear (React PDF Viewer takes time to render)
                                # Use same timeout as Dockets code (15 seconds)
                                self.page.locator('.rpv-default-layout__container, .rpv-core__viewer').wait_for(
                                    state='attached', timeout=15000
                                )
                                self.logger.info(f"✓ React PDF Viewer loaded inline for {doc_desc}")
                                # Wait an additional moment for full render
                                time.sleep(2)
                                viewer_loaded = True
                                self._take_screenshot(f"14c-after-extra-documents-viewer-loaded-{case_number}")
                            except Exception as e:
                                self._take_screenshot(f"14d-failed-extra-documents-viewer-loaded-{case_number}")
                                self.logger.warning(f"React PDF Viewer did not load within timeout: {e}")

                                # Try to extract PDF URL from page source as fallback (like Dockets code)
                                try:
                                    self.logger.debug("Attempting to find PDF URL directly in page source...")
                                    pdf_url_pattern = r'(https?://[^\s<>"]+\.pdf[^\s<>"]*|/cjis/[^\s<>"]*viewDocument[^\s<>"]*)'
                                    page_content = self.page.content()
                                    import re as re_module
                                    pdf_urls = re_module.findall(pdf_url_pattern, page_content)
                                    if pdf_urls:
                                        self.logger.debug(f"Found potential PDF URLs: {pdf_urls[:3]}")
                                except:
                                    pass

                                viewer_loaded = False

                        # Use the consolidated React PDF Viewer download helper only if viewer loaded
                        # viewer_page is set when a new page opened, navigated_inline is True when URL changed,
                        # and viewer_loaded is True when viewer container appeared
                        if viewer_page is not None or (navigated_inline and viewer_loaded) or viewer_loaded:
                            download_success = self._handle_react_pdf_viewer_download(filepath, viewer_page, doc_desc)
                        else:
                            download_success = False
                            self.logger.warning(f"Could not download {doc_desc} - no viewer detected")
                        
                        if download_success:
                            # Success!
                            self.seen_documents.add(doc_id)
                            self.logger.info(f"✓ Downloaded extra document: {case_number}/{filename}")
                        else:
                            self.logger.warning(f"Failed to download extra document: {doc_desc}")

                        # Navigate back to Extra Documents tab to return to the list
                        try:
                            # If we navigated inline (same page, different URL), use browser back
                            if navigated_inline:
                                self.logger.debug("Navigating back (inline navigation detected)")
                                try:
                                    self.page.go_back()
                                    time.sleep(2)
                                    # Wait for page to load after going back
                                    self.page.wait_for_load_state('networkidle', timeout=5000)
                                except Exception as back_error:
                                    self.logger.debug(f"Browser back failed: {back_error}")
                            
                            # Try to re-click Extra Documents tab
                            # First check if we're on the right page
                            current_url = self.page.url
                            if 'viewDocument' in current_url:
                                # Still on viewer page - go back
                                try:
                                    self.page.go_back()
                                    time.sleep(2)
                                except:
                                    pass
                            
                            # Now try to click Extra Documents tab
                            extra_docs_clicked = False
                            for selector in extra_docs_selectors:
                                try:
                                    extra_docs_elem = self.page.locator(selector)
                                    if extra_docs_elem.count() > 0:
                                        extra_docs_elem.first.click(timeout=3000)
                                        self.logger.debug("Re-clicked Extra Documents tab")
                                        time.sleep(1)
                                        extra_docs_clicked = True
                                        break
                                except Exception as e:
                                    self.logger.debug(f"Failed to re-click Extra Documents with {selector}: {e}")
                                    continue
                            
                            if not extra_docs_clicked:
                                self.logger.debug("Could not re-click Extra Documents tab - may need to re-navigate to case")
                        except Exception as nav_error:
                            self.logger.debug(f"Error navigating back to Extra Documents: {nav_error}")

                        # Small delay between downloads
                        time.sleep(0.5)

                    except Exception as e:
                        self.logger.debug(f"Error downloading extra document from row {row_index}: {e}")
                        continue

        except Exception as e:
            self.logger.debug(f"Error checking Extra Documents tab: {e}")

        return new_documents_count, total_documents_count

    def _check_ice_status(self) -> Optional[IceDetaineeStatus]:
        """
        Check ICE detainee locator for current status.
        Opens a new browser page to avoid interfering with court monitor page.
        """
        if not self.ice_monitoring:
            return None

        driver = None
        try:
            self.logger.info("Checking ICE detainee locator...")
            import undetected_chromedriver as uc
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait, Select
            from selenium.webdriver.support import expected_conditions as EC
            from selenium.webdriver.common.action_chains import ActionChains

            options = uc.ChromeOptions()
            # ICE site WAF blocks headless browsers, so always run non-headless
            # The window will briefly appear on screen during checks
            options.add_argument("--window-size=1920,1080")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")

            driver = uc.Chrome(options=options, version_main=145)
            driver.get("https://locator.ice.gov/odls/#/search")

            # Wait for Angular app to load
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input, form, app-root"))
            )
            # Wait for reCAPTCHA v3 to fully load and build a baseline score
            time.sleep(5)

            # Simulate human-like page interaction to boost reCAPTCHA score
            actions = ActionChains(driver)
            # Move mouse around the page naturally
            actions.move_by_offset(400, 300).pause(0.5)
            actions.move_by_offset(-100, 50).pause(0.3)
            actions.perform()

            if self.enable_screenshots:
                driver.save_screenshot(str(self.screenshots_dir / "ice_01_search_page.png"))

            # Check for access denied
            if "Access Denied" in driver.page_source:
                self.logger.error("ICE locator: Access Denied by WAF")
                return None

            # Fill in last name
            last_name_selectors = [
                (By.ID, "lastName"),
                (By.CSS_SELECTOR, 'input[formcontrolname="lastName"]'),
                (By.CSS_SELECTOR, 'input[name="lastName"]'),
                (By.CSS_SELECTOR, 'input[placeholder*="Last"]'),
            ]
            last_name_input = None
            for by, selector in last_name_selectors:
                try:
                    last_name_input = WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located((by, selector))
                    )
                    if last_name_input:
                        break
                except Exception:
                    continue

            if not last_name_input:
                self.logger.error("Could not find last name input")
                if self.enable_screenshots:
                    driver.save_screenshot(str(self.screenshots_dir / "ice_error_no_form.png"))
                return None

            last_name_input.clear()
            last_name_input.send_keys(self.defendant_last_name)
            time.sleep(0.5)

            # Fill in first name
            first_name_selectors = [
                (By.ID, "firstName"),
                (By.CSS_SELECTOR, 'input[formcontrolname="firstName"]'),
                (By.CSS_SELECTOR, 'input[name="firstName"]'),
                (By.CSS_SELECTOR, 'input[placeholder*="First"]'),
            ]
            for by, selector in first_name_selectors:
                try:
                    first_name_input = driver.find_element(by, selector)
                    first_name_input.clear()
                    first_name_input.send_keys(self.defendant_first_name)
                    break
                except Exception:
                    continue
            time.sleep(0.5)

            # Scroll down to reveal the bio search form
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 2)")
            time.sleep(1)

            # Select country of birth from dropdown (in the Bio section, not A-Number section)
            if self.country_of_birth:
                # The page has TWO country dropdowns - one for A-Number, one for Bio search
                # We need the second one (Bio search section)
                cob_selectors = [
                    (By.CSS_SELECTOR, 'b-search select'),
                    (By.CSS_SELECTOR, 'select[formcontrolname="country"]'),
                    (By.XPATH, '(//select[contains(@class,"form-control") or contains(@class,"form-select")])[last()]'),
                    (By.XPATH, '//b-search//select'),
                ]
                cob_selected = False
                for by, selector in cob_selectors:
                    try:
                        select_el = driver.find_element(by, selector)
                        Select(select_el).select_by_visible_text(self.country_of_birth)
                        self.logger.info(f"Selected country using: {selector}")
                        cob_selected = True
                        break
                    except Exception as e:
                        self.logger.debug(f"Country selector {selector} failed: {e}")
                        continue

                if not cob_selected:
                    # Fallback: try all select elements and pick the one in bio section
                    try:
                        selects = driver.find_elements(By.TAG_NAME, 'select')
                        for sel in selects:
                            try:
                                options = [o.text for o in sel.find_elements(By.TAG_NAME, 'option')]
                                if any(self.country_of_birth in o for o in options):
                                    Select(sel).select_by_visible_text(self.country_of_birth)
                                    self.logger.info("Selected country using fallback select scan")
                                    cob_selected = True
                                    break
                            except Exception:
                                continue
                    except Exception:
                        pass

                if not cob_selected:
                    self.logger.warning(f"Could not select country of birth: {self.country_of_birth}")

                time.sleep(0.5)

            # Fill optional DOB fields
            if self.dob_month:
                try:
                    el = driver.find_element(By.CSS_SELECTOR, 'select[formcontrolname="month"], #month')
                    Select(el).select_by_value(self.dob_month)
                except Exception:
                    pass
            if self.dob_day:
                try:
                    el = driver.find_element(By.CSS_SELECTOR, 'select[formcontrolname="day"], #day')
                    Select(el).select_by_value(self.dob_day)
                except Exception:
                    pass
            if self.dob_year:
                try:
                    el = driver.find_element(By.CSS_SELECTOR, 'select[formcontrolname="year"], #year, app-years select')
                    Select(el).select_by_visible_text(self.dob_year)
                except Exception:
                    pass

            if self.enable_screenshots:
                driver.save_screenshot(str(self.screenshots_dir / "ice_02_form_filled.png"))

            # Scroll to bottom to reveal search button and let reCAPTCHA fully initialize
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(3)

            # Click search button using JavaScript to avoid click intercept issues
            search_selectors = [
                (By.XPATH, '//button[contains(text(), "Search by Biographical")]'),
                (By.XPATH, '//b-search//button[contains(text(), "Search")]'),
                (By.CSS_SELECTOR, 'b-search button[type="submit"]'),
                (By.CSS_SELECTOR, 'b-search button'),
                (By.XPATH, '//button[contains(text(), "Search") and not(contains(text(), "A-Number"))]'),
            ]
            search_clicked = False
            for by, selector in search_selectors:
                try:
                    btn = driver.find_element(by, selector)
                    driver.execute_script("arguments[0].scrollIntoView(true);", btn)
                    time.sleep(0.5)
                    driver.execute_script("arguments[0].click();", btn)
                    search_clicked = True
                    self.logger.debug(f"Clicked search using: {selector}")
                    break
                except Exception:
                    continue

            if not search_clicked:
                self.logger.error("Could not click ICE search button")
                if self.enable_screenshots:
                    driver.save_screenshot(str(self.screenshots_dir / "ice_error_no_search_button.png"))
                return None

            # Wait for results
            time.sleep(8)

            if self.enable_screenshots:
                driver.save_screenshot(str(self.screenshots_dir / "ice_03_results.png"))

            # Parse results
            html = driver.page_source
            soup = BeautifulSoup(html, 'html.parser')
            page_text = soup.get_text().lower()

            # Check for internal error (reCAPTCHA failure)
            if 'internal error' in page_text:
                self.logger.warning("ICE locator: Internal Error (likely reCAPTCHA failure), retrying...")
                try:
                    # Full page reload to get fresh reCAPTCHA token
                    driver.get("https://locator.ice.gov/odls/#/search")
                    time.sleep(8)  # Long wait for reCAPTCHA v3 to build score

                    # Human-like mouse movements
                    actions = ActionChains(driver)
                    actions.move_by_offset(300, 200).pause(1)
                    actions.move_by_offset(50, 100).pause(0.5)
                    actions.perform()

                    # Re-fill the form with natural typing delays
                    for by, selector in last_name_selectors:
                        try:
                            last_name_input = WebDriverWait(driver, 5).until(
                                EC.presence_of_element_located((by, selector))
                            )
                            if last_name_input:
                                break
                        except Exception:
                            continue
                    if last_name_input:
                        last_name_input.click()
                        time.sleep(0.3)
                        last_name_input.clear()
                        for char in self.defendant_last_name:
                            last_name_input.send_keys(char)
                            time.sleep(0.05)
                        time.sleep(0.5)

                    for by, selector in first_name_selectors:
                        try:
                            fi = driver.find_element(by, selector)
                            fi.click()
                            time.sleep(0.3)
                            fi.clear()
                            for char in self.defendant_first_name:
                                fi.send_keys(char)
                                time.sleep(0.05)
                            break
                        except Exception:
                            continue
                    time.sleep(0.5)

                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 2)")
                    time.sleep(2)
                    if self.country_of_birth:
                        try:
                            sel = driver.find_element(By.CSS_SELECTOR, 'b-search select')
                            Select(sel).select_by_visible_text(self.country_of_birth)
                        except Exception:
                            pass
                    time.sleep(1)
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
                    time.sleep(5)

                    for by, selector in search_selectors:
                        try:
                            btn = driver.find_element(by, selector)
                            driver.execute_script("arguments[0].scrollIntoView(true);", btn)
                            time.sleep(0.5)
                            driver.execute_script("arguments[0].click();", btn)
                            break
                        except Exception:
                            continue
                    time.sleep(8)
                    if self.enable_screenshots:
                        driver.save_screenshot(str(self.screenshots_dir / "ice_04_retry_results.png"))

                    html = driver.page_source
                    soup = BeautifulSoup(html, 'html.parser')
                    page_text = soup.get_text().lower()
                    if 'internal error' in page_text:
                        self.logger.error("ICE locator: Internal Error persists after retry")
                        return None
                except Exception as retry_err:
                    self.logger.error(f"ICE retry failed: {retry_err}")
                    return None

            if 'no records found' in page_text or 'no results' in page_text or '0 results' in page_text:
                self.logger.info("ICE locator: No records found")
                return None

            result = self._parse_ice_results_selenium(soup, driver)
            return result

        except Exception as e:
            self.logger.error(f"Error checking ICE detainee locator: {e}")
            import traceback
            self.logger.debug(traceback.format_exc())
            if self.enable_screenshots and driver:
                try:
                    driver.save_screenshot(str(self.screenshots_dir / "ice_error_exception.png"))
                except Exception:
                    pass
            return None
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass

    def _parse_ice_results_selenium(self, soup: BeautifulSoup, driver) -> Optional[IceDetaineeStatus]:
        """Parse ICE detainee locator results page using Selenium driver"""
        from selenium.webdriver.common.by import By
        now = datetime.now().isoformat()

        # The ICE results page displays data in a "label : value" text format:
        #   RICARDO ULRICH DEUKER
        #   Country of Birth : Germany
        #   Status : In ICE Custody
        #   State: CA
        #   Current Detention Facility: CALIFORNIA CITY CORRECTIONS CENTER
        try:
            body_text = driver.find_element(By.TAG_NAME, 'body').text
        except Exception:
            self.logger.info("ICE locator: Could not get page text")
            return None

        if self.defendant_last_name.upper() not in body_text.upper():
            self.logger.info("ICE locator: Defendant name not found in results")
            return None

        lines = [l.strip() for l in body_text.split('\n') if l.strip()]

        # Debug: log the lines around the name for selector tuning
        self.logger.debug(f"ICE results page lines: {lines}")

        # Find the name line and extract fields from surrounding lines
        full_name = ""
        country = self.country_of_birth
        status = ""
        state = ""
        facility = ""

        for i, line in enumerate(lines):
            # The name appears as a standalone line in ALL CAPS
            if self.defendant_last_name.upper() in line.upper() and ':' not in line and 'search' not in line.lower():
                full_name = line.strip()
                continue

            # Parse "Label : Value" or "Label: Value" or "Label :Value" lines
            # Handle spaces around colon: "Status : In ICE Custody" or "Status: In ICE Custody"
            line_lower = line.lower().strip()
            if 'country of birth' in line_lower and ':' in line:
                country = line.split(':', 1)[-1].strip()
            elif re.match(r'^status\s*:', line_lower):
                status = line.split(':', 1)[-1].strip()
            elif re.match(r'^state\s*:', line_lower):
                state = line.split(':', 1)[-1].strip()
            elif 'detention facility' in line_lower and ':' in line:
                facility = line.split(':', 1)[-1].strip()

        if full_name:
            self.logger.info(f"ICE: Found {full_name} - Status: {status}, State: {state}, Facility: {facility}")
            return IceDetaineeStatus(
                full_name=full_name,
                country_of_birth=country,
                status=status,
                state=state,
                detention_facility=facility,
                last_checked=now,
                first_seen=now
            )

        self.logger.info("ICE locator: Could not parse results")
        return None

    def _detect_ice_changes(self, new_status: Optional[IceDetaineeStatus]) -> List[str]:
        """
        Compare new ICE status vs stored status and return list of changes.
        Uses failure counter to avoid false 'removed' alerts on transient errors.
        """
        changes = []

        if new_status is None:
            if self.ice_status is not None:
                self.ice_check_failures += 1
                if self.ice_check_failures >= 3:
                    changes.append("REMOVED from ICE detainee locator (not found after 3 consecutive checks)")
                else:
                    self.logger.info(f"ICE: Person not found (failure {self.ice_check_failures}/3, not alerting yet)")
            return changes

        # Reset failure counter on successful check
        self.ice_check_failures = 0

        if self.ice_status is None:
            # Newly found
            changes.append(f"NEWLY FOUND in ICE detainee locator: {new_status.status}, State: {new_status.state}, Facility: {new_status.detention_facility}")
            # Preserve first_seen time
            new_status.first_seen = datetime.now().isoformat()
        else:
            # Preserve original first_seen
            new_status.first_seen = self.ice_status.first_seen

            if new_status.status != self.ice_status.status:
                changes.append(f"Status changed: {self.ice_status.status} -> {new_status.status}")
            if new_status.state != self.ice_status.state:
                changes.append(f"State changed: {self.ice_status.state} -> {new_status.state}")
            if new_status.detention_facility != self.ice_status.detention_facility:
                changes.append(f"Facility changed: {self.ice_status.detention_facility} -> {new_status.detention_facility}")

        return changes

    def _send_ice_notification(self, changes: List[str], current_status: Optional[IceDetaineeStatus]):
        """Send notification about ICE detainee status changes"""
        if not changes:
            return

        # Build SMS message
        message_parts = [f"🚨 ICE Alert: {self.defendant_first_name} {self.defendant_last_name}"]
        for change in changes:
            message_parts.append(f"  • {change}")
        if current_status:
            message_parts.append(f"\nCurrent: {current_status.status}")
            message_parts.append(f"State: {current_status.state}")
            message_parts.append(f"Facility: {current_status.detention_facility}")
        message = "\n".join(message_parts)

        # Send SMS via Twilio
        if self.notification_sms:
            try:
                from twilio.rest import Client
                if all([self.twilio_account_sid, self.twilio_auth_token, self.twilio_phone_number]):
                    client = Client(self.twilio_account_sid, self.twilio_auth_token)
                    sms_message = client.messages.create(
                        body=message,
                        from_=self.twilio_phone_number,
                        to=self.notification_sms
                    )
                    self.logger.info(f"📱 ICE SMS sent to {self.notification_sms} (SID: {sms_message.sid})")
            except Exception as e:
                self.logger.error(f"❌ Error sending ICE SMS: {e}")

        # Send Email
        if self.notification_email:
            try:
                import smtplib
                from email.mime.text import MIMEText
                from email.mime.multipart import MIMEMultipart

                if all([self.smtp_server, self.smtp_username, self.smtp_password]):
                    msg = MIMEMultipart('alternative')
                    msg['Subject'] = f"🚨 ICE Alert: {self.defendant_first_name} {self.defendant_last_name}"
                    msg['From'] = self.smtp_from_address
                    msg['To'] = self.notification_email

                    text_body = message

                    html_body = f"""
                    <html>
                      <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                        <div style="background-color: #e65100; color: white; padding: 15px; border-radius: 5px 5px 0 0;">
                          <h2 style="margin: 0;">🚨 ICE Detainee Alert</h2>
                          <p style="margin: 5px 0 0 0; font-size: 16px;">{self.defendant_first_name} {self.defendant_last_name}</p>
                        </div>
                        <div style="padding: 20px; background-color: #f5f5f5; border-radius: 0 0 5px 5px;">
                          <div style="background-color: white; padding: 15px; margin-bottom: 15px; border-radius: 5px; border-left: 4px solid #e65100;">
                            <h3 style="margin: 0 0 10px 0; color: #e65100;">Changes Detected</h3>
                            <ul style="margin: 5px 0; padding-left: 20px;">
                    """
                    for change in changes:
                        html_body += f"<li><strong>{change}</strong></li>"

                    html_body += """
                            </ul>
                          </div>
                    """

                    if current_status:
                        html_body += f"""
                          <div style="background-color: white; padding: 15px; border-radius: 5px; border-left: 4px solid #2196f3;">
                            <h3 style="margin: 0 0 10px 0; color: #2196f3;">Current Status</h3>
                            <table style="width: 100%; border-collapse: collapse;">
                              <tr><td style="padding: 8px; font-weight: bold;">Name</td><td style="padding: 8px;">{current_status.full_name}</td></tr>
                              <tr><td style="padding: 8px; font-weight: bold;">Status</td><td style="padding: 8px;">{current_status.status}</td></tr>
                              <tr><td style="padding: 8px; font-weight: bold;">State</td><td style="padding: 8px;">{current_status.state}</td></tr>
                              <tr><td style="padding: 8px; font-weight: bold;">Facility</td><td style="padding: 8px;">{current_status.detention_facility}</td></tr>
                              <tr><td style="padding: 8px; font-weight: bold;">Country of Birth</td><td style="padding: 8px;">{current_status.country_of_birth}</td></tr>
                              <tr><td style="padding: 8px; font-weight: bold;">First Seen</td><td style="padding: 8px;">{current_status.first_seen}</td></tr>
                              <tr><td style="padding: 8px; font-weight: bold;">Last Checked</td><td style="padding: 8px;">{current_status.last_checked}</td></tr>
                            </table>
                          </div>
                        """

                    html_body += """
                        </div>
                        <div style="text-align: center; padding: 15px; color: #999; font-size: 12px;">
                          <p>ICE Detainee Locator Monitor</p>
                        </div>
                      </body>
                    </html>
                    """

                    part1 = MIMEText(text_body, 'plain')
                    part2 = MIMEText(html_body, 'html')
                    msg.attach(part1)
                    msg.attach(part2)

                    recipients = [email.strip() for email in self.notification_email.split(',')]
                    with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                        server.starttls()
                        server.login(self.smtp_username, self.smtp_password)
                        server.sendmail(self.smtp_from_address, recipients, msg.as_string())

                    self.logger.info(f"📧 ICE email sent to {', '.join(recipients)}")
            except Exception as e:
                self.logger.error(f"❌ Error sending ICE email: {e}")

    def check_all_cases(self) -> Dict[str, any]:
        """
        Check all cases from the search results

        Returns:
            Dict with statistics and new entries
        """
        results = {
            'total_cases': 0,
            'total_charges': 0,
            'total_dockets': 0,
            'total_documents': 0,
            'new_charges': [],
            'new_dockets': [],
            'new_documents_count': 0,
            'total_documents_seen': 0,
            'case_summaries': [],
            'ice_changes': [],
            'ice_status': None
        }

        try:
            # Extract case links (this method now handles page navigation)
            cases = self._extract_case_links()
            # #region agent log
            with open('/home/sfeltner/Projects/deuker-monitor/.cursor/debug.log', 'a') as f:
                import json as json_module
                f.write(json_module.dumps({'sessionId':'debug-session','runId':'run1','hypothesisId':'D','location':'deuker-monitor.py:1396','message':'Cases extracted before filtering','data':{'total_cases':len(cases),'case_numbers':[c['case_number'] for c in cases],'filter_case_number':self.filter_case_number},'timestamp':int(time.time()*1000)})+'\n')
            # #endregion

            # Filter to specific case if requested
            if self.filter_case_number:
                self.logger.info(f"Filtering to case: {self.filter_case_number}")
                # #region agent log
                with open('/home/sfeltner/Projects/deuker-monitor/.cursor/debug.log', 'a') as f:
                    import json as json_module
                    f.write(json_module.dumps({'sessionId':'debug-session','runId':'run1','hypothesisId':'A','location':'deuker-monitor.py:1401','message':'Before filtering comparison','data':{'filter_case_number':self.filter_case_number,'extracted_cases':[{'case_number':c['case_number'],'matches':c['case_number']==self.filter_case_number} for c in cases]},'timestamp':int(time.time()*1000)})+'\n')
                # #endregion
                cases = [c for c in cases if c['case_number'] == self.filter_case_number]
                # #region agent log
                with open('/home/sfeltner/Projects/deuker-monitor/.cursor/debug.log', 'a') as f:
                    import json as json_module
                    f.write(json_module.dumps({'sessionId':'debug-session','runId':'run1','hypothesisId':'A','location':'deuker-monitor.py:1401','message':'After filtering comparison','data':{'filter_case_number':self.filter_case_number,'filtered_count':len(cases),'filtered_cases':[c['case_number'] for c in cases]},'timestamp':int(time.time()*1000)})+'\n')
                # #endregion

                if not cases:
                    self.logger.warning(f"Case {self.filter_case_number} not found for {self.defendant_first_name} {self.defendant_last_name}")
                    # #region agent log
                    with open('/home/sfeltner/Projects/deuker-monitor/.cursor/debug.log', 'a') as f:
                        import json as json_module
                        f.write(json_module.dumps({'sessionId':'debug-session','runId':'run1','hypothesisId':'A','location':'deuker-monitor.py:1404','message':'Case not found after filtering','data':{'filter_case_number':self.filter_case_number},'timestamp':int(time.time()*1000)})+'\n')
                    # #endregion
                    return results

                self.logger.info(f"Found matching case: {self.filter_case_number}")

            results['total_cases'] = len(cases)

            self.logger.info(f"Found {len(cases)} case(s) to monitor")

            # Process each case
            for case_index, case_data in enumerate(cases):
                case_number = case_data['case_number']
                case_url = case_data['case_url']

                self.logger.info(f"Checking case: {case_number} ({case_index + 1}/{len(cases)})")

                # If this is not the first case, re-perform the search to get back to case list
                # This is more reliable than trying to navigate back
                if case_index > 0:
                    self.logger.info("Re-performing search to access case list...")
                    self._take_screenshot(f"15-re-performing-search-case-{case_index}")

                    # Perform the full defendant search
                    if not self._perform_defendant_search():
                        self.logger.error("Failed to re-perform defendant search")
                        continue

                    # Click on defendant result to open case list popup
                    defendant_name = f"{self.defendant_last_name.upper()}, {self.defendant_first_name.upper()}"
                    defendant_selectors = [
                        f'text={defendant_name}',
                        f':text("{self.defendant_last_name}")',
                        '[class*="defendant"]',
                        f'div:has-text("{self.defendant_last_name.upper()}")'
                    ]

                    clicked_defendant = False
                    for selector in defendant_selectors:
                        try:
                            self.logger.debug(f"Trying to click defendant with: {selector}")
                            self.page.click(selector, timeout=5000)
                            self.logger.info(f"✓ Opened case list using: {selector}")
                            self._take_screenshot(f"16-after-reclick-defendant-case-{case_index}")
                            clicked_defendant = True
                            time.sleep(2)
                            break
                        except Exception as click_err:
                            self.logger.debug(f"Selector {selector} failed: {click_err}")
                            continue

                    if not clicked_defendant:
                        self.logger.error("Could not open case list")
                        self._take_screenshot(f"16-error-reclick-defendant-case-{case_index}")
                        continue

                    # Verify the case list is visible
                    html = self.page.content()
                    soup = BeautifulSoup(html, 'html.parser')
                    table = soup.find('table')
                    if table:
                        self.logger.debug("✓ Case list table is now visible")
                    else:
                        self.logger.warning("Case list table NOT visible!")
                        continue

                # Fetch charges and docket entries
                charges, docket_entries, new_documents_this_case, total_documents_this_case = self._fetch_case_details(case_url, case_number)

                # Update case info
                self.case_info[case_number] = CaseInfo(
                    case_number=case_number,
                    filed_date=case_data['filed_date'],
                    closed_date=case_data['closed_date'],
                    first_charge=case_data['first_charge'],
                    balance_due=case_data['balance_due'],
                    charge_count=len(charges),
                    docket_count=len(docket_entries),
                    last_checked=datetime.now().isoformat()
                )

                results['total_charges'] += len(charges)
                results['total_dockets'] += len(docket_entries)
                results['new_documents_count'] += new_documents_this_case
                results['total_documents_seen'] += total_documents_this_case

                # Check for new charges
                new_charges_this_case = []
                for charge in charges:
                    charge_hash = self._generate_charge_hash(
                        charge.case_number,
                        charge.sequence_number,
                        charge.charge_description,
                        charge.charge_type
                    )

                    if charge_hash not in self.seen_charges:
                        new_charges_this_case.append(charge)
                        results['new_charges'].append(charge)
                        self.seen_charges.add(charge_hash)
                        self.logger.info(f"  🆕 NEW CHARGE: Seq {charge.sequence_number} - {charge.charge_description}")

                # Check for new dockets
                new_dockets_this_case = []
                for docket in docket_entries:
                    docket_hash = self._generate_docket_hash(
                        docket.case_number,
                        docket.din,
                        docket.date,
                        docket.docket_description
                    )

                    if docket_hash not in self.seen_dockets:
                        new_dockets_this_case.append(docket)
                        results['new_dockets'].append(docket)
                        self.seen_dockets.add(docket_hash)
                        self.logger.info(f"  🆕 NEW DOCKET: Din {docket.din} - {docket.docket_description[:50]}")

                # Add case summary
                results['case_summaries'].append({
                    'case_number': case_number,
                    'charge_count': len(charges),
                    'docket_count': len(docket_entries),
                    'documents_count': new_documents_this_case,
                    'new_charges_count': len(new_charges_this_case),
                    'new_dockets_count': len(new_dockets_this_case),
                    'new_documents_count': new_documents_this_case,
                    'first_charge': case_data['first_charge']
                })

                # Be polite - delay between cases
                if case_index < len(cases) - 1:
                    time.sleep(1)
            
            # Save state
            self._save_state()

            # ICE detainee locator check
            if self.ice_monitoring:
                try:
                    new_ice_status = self._check_ice_status()
                    ice_changes = self._detect_ice_changes(new_ice_status)
                    if new_ice_status is not None:
                        self.ice_status = new_ice_status
                    elif self.ice_check_failures >= 3:
                        self.ice_status = None
                    results['ice_changes'] = ice_changes
                    results['ice_status'] = self.ice_status
                    self._save_state()
                except Exception as ice_err:
                    self.logger.error(f"Error during ICE check: {ice_err}")
                    import traceback
                    self.logger.debug(traceback.format_exc())

        except Exception as e:
            self.logger.error(f"Error checking cases: {e}")
            import traceback
            self.logger.debug(traceback.format_exc())

        return results
    
    def _send_notification(self, new_charges: List[Charge], new_dockets: List[DocketEntry]):
        """
        Send notifications about new charges and dockets via SMS and/or email

        Configuration in JSON file for Twilio SMS:
        - twilio_account_sid: Your Twilio Account SID
        - twilio_auth_token: Your Twilio Auth Token
        - twilio_phone_number: Your Twilio phone number (e.g., +12345678900)

        Configuration in JSON file for Email:
        - smtp_server: SMTP server (e.g., smtp.gmail.com)
        - smtp_port: SMTP port (default: 587)
        - smtp_username: Your email username
        - smtp_password: Your email password or app password
        - smtp_from_address: From address (optional, defaults to smtp_username)
        """
        # Build notification message
        message_parts = []
        message_parts.append(f"🚨 Court Alert: {self.defendant_first_name} {self.defendant_last_name}")

        if new_charges:
            message_parts.append(f"\n⚖️  {len(new_charges)} NEW CHARGE(S):")
            for charge in new_charges[:3]:  # Limit to first 3 for SMS
                message_parts.append(f"  • {charge.charge_description}")
            if len(new_charges) > 3:
                message_parts.append(f"  • ...and {len(new_charges) - 3} more")

        if new_dockets:
            message_parts.append(f"\n📄 {len(new_dockets)} NEW DOCKET(S):")
            for docket in new_dockets[:3]:  # Limit to first 3 for SMS
                desc = docket.docket_description[:50] + "..." if len(docket.docket_description) > 50 else docket.docket_description
                message_parts.append(f"  • Din {docket.din}: {desc}")
            if len(new_dockets) > 3:
                message_parts.append(f"  • ...and {len(new_dockets) - 3} more")

        message = "\n".join(message_parts)

        # Send SMS via Twilio
        if self.notification_sms:
            try:
                from twilio.rest import Client

                if not all([self.twilio_account_sid, self.twilio_auth_token, self.twilio_phone_number]):
                    self.logger.warning("⚠️  Twilio credentials not found in configuration")
                    self.logger.warning("   Set twilio_account_sid, twilio_auth_token, and twilio_phone_number in config file")
                else:
                    client = Client(self.twilio_account_sid, self.twilio_auth_token)

                    sms_message = client.messages.create(
                        body=message,
                        from_=self.twilio_phone_number,
                        to=self.notification_sms
                    )

                    self.logger.info(f"📱 SMS sent to {self.notification_sms} (SID: {sms_message.sid})")

            except ImportError:
                self.logger.error("❌ Twilio library not installed. Run: pip install twilio")
            except Exception as e:
                self.logger.error(f"❌ Error sending SMS: {e}")

        # Send Email
        if self.notification_email:
            try:
                import smtplib
                from email.mime.text import MIMEText
                from email.mime.multipart import MIMEMultipart

                if not all([self.smtp_server, self.smtp_username, self.smtp_password]):
                    self.logger.warning("⚠️  Email credentials not found in configuration")
                    self.logger.warning("   Set smtp_server, smtp_username, and smtp_password in config file")
                else:
                    # Create email message
                    msg = MIMEMultipart('alternative')
                    msg['Subject'] = f"🚨 Court Alert: {self.defendant_first_name} {self.defendant_last_name}"
                    msg['From'] = self.smtp_from_address
                    msg['To'] = self.notification_email

                    # Create plain text version
                    text_body = message

                    # Create HTML version
                    html_body = f"""
                    <html>
                      <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                        <div style="background-color: #f44336; color: white; padding: 15px; border-radius: 5px 5px 0 0;">
                          <h2 style="margin: 0;">🚨 Court Alert</h2>
                          <p style="margin: 5px 0 0 0; font-size: 16px;">{self.defendant_first_name} {self.defendant_last_name}</p>
                        </div>
                        <div style="padding: 20px; background-color: #f5f5f5; border-radius: 0 0 5px 5px;">
                    """

                    if new_charges:
                        html_body += f"""
                          <div style="background-color: white; padding: 15px; margin-bottom: 15px; border-radius: 5px; border-left: 4px solid #ff9800;">
                            <h3 style="margin: 0 0 10px 0; color: #ff9800;">⚖️  {len(new_charges)} NEW CHARGE(S)</h3>
                        """
                        # Group charges by case
                        charges_by_case = {}
                        for charge in new_charges:
                            if charge.case_number not in charges_by_case:
                                charges_by_case[charge.case_number] = []
                            charges_by_case[charge.case_number].append(charge)

                        for case_number, charges in charges_by_case.items():
                            html_body += f"""
                            <div style="margin-bottom: 15px;">
                              <h4 style="margin: 10px 0 5px 0; color: #666; font-size: 14px;">📋 Case: {case_number}</h4>
                              <ul style="margin: 5px 0; padding-left: 20px;">
                            """
                            for charge in charges:
                                html_body += f"<li><strong>{charge.charge_description}</strong> ({charge.charge_type})</li>"
                            html_body += """
                              </ul>
                            </div>
                            """
                        html_body += """
                          </div>
                        """

                    if new_dockets:
                        html_body += f"""
                          <div style="background-color: white; padding: 15px; border-radius: 5px; border-left: 4px solid #2196f3;">
                            <h3 style="margin: 0 0 10px 0; color: #2196f3;">📄 {len(new_dockets)} NEW DOCKET ENTRY/ENTRIES</h3>
                        """
                        # Group dockets by case
                        dockets_by_case = {}
                        for docket in new_dockets:
                            if docket.case_number not in dockets_by_case:
                                dockets_by_case[docket.case_number] = []
                            dockets_by_case[docket.case_number].append(docket)

                        for case_number, dockets in dockets_by_case.items():
                            html_body += f"""
                            <div style="margin-bottom: 15px;">
                              <h4 style="margin: 10px 0 5px 0; color: #666; font-size: 14px;">📋 Case: {case_number}</h4>
                              <table style="width: 100%; border-collapse: collapse;">
                                <thead>
                                  <tr style="background-color: #f5f5f5;">
                                    <th style="padding: 8px; text-align: left; border-bottom: 2px solid #ddd;">Din</th>
                                    <th style="padding: 8px; text-align: left; border-bottom: 2px solid #ddd;">Date</th>
                                    <th style="padding: 8px; text-align: left; border-bottom: 2px solid #ddd;">Description</th>
                                  </tr>
                                </thead>
                                <tbody>
                            """
                            for docket in dockets:
                                html_body += f"""
                                  <tr style="border-bottom: 1px solid #eee;">
                                    <td style="padding: 8px;">{docket.din}</td>
                                    <td style="padding: 8px;">{docket.date}</td>
                                    <td style="padding: 8px;">{docket.docket_description}</td>
                                  </tr>
                                """
                            html_body += """
                                </tbody>
                              </table>
                            </div>
                            """
                        html_body += """
                          </div>
                        """

                    html_body += """
                        </div>
                        <div style="text-align: center; padding: 15px; color: #999; font-size: 12px;">
                          <p>Miami-Dade Court Docket Monitor</p>
                        </div>
                      </body>
                    </html>
                    """

                    # Attach both versions
                    part1 = MIMEText(text_body, 'plain')
                    part2 = MIMEText(html_body, 'html')
                    msg.attach(part1)
                    msg.attach(part2)

                    # Send email (supports comma-separated multiple recipients)
                    recipients = [email.strip() for email in self.notification_email.split(',')]
                    with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                        server.starttls()
                        server.login(self.smtp_username, self.smtp_password)
                        server.sendmail(self.smtp_from_address, recipients, msg.as_string())

                    self.logger.info(f"📧 Email sent to {', '.join(recipients)}")

            except ImportError:
                self.logger.error("❌ Email libraries not available (should be built-in)")
            except Exception as e:
                self.logger.error(f"❌ Error sending email: {e}")

        if not self.notification_sms and not self.notification_email:
            self.logger.info(f"📧 Notification: {len(new_charges)} new charges, {len(new_dockets)} new dockets (no recipients configured)")

    def on_new_entries(self, results: Dict):
        """Handle new charges and docket entries"""
        new_charges = results['new_charges']
        new_dockets = results['new_dockets']

        if not new_charges and not new_dockets:
            self.logger.info("✓ No new charges or docket entries")
            return

        # Display new charges
        if new_charges:
            print("\n" + "="*80)
            print(f"⚖️  FOUND {len(new_charges)} NEW CHARGE(S)!")
            print("="*80)

            # Group by case
            by_case = {}
            for charge in new_charges:
                if charge.case_number not in by_case:
                    by_case[charge.case_number] = []
                by_case[charge.case_number].append(charge)

            for case_number, charges in by_case.items():
                print(f"\n📋 Case: {case_number} ({len(charges)} new charge(s))")
                print("-" * 80)
                for charge in charges:
                    print(f"  Seq #: {charge.sequence_number}")
                    print(f"  Charge: {charge.charge_description}")
                    print(f"  Type: {charge.charge_type}")
                    print(f"  Disposition: {charge.disposition}")
                    print(f"  Found at: {charge.timestamp_found}")
                    print()

            print("="*80)

        # Display new dockets
        if new_dockets:
            print("\n" + "="*80)
            print(f"📄 FOUND {len(new_dockets)} NEW DOCKET ENTRY/ENTRIES!")
            print("="*80)

            # Group by case
            by_case = {}
            for docket in new_dockets:
                if docket.case_number not in by_case:
                    by_case[docket.case_number] = []
                by_case[docket.case_number].append(docket)

            for case_number, dockets in by_case.items():
                print(f"\n📋 Case: {case_number} ({len(dockets)} new docket entry/entries)")
                print("-" * 80)
                for docket in dockets:
                    print(f"  Din: {docket.din}")
                    print(f"  Date: {docket.date}")
                    print(f"  Docket: {docket.docket_description}")
                    print(f"  Book/Page: {docket.book_page}")
                    print(f"  Found at: {docket.timestamp_found}")
                    print()

            print("="*80)

        # Save to file
        self._save_new_entries_to_file(new_charges, new_dockets)

        # Send notifications (stub)
        self._send_notification(new_charges, new_dockets)

        # Handle ICE changes
        ice_changes = results.get('ice_changes', [])
        if ice_changes:
            print("\n" + "="*80)
            print("🚨 ICE DETAINEE STATUS CHANGES DETECTED!")
            print("="*80)
            for change in ice_changes:
                print(f"  • {change}")
            ice_status = results.get('ice_status')
            if ice_status:
                print(f"\n  Current Status: {ice_status.status}")
                print(f"  State: {ice_status.state}")
                print(f"  Facility: {ice_status.detention_facility}")
            print("="*80)
            self._send_ice_notification(ice_changes, ice_status)

    def _save_new_entries_to_file(self, charges: List[Charge], dockets: List[DocketEntry]):
        """Save new charges and dockets to timestamped JSON file"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        data = {
            'timestamp': timestamp,
            'new_charges': [asdict(c) for c in charges],
            'new_dockets': [asdict(d) for d in dockets]
        }

        filename = f"new_entries_{timestamp}.json"
        try:
            with open(filename, 'w') as f:
                json.dump(data, f, indent=2)
            self.logger.info(f"💾 Saved to {filename}")
            print(f"💾 Details saved to: {filename}")
        except Exception as e:
            self.logger.error(f"Error saving entries: {e}")
    
    def print_summary(self, results: Dict):
        """Print summary of current state"""
        # First show Per-Case Breakdown
        if results['case_summaries']:
            print("\n" + "="*80)
            print("📋 PER-CASE BREAKDOWN")
            print("="*80)
            for summary in results['case_summaries']:
                charge_indicator = f" ({summary['new_charges_count']} NEW!)" if summary.get('new_charges_count', 0) > 0 else ""
                docket_indicator = f" ({summary['new_dockets_count']} NEW!)" if summary.get('new_dockets_count', 0) > 0 else ""
                document_indicator = f" ({summary['new_documents_count']} NEW!)" if summary.get('new_documents_count', 0) > 0 else ""
                print(f"  {summary['case_number']}:")
                print(f"    Charges: {summary['charge_count']}{charge_indicator}")
                print(f"    Dockets: {summary['docket_count']}{docket_indicator}")
                print(f"    Documents Found: {summary['documents_count']}{document_indicator}")
                print(f"    First Charge: {summary['first_charge']}")
                print()
            print("="*80)

        # Then show Case Summary at the end
        print("\n" + "="*80)
        print("📊 CASE SUMMARY")
        print("="*80)
        print(f"Total Cases Monitored: {results['total_cases']}")
        print(f"Total Charges: {results['total_charges']}")
        print(f"Total Docket Entries: {results['total_dockets']}")
        print(f"Total Documents Seen: {results['total_documents_seen']}")
        print(f"New Charges This Check: {len(results['new_charges'])}")
        print(f"New Dockets This Check: {len(results['new_dockets'])}")
        print(f"New Documents This Check: {results['new_documents_count']}")
        print("="*80)

        # ICE Detainee Status
        if self.ice_monitoring:
            print("\n" + "="*80)
            print("🔒 ICE DETAINEE STATUS")
            print("="*80)
            ice_status = results.get('ice_status') or self.ice_status
            if ice_status:
                print(f"  Name: {ice_status.full_name}")
                print(f"  Status: {ice_status.status}")
                print(f"  State: {ice_status.state}")
                print(f"  Facility: {ice_status.detention_facility}")
                print(f"  Country of Birth: {ice_status.country_of_birth}")
                print(f"  First Seen: {ice_status.first_seen}")
                print(f"  Last Checked: {ice_status.last_checked}")
            else:
                print("  Not found in ICE detainee locator")
            print("="*80)
    
    def run(self):
        """Run the monitoring loop"""
        self.logger.info("="*60)
        self.logger.info("🚀 Starting Miami-Dade Docket Monitor")
        self.logger.info("="*60)
        self.logger.info(f"⏱️  Poll interval: {self.poll_interval} seconds ({self.poll_interval // 60} minutes)")
        self.logger.info(f"👤 Monitoring defendant: {self.defendant_first_name} {self.defendant_last_name} ({self.defendant_sex})")
        if self.ice_monitoring:
            self.logger.info(f"🔒 ICE detainee monitoring: ENABLED (Country: {self.country_of_birth})")

        try:
            # Initialize browser
            self._init_browser()

            iteration = 0
            while True:
                iteration += 1
                print("\n" + "="*80)
                print(f"Check #{iteration} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                print("="*80)

                results = self.check_all_cases()

                self.on_new_entries(results)
                self.print_summary(results)

                next_time = datetime.fromtimestamp(
                    datetime.now().timestamp() + self.poll_interval
                ).strftime('%Y-%m-%d %H:%M:%S')
                print(f"\n⏰ Next check at: {next_time}")
                self.logger.info(f"Sleeping for {self.poll_interval} seconds...")
                time.sleep(self.poll_interval)

        except KeyboardInterrupt:
            print("\n\n🛑 Monitor stopped by user")
            self.logger.info("Monitor stopped by user")
        except Exception as e:
            self.logger.error(f"❌ Monitor error: {e}")
            raise
        finally:
            # Clean up browser
            self._close_browser()


def load_monitor_config(config_file, args):
    """Load configuration from a config file and return monitor parameters"""
    defendant_first_name = args.first
    defendant_last_name = args.last
    defendant_sex = args.sex
    poll_interval = args.interval
    data_file = args.data_file
    notification_sms = ""
    notification_email = ""
    download_documents = args.download_documents if hasattr(args, 'download_documents') else True
    documents_dir = args.documents_dir if hasattr(args, 'documents_dir') else "court_documents"
    filter_case_number = args.case if hasattr(args, 'case') else ""
    enable_screenshots = args.screenshots if hasattr(args, 'screenshots') else False

    # SMTP configuration
    smtp_server = ""
    smtp_port = 587
    smtp_username = ""
    smtp_password = ""
    smtp_from_address = ""

    # Twilio configuration
    twilio_account_sid = ""
    twilio_auth_token = ""
    twilio_phone_number = ""

    # ICE detainee locator (defaults, overridden by config file)
    ice_monitoring = False
    country_of_birth = ""
    dob_month = ""
    dob_day = ""
    dob_year = ""
    # #region agent log
    with open('/home/sfeltner/Projects/deuker-monitor/.cursor/debug.log', 'a') as f:
        import json as json_module
        f.write(json_module.dumps({'sessionId':'debug-session','runId':'post-fix','hypothesisId':'E','location':'deuker-monitor.py:2007','message':'In load_monitor_config - args.case value','data':{'args_case':getattr(args,'case','NOT_SET'),'hasattr_case':hasattr(args,'case'),'filter_case_number_initial':filter_case_number},'timestamp':int(time.time()*1000)})+'\n')
    # #endregion
    print(f"🔍 DEBUG: load_monitor_config - args.case = {getattr(args, 'case', 'NOT_SET')}, filter_case_number = {filter_case_number}")

    try:
        with open(config_file, 'r') as f:
            config = json.load(f)
            defendant_first_name = config.get('defendant_first_name', defendant_first_name)
            defendant_last_name = config.get('defendant_last_name', defendant_last_name)
            defendant_sex = config.get('defendant_sex', defendant_sex)
            poll_interval = config.get('poll_interval', poll_interval)
            data_file = config.get('data_file', data_file)
            notification_sms = config.get('notification_sms', notification_sms)
            notification_email = config.get('notification_email', notification_email)
            download_documents = config.get('download_documents', download_documents)
            documents_dir = config.get('documents_dir', documents_dir)

            # SMTP configuration
            smtp_server = config.get('smtp_server', smtp_server)
            smtp_port = config.get('smtp_port', smtp_port)
            smtp_username = config.get('smtp_username', smtp_username)
            smtp_password = config.get('smtp_password', smtp_password)
            smtp_from_address = config.get('smtp_from_address', smtp_from_address)

            # Twilio configuration
            twilio_account_sid = config.get('twilio_account_sid', twilio_account_sid)
            twilio_auth_token = config.get('twilio_auth_token', twilio_auth_token)
            twilio_phone_number = config.get('twilio_phone_number', twilio_phone_number)

            # ICE detainee locator configuration
            ice_monitoring = config.get('ice_monitoring', False)
            country_of_birth = config.get('country_of_birth', '')
            dob_month = config.get('date_of_birth_month', '')
            dob_day = config.get('date_of_birth_day', '')
            dob_year = config.get('date_of_birth_year', '')

            if ice_monitoring and not country_of_birth:
                print(f"⚠️  Warning: ice_monitoring is enabled but country_of_birth is not set in '{config_file}'")

            # Command-line --case flag overrides config file
            if not filter_case_number:
                filter_case_number = config.get('filter_case_number', filter_case_number)
            # #region agent log
            with open('/home/sfeltner/Projects/deuker-monitor/.cursor/debug.log', 'a') as f:
                import json as json_module
                f.write(json_module.dumps({'sessionId':'debug-session','runId':'post-fix','hypothesisId':'E','location':'deuker-monitor.py:2029','message':'After config file load - filter_case_number','data':{'filter_case_number':filter_case_number,'config_has_filter':config.get('filter_case_number','NOT_IN_CONFIG')},'timestamp':int(time.time()*1000)})+'\n')
            # #endregion
            print(f"🔍 DEBUG: After config load - filter_case_number = {filter_case_number}, config has filter = {config.get('filter_case_number', 'NOT_IN_CONFIG')}")
    except FileNotFoundError:
        print(f"❌ Error: Config file '{config_file}' not found")
        return None
    except json.JSONDecodeError as e:
        print(f"❌ Error parsing config JSON in '{config_file}': {e}")
        return None

    if not defendant_first_name or not defendant_last_name:
        print(f"❌ Error: Defendant first and last name required in '{config_file}'")
        return None

    # Auto-generate data file name based on defendant if using default
    if data_file == 'docket_monitor_data.json':
        safe_first = defendant_first_name.lower().replace(' ', '_')
        safe_last = defendant_last_name.lower().replace(' ', '_')
        data_file = f"docket_monitor_{safe_last}_{safe_first}.json"

    return {
        'defendant_first_name': defendant_first_name,
        'defendant_last_name': defendant_last_name,
        'defendant_sex': defendant_sex,
        'poll_interval': poll_interval,
        'data_file': data_file,
        'skip_state': args.all,
        'notification_sms': notification_sms,
        'notification_email': notification_email,
        'download_documents': download_documents,
        'documents_dir': documents_dir,
        'filter_case_number': filter_case_number,
        'enable_screenshots': enable_screenshots,
        'smtp_server': smtp_server,
        'smtp_port': smtp_port,
        'smtp_username': smtp_username,
        'smtp_password': smtp_password,
        'smtp_from_address': smtp_from_address,
        'twilio_account_sid': twilio_account_sid,
        'twilio_auth_token': twilio_auth_token,
        'twilio_phone_number': twilio_phone_number,
        'ice_monitoring': ice_monitoring,
        'country_of_birth': country_of_birth,
        'dob_month': dob_month,
        'dob_day': dob_day,
        'dob_year': dob_year
    }


def main():
    parser = argparse.ArgumentParser(
        description='Monitor Miami-Dade court dockets for new entries',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Example usage:
  # Monitor with 10-minute interval
  python3 deuker-monitor.py --first Ricardo --last Deuker --sex Male -i 600

  # Run once to see current status
  python3 deuker-monitor.py --first Ricardo --last Deuker --once

  # Monitor only a specific case
  python3 deuker-monitor.py -c config.json --case F-25-024652 --once
  python3 deuker-monitor.py -c config.json --case F25024652 --once

  # Get all data without affecting tracking state (--all implies --once)
  python3 deuker-monitor.py -c config.json --all

  # Monitor multiple defendants at once
  python3 deuker-monitor.py -c ricardo.json -c sina.json --once

  # Use config file (recommended)
  python3 deuker-monitor.py -c config.json -i 300

Config file format (config.json):
{
  "defendant_first_name": "Ricardo",
  "defendant_last_name": "Deuker",
  "defendant_sex": "Male",
  "poll_interval": 600,
  "data_file": "docket_monitor_deuker_ricardo.json",  (optional, auto-generated if not specified)
  "download_documents": true,  (optional, default: true)
  "documents_dir": "court_documents",  (optional, default: court_documents)
  "filter_case_number": "F-25-024652"  (optional, monitor only this specific case)
}
        '''
    )

    parser.add_argument(
        '--first',
        help='Defendant first name'
    )
    parser.add_argument(
        '--last',
        help='Defendant last name'
    )
    parser.add_argument(
        '--sex',
        default='Male',
        help='Defendant sex (Male/Female, default: Male)'
    )
    parser.add_argument(
        '-c', '--config',
        action='append',
        help='JSON config file(s) with defendant info and poll_interval (can specify multiple)'
    )
    parser.add_argument(
        '-i', '--interval',
        type=int,
        default=300,
        help='Polling interval in seconds (default: 300 = 5 min)'
    )
    parser.add_argument(
        '-d', '--data-file',
        default='docket_monitor_data.json',
        help='Data file for tracking (default: auto-generated based on defendant name)'
    )
    parser.add_argument(
        '--once',
        action='store_true',
        help='Run once and exit (no continuous monitoring)'
    )
    parser.add_argument(
        '--all',
        action='store_true',
        help='Fetch all data without loading/saving state (implies --once, prevents continuous monitoring)'
    )
    parser.add_argument(
        '--no-downloads',
        action='store_true',
        help='Disable automatic document downloads'
    )
    parser.add_argument(
        '--documents-dir',
        default='court_documents',
        help='Directory to store downloaded documents (default: court_documents)'
    )
    parser.add_argument(
        '--case',
        default='',
        help='Monitor only a specific case number (e.g., F-25-024652 or F25024652)'
    )
    parser.add_argument(
        '--screenshots',
        action='store_true',
        help='Enable debug screenshots (default: off)'
    )

    args = parser.parse_args()

    # Set download_documents based on --no-downloads flag
    args.download_documents = not args.no_downloads

    # --all implies --once (prevent continuous monitoring with stateless mode)
    if args.all:
        args.once = True
        print("ℹ️  Note: --all flag implies --once (single run mode)")
        print("         State will not be loaded or saved.\n")

    # Build list of monitor configurations
    monitor_configs = []

    if args.config:
        # Load configurations from config file(s)
        # #region agent log
        with open('/home/sfeltner/Projects/deuker-monitor/.cursor/debug.log', 'a') as f:
            import json as json_module
            f.write(json_module.dumps({'sessionId':'debug-session','runId':'post-fix','hypothesisId':'E','location':'deuker-monitor.py:2113','message':'Before load_monitor_config','data':{'args_case':getattr(args,'case','NOT_SET'),'args_all':getattr(args,'all',False),'config_files':args.config},'timestamp':int(time.time()*1000)})+'\n')
        # #endregion
        for config_file in args.config:
            config = load_monitor_config(config_file, args)
            # #region agent log
            with open('/home/sfeltner/Projects/deuker-monitor/.cursor/debug.log', 'a') as f:
                import json as json_module
                f.write(json_module.dumps({'sessionId':'debug-session','runId':'post-fix','hypothesisId':'E','location':'deuker-monitor.py:2119','message':'After load_monitor_config','data':{'config_filter_case_number':config.get('filter_case_number','NOT_SET') if config else 'CONFIG_IS_NONE'},'timestamp':int(time.time()*1000)})+'\n')
            # #endregion
            if config is None:
                return 1
            monitor_configs.append(config)
    else:
        # Use command-line arguments
        defendant_first_name = args.first
        defendant_last_name = args.last
        defendant_sex = args.sex
        poll_interval = args.interval
        data_file = args.data_file

        if not defendant_first_name or not defendant_last_name:
            print("❌ Error: Defendant first and last name required (use --first/--last or -c)")
            parser.print_help()
            return 1

        # Auto-generate data file name based on defendant if using default
        if data_file == 'docket_monitor_data.json':
            safe_first = defendant_first_name.lower().replace(' ', '_')
            safe_last = defendant_last_name.lower().replace(' ', '_')
            data_file = f"docket_monitor_{safe_last}_{safe_first}.json"

        monitor_configs.append({
            'defendant_first_name': defendant_first_name,
            'defendant_last_name': defendant_last_name,
            'defendant_sex': defendant_sex,
            'poll_interval': poll_interval,
            'data_file': data_file,
            'skip_state': args.all,
            'notification_sms': '',
            'notification_email': '',
            'download_documents': args.download_documents,
            'documents_dir': args.documents_dir,
            'filter_case_number': args.case,
            'enable_screenshots': args.screenshots,
            'smtp_server': '',
            'smtp_port': 587,
            'smtp_username': '',
            'smtp_password': '',
            'smtp_from_address': '',
            'twilio_account_sid': '',
            'twilio_auth_token': '',
            'twilio_phone_number': '',
            'ice_monitoring': False,
            'country_of_birth': '',
            'dob_month': '',
            'dob_day': '',
            'dob_year': ''
        })

    # Warn about aggressive polling
    for config in monitor_configs:
        if config['poll_interval'] < 60:
            print(f"⚠️  Warning: Interval < 60 seconds may be too aggressive for {config['defendant_first_name']} {config['defendant_last_name']}")

    # Run monitors
    if args.once:
        # Run once mode - check each defendant sequentially
        print(f"\n🔍 Running single check for {len(monitor_configs)} defendant(s)...\n")

        for idx, config in enumerate(monitor_configs, 1):
            print("=" * 80)
            print(f"Defendant {idx}/{len(monitor_configs)}: {config['defendant_first_name']} {config['defendant_last_name']}")
            print("=" * 80)

            monitor = MiamiDadeCourtMonitor(**config)
            # #region agent log
            with open('/home/sfeltner/Projects/deuker-monitor/.cursor/debug.log', 'a') as f:
                import json as json_module
                f.write(json_module.dumps({'sessionId':'debug-session','runId':'post-fix','hypothesisId':'E','location':'deuker-monitor.py:2168','message':'Monitor created with config','data':{'filter_case_number':config.get('filter_case_number','NOT_SET'),'skip_state':config.get('skip_state',False),'all_keys':list(config.keys())},'timestamp':int(time.time()*1000)})+'\n')
            # #endregion
            try:
                monitor._init_browser()
                # #region agent log
                with open('/home/sfeltner/Projects/deuker-monitor/.cursor/debug.log', 'a') as f:
                    import json as json_module
                    f.write(json_module.dumps({'sessionId':'debug-session','runId':'post-fix','hypothesisId':'E','location':'deuker-monitor.py:2171','message':'Before check_all_cases','data':{'monitor_filter_case_number':monitor.filter_case_number},'timestamp':int(time.time()*1000)})+'\n')
                # #endregion
                results = monitor.check_all_cases()
                monitor.on_new_entries(results)
                monitor.print_summary(results)
            finally:
                monitor._close_browser()

            if idx < len(monitor_configs):
                print("\n")

        print("\n✅ All checks complete.")
    else:
        # Continuous monitoring mode
        if len(monitor_configs) > 1:
            print("⚠️  Warning: Continuous monitoring of multiple defendants not yet supported.")
            print("Please use --once flag or run separate instances for each defendant.")
            return 1

        # Run single monitor in continuous mode
        monitor = MiamiDadeCourtMonitor(**monitor_configs[0])
        monitor.run()

    return 0


if __name__ == "__main__":
    exit(main())
