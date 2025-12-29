# core/management/commands/load_tz_regions.py
import requests
from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand
from django.utils.text import slugify
from core.models import Region, District

WIKI_REGIONS_URL = "https://en.wikipedia.org/wiki/Regions_of_Tanzania"

class Command(BaseCommand):
    help = "Load Tanzania regions and districts by scraping Wikipedia. Requires internet."

    def handle(self, *args, **options):
        resp = requests.get(WIKI_REGIONS_URL, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')

        # Find the table or list containing regions. Wikipedia structure may change.
        # We'll iterate over region links in the list of regions on the page.
        region_links = []
        # Try to find "List of regions" table or the contents of the list
        # Simple heuristic: find all <a> inside the article that link to region pages and have "Region" or capital link nearby
        content = soup.find(id='mw-content-text')
        # collect region names by scanning list items and tables
        candidate_anchors = content.find_all('a')
        # We will collect unique region names from the "List of regions" part by matching link targets that exist as pages
        names = set()
        for a in candidate_anchors:
            txt = (a.get_text() or '').strip()
            href = a.get('href') or ''
            if not href.startswith('/wiki/'):
                continue
            # skip irrelevant links
            if any(x in href.lower() for x in ['help:', 'file:', 'category']):
                continue
            # Heuristic: region names are capitalized and not too long; we'll accept typical region names
            if txt and len(txt) < 40 and txt[0].isupper():
                names.add((txt, href))

        self.stdout.write(f"Found candidate region link count: {len(names)} - attempting to resolve best matches")

        # We'll go through a hand-picked subset by seeing if that page contains "Districts" or "Wards"
        regions_created = 0
        for txt, href in sorted(names):
            # get the page
            try:
                r = requests.get(f'https://en.wikipedia.org{href}', timeout=15)
                if r.status_code != 200:
                    continue
                page = BeautifulSoup(r.text, 'html.parser')
                page_text = page.get_text().lower()
                # Only accept candidate if the page mentions 'district' or 'districts'
                if 'district' not in page_text:
                    continue
                # create region
                reg, _ = Region.objects.get_or_create(name=txt, slug=slugify(txt))
                regions_created += 1
                # find district names on the page (common patterns: tables, lists with 'District' or 'districts')
                district_names = set()
                # search for tables with header containing "District"
                tables = page.find_all('table')
                for tab in tables:
                    if 'district' in tab.get_text().lower():
                        # extract text from table rows
                        for td in tab.find_all(['td', 'th']):
                            text = td.get_text(separator=' ', strip=True)
                            if text and len(text) < 80 and 'district' not in text.lower():
                                # split by commas or newlines
                                parts = [p.strip() for p in text.replace('\xa0', ' ').split('\n') if p.strip()]
                                for p in parts:
                                    if len(p) > 2 and len(p) < 60:
                                        district_names.add(p)
                # fallback: look for lists <li>
                if not district_names:
                    for li in page.find_all('li'):
                        t = li.get_text(strip=True)
                        # often district names are short phrases, avoid long descriptions
                        if len(t) < 80 and 'district' in t.lower():
                            # remove the word 'district' and parentheses
                            cleaned = t.replace('District','').replace('district','').strip(' -–:,.()')
                            if cleaned:
                                district_names.add(cleaned)
                # Final pass: split on commas for any lines that look like lists
                final_dnames = set()
                for dn in district_names:
                    for part in dn.split(','):
                        p = part.strip()
                        if p:
                            final_dnames.add(p)

                # Create district records
                created = 0
                for dname in sorted(final_dnames):
                    District.objects.get_or_create(region=reg, name=dname)
                    created += 1

                self.stdout.write(self.style.SUCCESS(f"Region: {reg.name} - districts added: {created}"))
            except Exception as e:
                self.stderr.write(f"Skipping {txt} due to error: {e}")

        self.stdout.write(self.style.SUCCESS(f"Regions processed: {regions_created}"))
        self.stdout.write("Done. Inspect the DB for Regions and Districts. If some districts look wrong, you can manually edit them in admin.")
