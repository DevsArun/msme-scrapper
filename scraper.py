import sys
import pandas as pd
import json
import re
import time
import random
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

# ================= CONFIG & REGEX =================
PAGE_WAIT = 4
PHONE_RE = re.compile(r"(?:\+91[\-\s]?|0)?[6-9]\d{4}[\s\-]?\d{5}")
EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
BAD_EMAIL_BITS = ("example.", "sentry", "wixpress", ".png", ".jpg", ".gif", "@2x", "schema.org", "godaddy", "domain.com", "google.", "gstatic")
BAD_SITE_BITS = ("google.", "justdial", "indiamart", "facebook.", "instagram.", "linkedin.", "zaubacorp", "tofler", "sulekha", "youtube.", "wikipedia", "tradeindia", "udyam", "gov.in", "maps.")

# ================= FILTERS =================

def is_high_potential_tech_lead(name, activity_str):
    """Sirf unko select karega jo App ya Website banwa sakte hain"""
    name = str(name).lower() if pd.notna(name) else ""
    try:
        activities = json.loads(activity_str) if pd.notna(activity_str) else []
        desc = " ".join([act.get('Description', '').lower() for act in activities])
    except:
        desc = str(activity_str).lower()

    # Reject micro/retail businesses completely
    junk = ["household", "cleaning", "repair", "maintenance", "retail sale", "kirana", 
            "grocery", "general store", "dairy", "poultry", "meat", "spices", "sweet", 
            "bakery", "canteen", "stall", "tailor", "begging", "religious", "utensils", 
            "cyber", "hardware", "furniture", "readymade garments"]
    
    if any(j in desc for j in junk) or any(j in name for j in junk):
        return False

    # Keep only High-Ticket / Tech-Hungry niches
    premium = ["hospital", "nursing home", "diagnostic", "pathological", "clinic",
               "real estate", "builder", "developer", "architect", "construction of building",
               "travel agency", "tour operator", "hotel", "resort",
               "university", "institute", "coaching", "school", "college",
               "software", "tech", "it service", "startup",
               "jeweller", "automobile dealer", "car showroom", "logistics"]
    
    if any(p in desc for p in premium) or any(p in name for p in premium):
        return True
        
    return False

# ================= SCRAPING HELPERS (From User's Script) =================

def clean_phone(p):
    d = re.sub(r"\D", "", p)
    if len(d) == 12 and d.startswith("91"): d = d[2:]
    if len(d) == 11 and d.startswith("0"): d = d[1:]
    return d if len(d) == 10 and d[0] in "6789" else None

def good_email(e):
    e = e.lower().strip(".")
    return None if any(b in e for b in BAD_EMAIL_BITS) else e

def extract_contacts(text):
    phones = {p for p in (clean_phone(m) for m in PHONE_RE.findall(text)) if p}
    emails = {e for e in (good_email(m) for m in EMAIL_RE.findall(text)) if e}
    return phones, emails

def get_page(driver, url, wait=PAGE_WAIT):
    try:
        driver.get(url)
        time.sleep(wait)
        return driver.page_source
    except:
        return ""

def gmaps_lookup(driver, name, city):
    q = f"{name} {city}".replace(" ", "+")
    html = get_page(driver, "https://www.google.com/maps/search/" + q + "?hl=en")
    if not html: return None, None
    phones, _ = extract_contacts(html)
    phone = next(iter(phones)) if phones else None
    website = None
    try:
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.startswith("http") and not any(b in href for b in BAD_SITE_BITS):
                website = href.split("?")[0]
                break
    except: pass
    return phone, website

def gsearch_lookup(driver, name, city):
    q = f'"{name}" {city} contact phone'.replace(" ", "+")
    html = get_page(driver, "https://www.google.com/search?q=" + q + "&hl=en&gl=in&num=10", wait=3)
    if not html or "unusual traffic" in html.lower():
        return None, None, None, True
    phones, emails = extract_contacts(html)
    website = None
    try:
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            m = re.search(r"[?&]q=(https?://[^&]+)", href)
            if m: href = m.group(1)
            if href.startswith("http") and not any(b in href for b in BAD_SITE_BITS):
                website = href.split("&")[0].split("?")[0]
                break
    except: pass
    return next(iter(phones), None), next(iter(emails), None), website, False

def bing_lookup(driver, name, city):
    q = f'"{name}" {city} contact'.replace(" ", "+")
    html = get_page(driver, "https://www.bing.com/search?q=" + q + "&setmkt=en-IN", wait=3)
    if not html: return None, None, None
    phones, emails = extract_contacts(html)
    website = None
    try:
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.select("li.b_algo h2 a[href^='http']"):
            href = a["href"]
            if not any(b in href for b in BAD_SITE_BITS) and "bing." not in href:
                website = href.split("?")[0]
                break
    except: pass
    return next(iter(phones), None), next(iter(emails), None), website

