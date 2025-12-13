# Refactoring Example: Modular Architecture

This document shows how the monolithic `MiamiDadeCourtMonitor` class can be refactored into a modular architecture. This is a **reference implementation** - not meant to replace the current code immediately, but to demonstrate the pattern.

## Current Structure (Monolithic)

```python
class MiamiDadeCourtMonitor:
    # 2,000+ lines doing everything:
    # - Browser automation
    # - HTML parsing
    # - State management
    # - Notifications
    # - Document downloads
    # - Configuration
```

## Proposed Structure (Modular)

### 1. Core Models (`models/models.py`)

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class Charge:
    case_number: str
    sequence_number: str
    charge_description: str
    charge_type: str
    disposition: str
    timestamp_found: str

@dataclass
class DocketEntry:
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
    case_number: str
    filed_date: str
    closed_date: str
    first_charge: str
    balance_due: str
    charge_count: int
    docket_count: int
    last_checked: str
```

### 2. Browser Automation (`core/browser.py`)

```python
from playwright.sync_api import sync_playwright, Browser, Page, Playwright
from typing import Optional
import logging

class BrowserManager:
    """Manages Playwright browser lifecycle"""
    
    def __init__(self, headless: bool = True):
        self.headless = headless
        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.logger = logging.getLogger(__name__)
    
    def __enter__(self):
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
    
    def start(self):
        """Initialize browser"""
        self.logger.info("Initializing browser...")
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=self.headless)
        self.page = self.browser.new_page()
        self.page.set_viewport_size({"width": 1920, "height": 1080})
        self.logger.info("Browser initialized")
    
    def close(self):
        """Close browser and cleanup"""
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
    
    def navigate(self, url: str, wait_until: str = "networkidle", timeout: int = 60000):
        """Navigate to URL"""
        self.page.goto(url, wait_until=wait_until, timeout=timeout)
    
    def click_selector(self, selector: str, timeout: int = 5000) -> bool:
        """Click element with multiple selector fallbacks"""
        selectors = [
            selector,
            f'text={selector}',
            f':has-text("{selector}")',
        ]
        
        for sel in selectors:
            try:
                self.page.click(sel, timeout=timeout)
                return True
            except:
                continue
        return False
```

### 3. Data Scraper (`core/scraper.py`)

```python
from bs4 import BeautifulSoup
from typing import List, Dict
from models.models import Charge, DocketEntry
from core.browser import BrowserManager
import logging

class CourtDataScraper:
    """Handles HTML parsing and data extraction"""
    
    def __init__(self, browser: BrowserManager):
        self.browser = browser
        self.logger = logging.getLogger(__name__)
    
    def extract_case_links(self, defendant_first_name: str, 
                          defendant_last_name: str, 
                          defendant_sex: str) -> List[Dict[str, str]]:
        """Extract case information from search results"""
        cases = []
        
        # Perform search
        if not self._perform_search(defendant_first_name, defendant_last_name, defendant_sex):
            return cases
        
        # Click defendant result
        defendant_name = f"{defendant_last_name.upper()}, {defendant_first_name.upper()}"
        if not self.browser.click_selector(defendant_name):
            return cases
        
        # Parse case table
        html = self.browser.page.content()
        soup = BeautifulSoup(html, 'html.parser')
        table = soup.find('table')
        
        if not table:
            return cases
        
        # Extract case data
        for row in table.find_all('tr'):
            cells = row.find_all('td')
            if len(cells) >= 4:
                case_data = self._parse_case_row(cells)
                if case_data:
                    cases.append(case_data)
        
        return cases
    
    def extract_charges(self, case_number: str) -> List[Charge]:
        """Extract charges from case page"""
        charges = []
        html = self.browser.page.content()
        soup = BeautifulSoup(html, 'html.parser')
        
        # Find charges table
        for table in soup.find_all('table'):
            headers = table.find_all('th')
            if headers:
                header_text = ' '.join([h.get_text() for h in headers]).lower()
                if 'seq no' in header_text and 'charge' in header_text:
                    # Parse charge rows
                    for row in table.find_all('tr')[1:]:  # Skip header
                        charge = self._parse_charge_row(row, case_number)
                        if charge:
                            charges.append(charge)
                    break
        
        return charges
    
    def extract_dockets(self, case_number: str) -> List[DocketEntry]:
        """Extract docket entries from case page"""
        dockets = []
        html = self.browser.page.content()
        soup = BeautifulSoup(html, 'html.parser')
        
        # Similar logic for dockets
        # ... (implementation details)
        
        return dockets
    
    def _perform_search(self, first_name: str, last_name: str, sex: str) -> bool:
        """Perform defendant search"""
        # Implementation
        pass
    
    def _parse_case_row(self, cells) -> Optional[Dict[str, str]]:
        """Parse a single case table row"""
        # Implementation
        pass
    
    def _parse_charge_row(self, row, case_number: str) -> Optional[Charge]:
        """Parse a single charge table row"""
        # Implementation
        pass
