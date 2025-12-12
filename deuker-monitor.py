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
                 filter_case_number: str = ""):
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
            return normalized
        else:
            # Already has dashes or unknown format, return as-is
            self.logger.warning(f"Case number format not recognized: {case_number}")
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
                'defendant_sex': self.defendant_sex
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
                    break
                except:
                    continue

            if not clicked:
                self.logger.error("Could not find Defendant search button")
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
                    break
                except:
                    continue

            # Wait for results to load
            time.sleep(3)
            self.logger.info("Search submitted, waiting for results...")

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
                    clicked_defendant = True
                    break
                except:
                    continue

            if not clicked_defendant:
                self.logger.error("Could not find defendant result to click")
                return cases

            # Wait for the popup with case information to appear
            time.sleep(2)
            self.logger.info("Extracting cases from popup...")

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

                    except Exception as e:
                        self.logger.debug(f"Error parsing case row: {e}")
                        continue

        except Exception as e:
            self.logger.error(f"Error extracting case links: {e}")
            import traceback
            self.logger.debug(traceback.format_exc())

        return cases
    
    def _fetch_case_details(self, case_url: str, case_number: str) -> tuple[List[Charge], List[DocketEntry]]:
        """
        Fetch all charges and docket entries for a specific case

        Args:
            case_url: URL to the case details page
            case_number: Case number for reference

        Returns:
            Tuple of (charges_list, dockets_list)
        """
        charges = []
        dockets = []

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
                    clicked_case = True
                    break
                except Exception as e:
                    self.logger.debug(f"Selector {selector} failed: {e}")
                    continue

            if not clicked_case:
                self.logger.warning(f"Could not click case {case_number}, trying URL navigation...")
                # Fallback: try to navigate directly if clicking didn't work
                if case_url:
                    self.page.goto(case_url, wait_until="networkidle", timeout=60000)
                else:
                    self.logger.error(f"No URL available for case {case_number}, cannot navigate!")
                    return charges, dockets

            # Wait for case page to load
            time.sleep(2)
            self.logger.debug(f"Case page loaded, URL: {self.page.url}")

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
                        clicked_charges = True
                        time.sleep(1)
                        break
                    except Exception as e:
                        self.logger.debug(f"CHARGES selector {selector} failed: {e}")
                        continue

                if not clicked_charges:
                    self.logger.warning("Could not click CHARGES section - may already be expanded or not found")
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
                        clicked_dockets = True
                        time.sleep(1)
                        break
                    except Exception as e:
                        self.logger.debug(f"DOCKETS selector {selector} failed: {e}")
                        continue

                if not clicked_dockets:
                    self.logger.warning("Could not click DOCKETS section - may already be expanded or not found")
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
                self._download_case_documents(case_number, dockets)

            # Check for "Extra Documents" tab
            if self.download_documents:
                self._check_extra_documents_tab(case_number)

        except Exception as e:
            self.logger.error(f"Error fetching case details for {case_number}: {e}")
            import traceback
            self.logger.debug(traceback.format_exc())

        return charges, dockets

    def _download_case_documents(self, case_number: str, dockets: List[DocketEntry]):
        """
        Download documents for dockets that have them available

        Args:
            case_number: The case number
            dockets: List of docket entries to check for documents
        """
        import os
        import re

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

            # Create a unique identifier for this document
            doc_id = f"{case_number}_{docket.din}_{docket.docket_description}"

            # Check if we've already downloaded this document
            if doc_id in self.seen_documents:
                self.logger.debug(f"Document already downloaded: {doc_id}")
                continue

            try:
                # Generate safe filename: case_number-docket_description.pdf
                # Clean docket description to be filesystem-safe
                safe_desc = re.sub(r'[^\w\s-]', '', docket.docket_description)
                safe_desc = re.sub(r'[-\s]+', '-', safe_desc)
                safe_desc = safe_desc[:100]  # Limit length
                filename = f"{case_number}-{safe_desc}.pdf"
                filepath = self.documents_dir / filename

                # If file already exists, add a counter
                counter = 1
                original_filepath = filepath
                while filepath.exists():
                    filename = f"{case_number}-{safe_desc}-{counter}.pdf"
                    filepath = self.documents_dir / filename
                    counter += 1

                self.logger.info(f"Downloading document for Din {docket.din}: {filename}")

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

    def _check_extra_documents_tab(self, case_number: str):
        """Check and download documents from the Extra Documents tab if it exists"""
        import re

        try:
            self.logger.debug(f"Checking for Extra Documents tab in {case_number}...")

            # Look for "Extra Documents" tab/link
            html = self.page.content()
            if 'EXTRA DOCUMENTS' not in html.upper():
                self.logger.debug("No Extra Documents tab found")
                return

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
                    clicked = True
                    time.sleep(1)
                    break
                except Exception as e:
                    self.logger.debug(f"Extra Documents selector {selector} failed: {e}")
                    continue

            if not clicked:
                self.logger.debug("Could not click Extra Documents tab")
                return

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
                return

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

                        # Generate safe filename
                        safe_desc = re.sub(r'[^\w\s-]', '', doc_desc)
                        safe_desc = re.sub(r'[-\s]+', '-', safe_desc)
                        safe_desc = safe_desc[:100]
                        filename = f"{case_number}-{safe_desc}.pdf"
                        filepath = self.documents_dir / filename

                        # Handle duplicate filenames
                        counter = 1
                        while filepath.exists():
                            filename = f"{case_number}-{safe_desc}-{counter}.pdf"
                            filepath = self.documents_dir / filename
                            counter += 1

                        self.logger.info(f"Downloading extra document: {filename}")

                        # For Extra Documents, find and click view button by looking for SVG icon
                        # Extra Documents uses a different structure than Dockets
                        clicked_view = False
                        viewer_page = None
                        initial_pages = len(self.page.context.pages)

                        self.logger.info(f"DEBUG: Looking for Extra Doc view button...")

                        # Debug: Check what's in the first cell
                        first_cell = self.page.locator('table tr:has-text("Arrest Form Summary") td:first-child')
                        if first_cell.count() > 0:
                            cell_html = first_cell.first.inner_html()
                            self.logger.info(f"DEBUG: First cell HTML: {cell_html[:200]}")

                        # The desktop version button is NOT in d-md-none
                        # Look for span with role="button" that's not in a d-md-none div
                        view_links = self.page.locator('table tr:has-text("Arrest Form Summary") td:first-child span[role="button"]:not(.d-md-none span[role="button"])')
                        self.logger.info(f"DEBUG: Found {view_links.count()} desktop view buttons")

                        if view_links.count() == 0:
                            # Fallback: try any span with aria-label containing "View"
                            view_links = self.page.locator('table tr:has-text("Arrest Form Summary") span[aria-label*="View"]')
                            self.logger.info(f"DEBUG: Found {view_links.count()} spans with View aria-label")

                        if view_links.count() > 0:
                            # Use the first one
                            self.logger.info(f"DEBUG: Getting first view link...")
                            view_btn = view_links.first
                            # Skip scroll_into_view - it hangs on Extra Documents

                            self.logger.info(f"DEBUG: About to click Extra Docs view link for: {doc_desc}")
                            try:
                                # Try evaluate click directly on the locator
                                self.logger.info(f"DEBUG: Trying evaluate click...")
                                view_btn.evaluate('el => el.click()')
                                clicked_view = True
                                self.logger.info("DEBUG: Evaluate click succeeded, waiting...")
                            except Exception as e:
                                self.logger.info(f"DEBUG: Evaluate click failed: {e}")
                                # Try dispatch_event
                                try:
                                    self.logger.info(f"DEBUG: Trying dispatch_event...")
                                    view_btn.dispatch_event('click')
                                    clicked_view = True
                                    self.logger.info("DEBUG: Dispatch event succeeded")
                                except Exception as e2:
                                    self.logger.info(f"DEBUG: Dispatch event failed: {e2}")

                            time.sleep(3)  # Wait for page to load

                            # Check if new page opened
                            current_pages = self.page.context.pages
                            self.logger.info(f"DEBUG: Pages before={initial_pages}, after={len(current_pages)}")
                            if len(current_pages) > initial_pages:
                                viewer_page = current_pages[-1]
                                self.page = viewer_page
                                self.logger.info(f"✓ Opened viewer in new page for {doc_desc}")
                            else:
                                # Check if URL changed (inline navigation)
                                self.logger.info(f"DEBUG: Current URL: {self.page.url}")

                        if not clicked_view:
                            self.logger.warning(f"Could not open viewer for extra document: {doc_desc}")
                            continue

                        # Use the consolidated React PDF Viewer download helper
                        if self._handle_react_pdf_viewer_download(filepath, viewer_page, doc_desc):
                            # Success!
                            self.seen_documents.add(doc_id)
                            self.logger.info(f"✓ Downloaded extra document: {filename}")
                        else:
                            self.logger.warning(f"Failed to download extra document: {doc_desc}")

                        # Re-click Extra Documents tab to return to the list
                        for selector in extra_docs_selectors:
                            try:
                                self.page.click(selector, timeout=3000)
                                self.logger.debug("Re-clicked Extra Documents tab")
                                time.sleep(1)
                                break
                            except:
                                continue

                        # Small delay between downloads
                        time.sleep(0.5)

                    except Exception as e:
                        self.logger.debug(f"Error downloading extra document from row {row_index}: {e}")
                        continue

        except Exception as e:
            self.logger.debug(f"Error checking Extra Documents tab: {e}")

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
            'new_charges': [],
            'new_dockets': [],
            'case_summaries': []
        }

        try:
            # Extract case links (this method now handles page navigation)
            cases = self._extract_case_links()

            # Filter to specific case if requested
            if self.filter_case_number:
                self.logger.info(f"Filtering to case: {self.filter_case_number}")
                cases = [c for c in cases if c['case_number'] == self.filter_case_number]

                if not cases:
                    self.logger.warning(f"Case {self.filter_case_number} not found for {self.defendant_first_name} {self.defendant_last_name}")
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
                            clicked_defendant = True
                            time.sleep(2)
                            break
                        except Exception as click_err:
                            self.logger.debug(f"Selector {selector} failed: {click_err}")
                            continue

                    if not clicked_defendant:
                        self.logger.error("Could not open case list")
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
                charges, docket_entries = self._fetch_case_details(case_url, case_number)

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
                    'new_charges_count': len(new_charges_this_case),
                    'new_dockets_count': len(new_dockets_this_case),
                    'first_charge': case_data['first_charge']
                })

                # Be polite - delay between cases
                if case_index < len(cases) - 1:
                    time.sleep(1)
            
            # Save state
            self._save_state()
            
        except Exception as e:
            self.logger.error(f"Error checking cases: {e}")
            import traceback
            self.logger.debug(traceback.format_exc())
        
        return results
    
    def _send_notification(self, new_charges: List[Charge], new_dockets: List[DocketEntry]):
        """
        Send notifications about new charges and dockets via SMS and/or email

        Environment variables needed for Twilio SMS:
        - TWILIO_ACCOUNT_SID: Your Twilio Account SID
        - TWILIO_AUTH_TOKEN: Your Twilio Auth Token
        - TWILIO_PHONE_NUMBER: Your Twilio phone number (e.g., +12345678900)
        """
        import os

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

                account_sid = os.environ.get('TWILIO_ACCOUNT_SID')
                auth_token = os.environ.get('TWILIO_AUTH_TOKEN')
                from_number = os.environ.get('TWILIO_PHONE_NUMBER')

                if not all([account_sid, auth_token, from_number]):
                    self.logger.warning("⚠️  Twilio credentials not found in environment variables")
                    self.logger.warning("   Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, and TWILIO_PHONE_NUMBER")
                else:
                    client = Client(account_sid, auth_token)

                    sms_message = client.messages.create(
                        body=message,
                        from_=from_number,
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

                smtp_server = os.environ.get('EMAIL_SMTP_SERVER')
                smtp_port = int(os.environ.get('EMAIL_SMTP_PORT', '587'))
                smtp_username = os.environ.get('EMAIL_USERNAME')
                smtp_password = os.environ.get('EMAIL_PASSWORD')
                from_email = os.environ.get('EMAIL_FROM_ADDRESS', smtp_username)

                if not all([smtp_server, smtp_username, smtp_password]):
                    self.logger.warning("⚠️  Email credentials not found in environment variables")
                    self.logger.warning("   Set EMAIL_SMTP_SERVER, EMAIL_USERNAME, EMAIL_PASSWORD")
                else:
                    # Create email message
                    msg = MIMEMultipart('alternative')
                    msg['Subject'] = f"🚨 Court Alert: {self.defendant_first_name} {self.defendant_last_name}"
                    msg['From'] = from_email
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

                    # Send email
                    with smtplib.SMTP(smtp_server, smtp_port) as server:
                        server.starttls()
                        server.login(smtp_username, smtp_password)
                        server.sendmail(from_email, self.notification_email, msg.as_string())

                    self.logger.info(f"📧 Email sent to {self.notification_email}")

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
        print("\n" + "="*80)
        print("📊 CASE SUMMARY")
        print("="*80)
        print(f"Total Cases Monitored: {results['total_cases']}")
        print(f"Total Charges: {results['total_charges']}")
        print(f"Total Docket Entries: {results['total_dockets']}")
        print(f"New Charges This Check: {len(results['new_charges'])}")
        print(f"New Dockets This Check: {len(results['new_dockets'])}")
        print()

        if results['case_summaries']:
            print("Per-Case Breakdown:")
            print("-" * 80)
            for summary in results['case_summaries']:
                charge_indicator = f" ({summary['new_charges_count']} NEW!)" if summary.get('new_charges_count', 0) > 0 else ""
                docket_indicator = f" ({summary['new_dockets_count']} NEW!)" if summary.get('new_dockets_count', 0) > 0 else ""
                print(f"  {summary['case_number']}:")
                print(f"    Charges: {summary['charge_count']}{charge_indicator}")
                print(f"    Dockets: {summary['docket_count']}{docket_indicator}")
                print(f"    First Charge: {summary['first_charge']}")
        print("="*80)
    
    def run(self):
        """Run the monitoring loop"""
        self.logger.info("="*60)
        self.logger.info("🚀 Starting Miami-Dade Docket Monitor")
        self.logger.info("="*60)
        self.logger.info(f"⏱️  Poll interval: {self.poll_interval} seconds ({self.poll_interval // 60} minutes)")
        self.logger.info(f"👤 Monitoring defendant: {self.defendant_first_name} {self.defendant_last_name} ({self.defendant_sex})")

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
            # Command-line --case flag overrides config file
            if not filter_case_number:
                filter_case_number = config.get('filter_case_number', filter_case_number)
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
        'filter_case_number': filter_case_number
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
        for config_file in args.config:
            config = load_monitor_config(config_file, args)
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
            'filter_case_number': args.case
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
            try:
                monitor._init_browser()
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
