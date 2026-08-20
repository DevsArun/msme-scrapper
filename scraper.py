import sys
import pandas as pd
import json
import re
import time
import random
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

# --- BROAD & PROFITABLE FILTER LOGIC ---
def is_target_lead(name, activity_str):
    name = str(name).lower() if pd.notna(name) else ""
    try:
        if pd.isna(activity_str):
            desc = ""
        else:
            activities = json.loads(activity_str)
            desc = " ".join([act.get('Description', '').lower() for act in activities])
    except:
        desc = str(activity_str).lower()

    # STRICT JUNK REJECTION
    junk_keywords = [
        "household", "cleaning", "dusting", "repair of", "maintenance", 
        "retail sale of food", "cereals", "pulses", "grocery", "general store",
        "kirana", "dairy", "poultry", "meat", "fish", "spices", "sweet", "bakery",
        "canteen", "fast food", "stall", "tailor", "begging", 
        "religious", "pipeline", "utensils", "pan", "bidi"
    ]
    
    if any(junk in desc for junk in junk_keywords) or any(junk in name for junk in junk_keywords):
        return False

    # PROFITABLE BUSINESSES (High & Medium Ticket)
    target_keywords = [
        "hospital", "diagnostic", "nursing home", "pathological", "clinic",
        "real estate", "builder", "developer", "architect", "construction",
        "travel agency", "tour", "resort", "hotel",
        "jeweller", "gold", "diamond",
        "automobile", "showroom", "university", "institute", "coaching", "school",
        "garment", "boutique", "apparel", "clothing",
        "beauty", "salon", "parlour", "spa",
        "hardware", "furniture", "photography", "event", "gym", "fitness"
    ]
    
    if any(target in desc for target in target_keywords) or any(target in name for target in target_keywords):
        return True
        
    return False

# --- CONTACT EXTRACTOR ---
PHONE_RE = re.compile(r"(?:\+91[\-\s]?|0)?[6-9]\d{4}[\s\-]?\d{5}")
EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

def clean_phone(p):
    d = re.sub(r"\D", "", p)
    if len(d) == 12 and d.startswith("91"): d = d[2:]
    if len(d) == 11 and d.startswith("0"): d = d[1:]
    return d if len(d) == 10 and d[0] in "6789" else None

def get_page(driver, url):
    try:
        driver.get(url)
        time.sleep(3)
        return driver.page_source
    except:
        return ""

def search_contact(driver, name, district):
    q = f'"{name}" {district} contact phone email'.replace(" ", "+")
    html = get_page(driver, f"https://www.google.com/search?q={q}&hl=en")
    
    phones = {clean_phone(p) for p in PHONE_RE.findall(html) if clean_phone(p)}
    emails = {e.lower() for e in EMAIL_RE.findall(html) if not any(b in e.lower() for b in ["example", ".png", "google", "wix"])}
    
    return next(iter(phones), None), next(iter(emails), None)

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("❌ Error: Missing arguments. Use: python scraper.py <file> <start_row> <limit>")
        sys.exit(1)
        
    input_csv = sys.argv[1]
    start_row = int(sys.argv[2])
    limit = int(sys.argv[3])
    
    print(f"📂 Reading Data from: {input_csv}...")
    try:
        df = pd.read_csv(input_csv)
    except FileNotFoundError:
        print(f"❌ Error: File '{input_csv}' not found.")
        sys.exit(1)
    
    print("🧹 Applying Filter...")
    df['Is_Target'] = df.apply(lambda x: is_target_lead(x.get('EnterpriseName', ''), x.get('Activities', '')), axis=1)
    filtered_leads = df[df['Is_Target'] == True].copy().reset_index(drop=True)
    
    total_found = len(filtered_leads)
    print(f"✅ Total Tech-Ready Leads Found in File: {total_found}")
    
    # BATCH SLICING
    end_row = min(start_row + limit, total_leads_found := total_found)
    print(f"⏳ Processing batch: Row {start_row} to {end_row-1} (Total {end_row - start_row} leads for this run)")
    
    batch_leads = filtered_leads.iloc[start_row:end_row].copy()

    if batch_leads.empty:
        print("⚠️ No leads left to process in this range.")
        sys.exit(0)

    print("🌐 Setting up Headless Browser...")
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
    
    driver = webdriver.Chrome(options=opts)
    
    phones, emails = [], []
    found_count = 0
    
    print("\n🚀 STARTING LEAD EXTRACTION (Real-Time Output)...\n")
    
    for idx, row in batch_leads.iterrows():
        name = row.get('EnterpriseName', 'Unknown')
        dist = row.get('District', 'Bihar')
        print(f"🔎 [Row {idx}] Searching: {name} ...", end=" ")
        
        try:
            phone, email = search_contact(driver, name, dist)
            phones.append(phone)
            emails.append(email)
            
            result_str = ""
            if phone: result_str += f"📞 {phone} "
            if email: result_str += f"📧 {email}"
            
            if result_str:
                print(f"✅ {result_str}")
                found_count += 1
            else:
                print("❌ No contact found")
                
        except Exception:
            phones.append(None)
            emails.append(None)
            print("⚠️ Error searching")
            
        time.sleep(random.uniform(2.5, 4.5)) 
        
    driver.quit()
    
    batch_leads['Mobile_No'] = phones
    batch_leads['Email'] = emails
    
    final_data = batch_leads.dropna(subset=['Mobile_No', 'Email'], how='all')
    print(f"\n🎉 Extraction Complete for this batch! Valid leads with contacts: {len(final_data)}")
    
    file_prefix = f"premium_leads_contacts_{start_row}_to_{end_row}"
    final_data.to_csv(f"{file_prefix}.csv", index=False)
    final_data.to_excel(f"{file_prefix}.xlsx", index=False)
    print(f"💾 Saved as {file_prefix}.csv and .xlsx. Ready for download!")