```

### 4. State Management (`core/state.py`)

```python
from abc import ABC, abstractmethod
from typing import Set, Dict
from pathlib import Path
import json
from models.models import CaseInfo
import logging

class StateStorage(ABC):
    """Abstract base class for state storage"""
    
    @abstractmethod
    def load_seen_charges(self) -> Set[str]:
        pass
    
    @abstractmethod
    def save_seen_charge(self, charge_hash: str):
        pass
    
    @abstractmethod
    def load_seen_dockets(self) -> Set[str]:
        pass
    
    @abstractmethod
    def save_seen_docket(self, docket_hash: str):
        pass
    
    @abstractmethod
    def load_case_info(self) -> Dict[str, CaseInfo]:
        pass
    
    @abstractmethod
    def save_case_info(self, case_info: Dict[str, CaseInfo]):
        pass

class JSONStateStorage(StateStorage):
    """JSON file-based state storage (current implementation)"""
    
    def __init__(self, data_file: Path, skip_state: bool = False):
        self.data_file = data_file
        self.skip_state = skip_state
        self.seen_charges: Set[str] = set()
        self.seen_dockets: Set[str] = set()
        self.case_info: Dict[str, CaseInfo] = {}
        self.logger = logging.getLogger(__name__)
        self._load()
    
    def _load(self):
        """Load state from file"""
        if self.skip_state or not self.data_file.exists():
            return
        
        try:
            with open(self.data_file, 'r') as f:
                data = json.load(f)
                self.seen_charges = set(data.get('seen_charges', []))
                self.seen_dockets = set(data.get('seen_dockets', []))
                # Reconstruct case_info
                for case_num, case_data in data.get('case_info', {}).items():
                    self.case_info[case_num] = CaseInfo(**case_data)
        except Exception as e:
            self.logger.error(f"Error loading state: {e}")
    
    def save(self):
        """Save state to file"""
        if self.skip_state:
            return
        
        try:
            data = {
                'seen_charges': list(self.seen_charges),
                'seen_dockets': list(self.seen_dockets),
                'case_info': {k: asdict(v) for k, v in self.case_info.items()},
            }
            with open(self.data_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            self.logger.error(f"Error saving state: {e}")
    
    def load_seen_charges(self) -> Set[str]:
        return self.seen_charges
    
    def save_seen_charge(self, charge_hash: str):
        self.seen_charges.add(charge_hash)
        self.save()
    
    # ... implement other abstract methods
```

### 5. Notification Services (`notifications/__init__.py`)

```python
from typing import List
from models.models import Charge, DocketEntry

class NotificationService:
    """Base class for notification services"""
    
    def send(self, new_charges: List[Charge], new_dockets: List[DocketEntry]):
        """Send notification"""
        raise NotImplementedError

class NotificationManager:
    """Orchestrates multiple notification services"""
    
    def __init__(self, services: List[NotificationService]):
        self.services = services
    
    def notify(self, new_charges: List[Charge], new_dockets: List[DocketEntry]):
        """Send notifications via all registered services"""
        for service in self.services:
            try:
                service.send(new_charges, new_dockets)
            except Exception as e:
                # Log but don't fail if one notification fails
                logging.error(f"Notification service {service} failed: {e}")
```

### 6. Main Monitor (`core/monitor.py`)

```python
from core.browser import BrowserManager
from core.scraper import CourtDataScraper
from core.state import StateStorage
from notifications import NotificationManager
from models.models import Charge, DocketEntry
import hashlib
import logging

class MiamiDadeCourtMonitor:
    """Main orchestrator class - now much smaller and focused"""
    
    def __init__(self, 
                 defendant_first_name: str,
                 defendant_last_name: str,
                 defendant_sex: str,
                 state_storage: StateStorage,
                 notification_manager: NotificationManager,
                 browser_headless: bool = True):
        self.defendant_first_name = defendant_first_name
        self.defendant_last_name = defendant_last_name
        self.defendant_sex = defendant_sex
        self.state_storage = state_storage
        self.notification_manager = notification_manager
        self.browser_headless = browser_headless
        self.logger = logging.getLogger(__name__)
    
    def check_all_cases(self) -> Dict[str, any]:
        """Check all cases - now delegates to other components"""
        results = {
            'total_cases': 0,
            'total_charges': 0,
            'total_dockets': 0,
            'new_charges': [],
            'new_dockets': [],
            'case_summaries': []
        }
        
        with BrowserManager(headless=self.browser_headless) as browser:
            scraper = CourtDataScraper(browser)
            
            # Extract cases
            cases = scraper.extract_case_links(
                self.defendant_first_name,
                self.defendant_last_name,
                self.defendant_sex
            )
            
            results['total_cases'] = len(cases)
            
            # Process each case
            for case_data in cases:
                case_number = case_data['case_number']
                
                # Extract charges and dockets
                charges = scraper.extract_charges(case_number)
                dockets = scraper.extract_dockets(case_number)
                
                # Check for new entries
                new_charges = self._find_new_charges(charges)
                new_dockets = self._find_new_dockets(dockets)
                
                results['new_charges'].extend(new_charges)
                results['new_dockets'].extend(new_dockets)
                results['total_charges'] += len(charges)
                results['total_dockets'] += len(dockets)
            
            # Save state
            self.state_storage.save()
            
            # Send notifications
            if results['new_charges'] or results['new_dockets']:
                self.notification_manager.notify(
                    results['new_charges'],
                    results['new_dockets']
                )
        
        return results
    
    def _find_new_charges(self, charges: List[Charge]) -> List[Charge]:
        """Find charges not seen before"""
        new_charges = []
        seen = self.state_storage.load_seen_charges()
        
        for charge in charges:
            charge_hash = self._hash_charge(charge)
            if charge_hash not in seen:
                new_charges.append(charge)
                self.state_storage.save_seen_charge(charge_hash)
        
        return new_charges
    
    def _hash_charge(self, charge: Charge) -> str:
        """Generate hash for charge"""
        content = f"{charge.case_number}|{charge.sequence_number}|{charge.charge_description}"
        return hashlib.sha256(content.encode()).hexdigest()
    
    # Similar for dockets...
```

### 7. Usage Example

```python
# Before (monolithic):
monitor = MiamiDadeCourtMonitor(
    defendant_first_name="Ricardo",
    defendant_last_name="Deuker",
    defendant_sex="Male",
    poll_interval=600,
    notification_email="user@example.com",
    # ... 10+ more parameters
)
monitor.run()

# After (modular):
from core.state import JSONStateStorage
from notifications.sms import TwilioSMSService
from notifications.email import SMTPEmailService
from notifications import NotificationManager

# Build components
state = JSONStateStorage(Path("docket_monitor_data.json"))

sms_service = TwilioSMSService(phone_number="+1234567890")
email_service = SMTPEmailService(email="user@example.com")
notifications = NotificationManager([sms_service, email_service])

# Build monitor
monitor = MiamiDadeCourtMonitor(
    defendant_first_name="Ricardo",
    defendant_last_name="Deuker",
    defendant_sex="Male",
    state_storage=state,
    notification_manager=notifications
)

# Use monitor
results = monitor.check_all_cases()
```

## Benefits of This Refactoring

1. **Testability**: Each component can be tested independently
2. **Reusability**: Browser manager, scraper, notifications can be reused
3. **Flexibility**: Easy to swap implementations (e.g., database instead of JSON)
4. **Maintainability**: Smaller, focused classes are easier to understand
5. **Extensibility**: Easy to add new notification types, storage backends

## Migration Strategy

1. **Phase 1**: Create new modules alongside existing code
2. **Phase 2**: Gradually move functionality, keeping old code working
3. **Phase 3**: Add integration tests to verify parity
4. **Phase 4**: Switch over and remove old code

This allows for incremental refactoring without breaking existing functionality.