def site_scrape(driver, url):
    html = get_page(driver, url, wait=3)
    if not html: return None, None
    phones, emails = extract_contacts(html)
    try:
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.startswith("mailto:"):
                em = good_email(href[7:].split("?")[0])
                if em: emails.add(em)
            elif href.startswith("tel:"):
                ph = clean_phone(href[4:])
                if ph: phones.add(ph)
            elif "contact" in href.lower() and not emails:
                if href.startswith("/"): href = url.rstrip("/") + href
                if href.startswith("http"):
                    p2, e2 = extract_contacts(get_page(driver, href, wait=2))
                    phones |= p2; emails |= e2
    except: pass
    return next(iter(phones), None), next(iter(emails), None)

# ================= MAIN EXECUTION =================

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("❌ Error: Please provide the CSV filename.")
        sys.exit(1)
        
    input_csv = sys.argv[1]
    print(f"📂 Loading {input_csv}...")
    
    df = pd.read_csv(input_csv)
    initial_count = len(df)
    
    # 1. APPLY DATE FILTER (> MARCH 2026)
    print("⏳ Applying Date Filter (Only leads after March 2026)...")
    df['ParsedDate'] = pd.to_datetime(df['RegistrationDate'], format='mixed', dayfirst=True, errors='coerce')
    target_date = pd.Timestamp('2026-03-31')
    df = df[df['ParsedDate'] > target_date].copy()
    print(f"📅 Leads after March 2026: {len(df)} (Dropped {initial_count - len(df)})")
    
    # 2. APPLY TECH-POTENTIAL FILTER
    print("🧹 Applying High-Ticket Tech Filter...")
    df['Is_Target'] = df.apply(lambda x: is_high_potential_tech_lead(x.get('EnterpriseName'), x.get('Activities')), axis=1)
    filtered_leads = df[df['Is_Target'] == True].copy().reset_index(drop=True)
    
    print(f"✅ Final High-Potential Fresh Leads: {len(filtered_leads)}")
    
    if filtered_leads.empty:
        print("⚠️ No leads matched the strict criteria. Exiting.")
        sys.exit(0)

    # 3. START BROWSER & SCRAPE
    print("🌐 Launching Headless Chromium...")
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
    driver = webdriver.Chrome(options=opts)
    
    phones, emails, websites = [], [], []
    google_blocked = False
    
    print("\n🚀 STARTING MULTI-LAYER SCRAPING (Maps -> Search -> Bing -> Site)\n")
    
    for i, row in filtered_leads.iterrows():
        name = str(row.get('EnterpriseName', '')).strip()
        city = str(row.get('District', 'Bihar')).strip()
        print(f"🔎 [{i+1}/{len(filtered_leads)}] {name} ...", end=" ")
        
        phone = email = website = None
        try:
            # Step A: Google Maps
            p, w = gmaps_lookup(driver, name, city)
            phone = phone or p; website = website or w
            
            # Step B: Google Search
            if not (phone and email) and not google_blocked:
                p, e, w, blocked = gsearch_lookup(driver, name, city)
                if blocked:
                    google_blocked = True
                    print("(⚠️ Google Blocked) ", end="")
                phone = phone or p; email = email or e; website = website or w
                
            # Step C: Bing Fallback
            if not phone and not email:
                p, e, w = bing_lookup(driver, name, city)
                phone = phone or p; email = email or e; website = website or w
                
            # Step D: Deep Website Scrape
            if website and not (phone and email):
                p, e = site_scrape(driver, website)
                phone = phone or p; email = email or e
                
        except Exception as ex:
            print(f"error: {str(ex)[:30]}", end=" ")
            try: driver.quit(); driver = webdriver.Chrome(options=opts)
            except: pass
            
        phones.append(phone)
        emails.append(email)
        websites.append(website)
        
        found = "".join(x for x, v in [("📞", phone), ("📧", email), ("🌐", website)] if v)
        print(found if found else "❌")
        
        time.sleep(random.uniform(2.0, 4.0)) # Anti-ban delay

    driver.quit()
    
    filtered_leads['Mobile_No'] = phones
    filtered_leads['Email'] = emails
    filtered_leads['Website'] = websites
    
    final_data = filtered_leads.dropna(subset=['Mobile_No', 'Email', 'Website'], how='all').reset_index(drop=True)
    
    print(f"\n🎉 Extraction Complete! Found contact info for {len(final_data)} businesses.")
    
    # Save final output
    final_data.drop(columns=['ParsedDate', 'Is_Target'], inplace=True, errors='ignore')
    final_data.to_csv("fresh_tech_leads.csv", index=False)
    final_data.to_excel("fresh_tech_leads.xlsx", index=False)
    print("💾 Saved as fresh_tech_leads.csv and .xlsx!")
